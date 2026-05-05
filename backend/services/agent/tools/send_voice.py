"""发送语音工具 - 通过 voice_player 发送语音回复."""

import asyncio
import logging
import re
from typing import Dict, List

from .base import Tool, ToolArgument
from backend.services.voice_service import voice_service, VoiceError
from backend.services.context_manager import context_manager

import backend.services.memory_interface as mem_mod

logger = logging.getLogger(__name__)

# D-07: 按句末标点拆分（和 send_message._split_message 相同模式）
_SPLIT_PUNCTS = re.compile(r'[。！？\n]+')


def _split_sentences(text: str) -> List[str]:
    """将文本按句末标点拆分为句子列表。"""
    text = text.strip()
    if not text:
        return []
    parts: list[str] = []
    last = 0
    for m in _SPLIT_PUNCTS.finditer(text):
        end = m.end()
        seg = text[last:end].strip()
        if seg:
            parts.append(seg)
        last = end
    tail = text[last:].strip()
    if tail:
        parts.append(tail)
    return parts if parts else [text]


class SendVoiceTool(Tool):
    """发送语音工具 - 通过 voice_player 发送语音回复。

    D-01: 始终注册在 ToolRegistry 中。
    D-03: 工具描述告知 AI 仅在语音频道可用。
    D-05: 不直接依赖任何平台 API。
    D-09: 不设置文本长度上限。
    """

    @property
    def name(self) -> str:
        return "send_voice"

    @property
    def description(self) -> str:
        # D-03: 明确告知 AI 可用性约束
        return "仅在已连接的语音频道中可用，用于发送语音回复。AI输入文字，系统自动转为语音播放。"

    @property
    def arguments(self) -> list:
        return [
            ToolArgument(
                name="group_id",
                type="string",
                description="群聊ID",
                required=True
            ),
            ToolArgument(
                name="content",
                type="string",
                description="要转为语音发送的完整消息内容",
                required=True
            )
        ]

    async def execute(self, **kwargs) -> Dict:
        group_id = kwargs.get("group_id")
        content = kwargs.get("content")

        if not group_id or not content:
            return {"success": False, "error": "缺少必要参数"}

        # D-02: 检测 voice_player 连接状态
        from backend.services.voice_player import voice_player
        if not voice_player.is_connected():
            return {"success": False, "error": "当前未连接到语音频道"}

        # D-07: 按句子拆分
        sentences = _split_sentences(content)
        if not sentences:
            return {"success": False, "error": "消息内容为空"}

        try:
            # D-07 + D-08: 逐句 TTS 合成（Phase 20 实现流水线并行）
            audio_chunks: List[bytes] = []
            for sentence in sentences:
                try:
                    audio = await voice_service.synthesize(sentence)
                    audio_chunks.append(audio)
                except VoiceError as e:
                    logger.error(f"TTS合成失败: {sentence[:30]}, error: {e}")
                    # D-07: 合成失败立即返回，不做部分投递
                    return {"success": False, "error": f"语音合成失败: {e}"}

            # 通过 voice_player 播放
            success = await voice_player.play_sentences(audio_chunks)
            if not success:
                return {"success": False, "error": "语音播放失败"}

            full_reply = content

            # D-10: 上下文存储（和 send_message 一致）
            await context_manager.add_group_message(
                group_id=group_id,
                user_id="robot",
                role="assistant",
                content=full_reply,
                sender_nickname="机器人",
                mentions=[],
                is_directed_at_bot=False
            )

            # D-11: 记忆提取（fire-and-forget）
            try:
                asyncio.create_task(
                    mem_mod.memory_provider.extract_and_store(
                        group_id=group_id,
                        user_id="robot",
                        content=full_reply,
                        role="assistant",
                        speaker="千雪",
                        source_type="voice_reply",
                    )
                )
            except Exception:
                pass

            # D-12: STM 记录（fire-and-forget）
            try:
                from backend.services.stm_client import stm_client
                asyncio.create_task(stm_client.record_event(
                    event_type="voice_reply",
                    source_type="voice_channel",
                    group_id=group_id,
                    summary=f"你语音回复了: {full_reply[:60]}",
                    importance=0.6,
                ))
            except Exception:
                pass

            logger.info(f"语音回复发送成功: {full_reply[:50]}...")
            return {"success": True, "message": full_reply, "group_id": group_id}

        except Exception as e:
            logger.error(f"发送语音失败: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
