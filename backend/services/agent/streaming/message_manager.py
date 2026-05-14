"""统一消息管理器 — 所有消息收发的唯一入口.

职责：
- 发送端：根据 message.source + group_id 前缀统一路由到 QQ/Discord/TTS
- 工具里的发送逻辑也收拢到此处
- Brain 不再直接调 napcat_client 或 discord_source
- 有序并发 TTS：首句立即合成，后续攒批保持语气一致
"""

import asyncio
import logging
import re
import struct
from typing import Optional

from backend.services.agent.message import AgentMessage

logger = logging.getLogger(__name__)

_AT_PATTERN = re.compile(r'@\[(\d+)\]')

# 并发 TTS 上限（单 GPU 并发会导致 RTF > 1.0，流式断裂）
_MAX_CONCURRENT_TTS = 1

# PCM fade 参数（消除句首/句尾 click 杂音）
_FADE_SAMPLES = 240  # 10ms at 24kHz

# 句子攒批参数（解决逐句合成语气不连贯问题）
_BATCH_MAX = 4          # 最多攒几句一起合成
_BATCH_TIMEOUT = 0.35   # 攒句等待超时（秒）


def _pcm_fade_in(data: bytes) -> bytes:
    """对 PCM 16-bit LE 数据做淡入（消除句首 click）."""
    samples = len(data) // 2
    n = min(_FADE_SAMPLES, samples)
    buf = bytearray(data)
    for i in range(n):
        s = struct.unpack_from('<h', buf, i * 2)[0]
        struct.pack_into('<h', buf, i * 2, max(-32768, min(32767, int(s * i / n))))
    return bytes(buf)


def _pcm_fade_out(data: bytes) -> bytes:
    """对 PCM 16-bit LE 数据做淡出（消除句尾 click）."""
    samples = len(data) // 2
    n = min(_FADE_SAMPLES, samples)
    buf = bytearray(data)
    for i in range(n):
        idx = samples - 1 - i
        s = struct.unpack_from('<h', buf, idx * 2)[0]
        struct.pack_into('<h', buf, idx * 2, max(-32768, min(32767, int(s * i / n))))
    return bytes(buf)


