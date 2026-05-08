"""统一消息管理器 — 所有消息收发的唯一入口.

职责：
- 发送端：根据 message.source + group_id 前缀统一路由到 QQ/Discord/TTS
- 工具里的发送逻辑也收拢到此处
- Brain 不再直接调 napcat_client 或 discord_source
"""

import asyncio
import logging
from typing import Optional

from backend.services.agent.message import AgentMessage

logger = logging.getLogger(__name__)


class MessageManager:
    """统一消息管理器."""

    def __init__(self):
        self._voice_sentence_queue: Optional[asyncio.Queue] = None

    def set_voice_sentence_queue(self, queue: asyncio.Queue):
        """设置语音管道的句子队列（用于 TTS 流式播放）。"""
        self._voice_sentence_queue = queue

    async def send_sentence(self, original_msg: AgentMessage, sentence: str) -> bool:
        """发送一个完整句子到对应的目标。

        路由规则：
        - voice_ 前缀 → TTS → voice_player streaming queue
        - dm_ 前缀 → Discord 文字发送
        - private_ 前缀 → QQ 私聊发送
        - 其他 → QQ 群聊发送

        Returns:
            True 表示发送成功
        """
        group_id = original_msg.group_id
        source = original_msg.source

        # 语音频道 → TTS 管道
        if group_id.startswith("voice_"):
            return await self._send_voice(sentence)

        # Discord 文字
        if group_id.startswith("dm_"):
            return await self._send_discord(group_id, sentence)

        # QQ 私聊
        if group_id.startswith("private_"):
            return await self._send_qq_private(group_id, sentence)

        # Discord 群聊（通过 source 判断）
        if source == "discord":
            return await self._send_discord(group_id, sentence)

        # QQ 群聊（默认）
        return await self._send_qq_group(group_id, sentence)

    async def send_text(self, group_id: str, text: str, source: str = "qq",
                        is_private: bool = False) -> bool:
        """发送完整文本（工具调用等场景使用）。

        自动路由到正确平台。
        """
        if group_id.startswith("voice_"):
            return await self._send_voice(text)

        if group_id.startswith("dm_"):
            return await self._send_discord(group_id, text)

        if group_id.startswith("private_"):
            return await self._send_qq_private(group_id, text)

        if source == "discord":
            return await self._send_discord(group_id, text)

        if is_private:
            return await self._send_qq_private(group_id, text)

        return await self._send_qq_group(group_id, text)

    # ------------------------------------------------------------------
    # 内部路由
    # ------------------------------------------------------------------

    async def _send_voice(self, text: str) -> bool:
        """将文字合成 TTS 后放入语音播放队列。"""
        if not self._voice_sentence_queue:
            logger.warning("MessageManager: 语音队列未设置，跳过 TTS")
            return False

        try:
            from backend.services.voice_service import voice_service
            mp3 = await voice_service.synthesize(text)
            await self._voice_sentence_queue.put(mp3)
            return True
        except Exception as e:
            logger.error(f"MessageManager TTS 失败: {e}")
            return False

    async def _send_discord(self, group_id: str, text: str) -> bool:
        """发送 Discord 文字消息。"""
        try:
            from backend.services.agent.sources.discord_source import discord_source
            if discord_source is None or not discord_source.is_connected():
                logger.warning("MessageManager: Discord 未连接")
                return False
            is_private = group_id.startswith("dm_")
            return await discord_source.send_message(
                channel_id=group_id,
                text=text,
                is_private=is_private,
            )
        except Exception as e:
            logger.error(f"MessageManager Discord 发送失败: {e}")
            return False

    async def _send_qq_private(self, group_id: str, text: str) -> bool:
        """发送 QQ 私聊消息。"""
        try:
            from backend.api.napcat import napcat_client
            target_user_id = int(group_id.replace("private_", ""))
            return await napcat_client.send_private_message(target_user_id, text)
        except Exception as e:
            logger.error(f"MessageManager QQ 私聊发送失败: {e}")
            return False

    async def _send_qq_group(self, group_id: str, text: str) -> bool:
        """发送 QQ 群聊消息。"""
        try:
            from backend.api.napcat import napcat_client
            return await napcat_client.send_group_message(int(group_id), text)
        except Exception as e:
            logger.error(f"MessageManager QQ 群聊发送失败: {e}")
            return False


# 模块级单例
message_manager = MessageManager()