class MessageManager:
    """统一消息管理器."""

    def __init__(self):
        self._voice_sentence_queue: Optional[asyncio.Queue] = None
        # 有序并发 TTS 状态
        self._tts_seq: int = 0
        self._tts_gate: dict[int, asyncio.Event] = {}
        self._tts_semaphore = asyncio.Semaphore(_MAX_CONCURRENT_TTS)
        self._tts_active: bool = False
        # 句子攒批
        self._batch_buf: list[str] = []
        self._batch_timer: Optional[asyncio.TimerHandle] = None

    def set_voice_sentence_queue(self, queue: asyncio.Queue):
        """设置语音管道的句子队列（用于 TTS 流式播放）。"""
        self._voice_sentence_queue = queue

    # ------------------------------------------------------------------
    # TTS 回复生命周期
    # ------------------------------------------------------------------

    def begin_tts_reply(self):
        """开始一轮新的 TTS 回复，重置序号、门控和攒批缓冲。"""
        self._tts_seq = 0
        self._tts_gate.clear()
        self._tts_active = True
        self._batch_buf.clear()
        self._cancel_batch_timer()

    async def end_tts_reply(self):
        """结束当前 TTS 回复，刷出残余批，等待所有任务完成。"""
        self._tts_active = False
        await self._flush_batch()
        if self._tts_gate:
            last_seq = max(self._tts_gate.keys())
            gate = self._tts_gate.get(last_seq)
            if gate:
                try:
                    await asyncio.wait_for(gate.wait(), timeout=60.0)
                except asyncio.TimeoutError:
                    logger.warning("end_tts_reply: 等待最后 TTS 任务超时")

    # ------------------------------------------------------------------
    # 句子攒批
    # ------------------------------------------------------------------

    def _cancel_batch_timer(self):
        if self._batch_timer is not None:
            self._batch_timer.cancel()
            self._batch_timer = None

    def _schedule_batch_flush(self):
        """设置定时器，超时后刷出攒批。"""
        self._cancel_batch_timer()
        loop = asyncio.get_event_loop()
        self._batch_timer = loop.call_later(
            _BATCH_TIMEOUT,
            lambda: asyncio.ensure_future(self._flush_batch()),
        )

    async def _flush_batch(self):
        """将攒批缓冲中的句子合并为一次 TTS 合成。"""
        self._cancel_batch_timer()
        if not self._batch_buf:
            return
        text = "".join(self._batch_buf)
        self._batch_buf.clear()
        seq = self._next_tts_seq()
        asyncio.create_task(self._stream_sentence_tts(seq, text))

    async def _enqueue_tts(self, text: str):
        """Computer TTS 入队 — 首句立即合成，后续攒批。

        首句走独立流式合成以获得最低 TTFB；
        后续句攒到一起给模型更多文本上下文，语气更连贯。
        """
        if self._tts_seq == 0:
            # 首句：立即合成
            seq = self._next_tts_seq()
            asyncio.create_task(self._stream_sentence_tts(seq, text))
        else:
            # 后续：攒批
            self._batch_buf.append(text)
            if len(self._batch_buf) >= _BATCH_MAX:
                await self._flush_batch()
            else:
                self._schedule_batch_flush()

    # ------------------------------------------------------------------
    # 发送接口
    # ------------------------------------------------------------------

    async def send_sentence(self, original_msg: AgentMessage, sentence: str) -> bool:
        """发送一个完整句子到对应的目标。"""
        group_id = original_msg.group_id
        source = original_msg.source

        if group_id.startswith("voice_"):
            if source == "computer":
                return await self._send_computer_voice(sentence)
            return await self._send_voice(sentence)

        if source == "computer":
            if await self._should_computer_voice():
                await self._enqueue_tts(sentence)
            return True

        if group_id.startswith("dm_"):
            return await self._send_discord(group_id, sentence)

        if group_id.startswith("private_"):
            return await self._send_qq_private(group_id, sentence)

        if source == "discord":
            return await self._send_discord(group_id, sentence)

        return await self._send_qq_group(group_id, sentence)

    async def send_text(self, group_id: str, text: str, source: str = "qq",
                        is_private: bool = False) -> bool:
        """发送完整文本（工具调用等场景使用）。"""
        if group_id.startswith("voice_"):
            if source == "computer":
                return await self._send_computer_voice(text)
            return await self._send_voice(text)

        if source == "computer":
            if await self._should_computer_voice():
                await self._enqueue_tts(text)
            return True

        if group_id.startswith("dm_"):
            return await self._send_discord(group_id, text)

        if group_id.startswith("private_"):
            return await self._send_qq_private(group_id, text)

        if source == "discord":
            return await self._send_discord(group_id, text)

        if is_private:
            return await self._send_qq_private(group_id, text)

        return await self._send_qq_group(group_id, text)

    async def send_token(self, original_msg: AgentMessage, token: str) -> bool:
        """推送单个 token 到前端（逐字显示）。仅 computer source 使用."""
        if original_msg.source != "computer":
            return True
        try:
            from backend.routes.computer_routes import send_token_to_computer
            return await send_token_to_computer(token)
        except Exception:
            return False

    async def _should_computer_voice(self) -> bool:
        """检查电脑前端是否开启了语音."""
        try:
            from backend.routes.computer_routes import is_voice_enabled
            return is_voice_enabled()
        except Exception:
            return False

    # ------------------------------------------------------------------
    # 有序并发流式 TTS
    # ------------------------------------------------------------------

    def _next_tts_seq(self) -> int:
        """分配下一个 TTS 序号。"""
        seq = self._tts_seq
        self._tts_seq += 1
        self._tts_gate[seq] = asyncio.Event()
        return seq

    async def _stream_sentence_tts(self, seq: int, text: str):
        """流式 TTS — 合成与推送解耦，边合成边推送到前端。"""
        gate = self._tts_gate[seq]
        chunk_queue: asyncio.Queue = asyncio.Queue()

        async def _synthesize():
            """后台合成，将 chunk 推入队列."""
            try:
                async with self._tts_semaphore:
                    from backend.services.voice_service import voice_service
                    async for chunk in voice_service.synthesize_stream_pcm(text):
                        await chunk_queue.put(("chunk", chunk))
            except Exception as e:
                await chunk_queue.put(("error", e))
            finally:
                await chunk_queue.put(("done", None))

        try:
            from backend.routes.computer_routes import (
                send_audio_begin, send_audio_chunk, send_audio_end,
                send_audio_to_computer,
            )

            # Phase 1: 立即启动合成
            synth_task = asyncio.create_task(_synthesize())

            # Phase 2: 等前一句推送完毕（保序）
            if seq > 0:
                prev_gate = self._tts_gate.get(seq - 1)
                if prev_gate:
                    await prev_gate.wait()

            # Phase 3: 从队列取出 chunk，到达即推送
            chunk_idx = 0
            sent_begin = False
            pending = None
            while True:
                kind, data = await chunk_queue.get()
                if kind == "done":
                    break
                if kind == "error":
                    raise data
                if pending is not None:
                    if not sent_begin:
                        await send_audio_begin(seq, text)
                        pending = _pcm_fade_in(pending)
                        sent_begin = True
                    await send_audio_chunk(seq, chunk_idx, pending)
                    chunk_idx += 1
                pending = data

            # 最后一个 chunk（带 fade-out）
            if pending is not None:
                pending = _pcm_fade_out(pending)
                if not sent_begin:
                    await send_audio_begin(seq, text)
                    pending = _pcm_fade_in(pending)
                    sent_begin = True
                await send_audio_chunk(seq, chunk_idx, pending)
                chunk_idx += 1

            if chunk_idx > 0:
                await send_audio_end(seq)
            else:
                from backend.services.voice_service import voice_service
                audio = await voice_service.synthesize(text)
                await send_audio_to_computer(audio, seq)

        except Exception as e:
            logger.error(f"TTS 句子 #{seq} 失败: {e}")
        finally:
            gate.set()

    # ------------------------------------------------------------------
    # 内部路由
    # ------------------------------------------------------------------

    async def _send_voice(self, text: str) -> bool:
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
        try:
            from backend.services.agent.sources.discord_source import discord_source
            if discord_source is None or not discord_source.is_connected():
                return False
            is_private = group_id.startswith("dm_")
            return await discord_source.send_message(
                channel_id=group_id, text=text, is_private=is_private,
            )
        except Exception as e:
            logger.error(f"MessageManager Discord 发送失败: {e}")
            return False

    async def _send_qq_private(self, group_id: str, text: str) -> bool:
        try:
            from backend.api.napcat import napcat_client
            target_user_id = int(group_id.replace("private_", ""))
            return await napcat_client.send_private_message(target_user_id, text)
        except Exception as e:
            logger.error(f"MessageManager QQ 私聊发送失败: {e}")
            return False

    async def _send_qq_group(self, group_id: str, text: str) -> bool:
        try:
            from backend.api.napcat import napcat_client
            text = _AT_PATTERN.sub(r'[CQ:at,qq=\1]', text)
            return await napcat_client.send_group_message(int(group_id), text)
        except Exception as e:
            logger.error(f"MessageManager QQ 群聊发送失败: {e}")
            return False

    async def _send_computer_voice(self, text: str) -> bool:
        try:
            from backend.services.voice_service import voice_service
            from backend.routes.computer_routes import send_audio_to_computer
            audio = await voice_service.synthesize(text)
            return await send_audio_to_computer(audio)
        except Exception as e:
            logger.error(f"MessageManager 电脑 TTS 失败: {e}")
            return False


# 模块级单例
message_manager = MessageManager()
