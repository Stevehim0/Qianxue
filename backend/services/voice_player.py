"""语音播放器 -- Discord 语音频道连接、TTS 播放、语音接收与打断机制.

Phase 20 核心实现：
- VoicePlayer: 管理语音频道连接、TTS 音频队列播放、打断控制
- SilenceSegmentingSink: 基于能量的静音分割，收集用户语音段并转写

线程安全注意事项：
- AudioSink.write() 和 VoiceClient.play() 的 after 回调在独立线程运行
- 使用 asyncio.run_coroutine_threadsafe() 从线程安全调度异步操作
"""

import asyncio
import io
import logging
import struct
import time
import wave
from typing import Awaitable, Callable, List, Optional

try:
    import discord
    _DISCORD_AVAILABLE = True
except ImportError:
    discord = None  # type: ignore[assignment]
    _DISCORD_AVAILABLE = False

from backend.config.loader import settings
from backend.services.agent.message import AgentMessage
from backend.services.voice_service import voice_service

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 尝试导入 discord-ext-voice-recv
# Per D-06: 强制可用 -- connect() 时会再次检查，这里仅为类继承
# ---------------------------------------------------------------------------
try:
    from discord.ext import voice_recv as _voice_recv_module
    _AudioSinkBase = _voice_recv_module.AudioSink
except ImportError:
    _voice_recv_module = None
    # 降级基类：允许模块导入，但 connect() 时会拒绝
    _AudioSinkBase = object


# ---------------------------------------------------------------------------
# SilenceSegmentingSink -- 静音分割音频接收器
# ---------------------------------------------------------------------------


class SilenceSegmentingSink(_AudioSinkBase):
    """基于能量的静音分割音频接收器。

    继承 discord-ext-voice-recv 的 AudioSink，实现：
    - 能量检测区分语音/静音
    - 静音超时触发语音段提交
    - 持续语音检测触发打断
    - 线程安全的 write() 回调

    接收格式: 48kHz 立体声 16-bit signed LE PCM (wants_opus() = False)
    """

    SILENCE_THRESHOLD = 500        # 振幅阈值 (0-32767)
    SILENCE_DURATION = 1.0         # 静音持续时间（秒）触发语音段结束
    MIN_SPEECH_DURATION = 0.3      # 最短有效语音时长（秒）
    INTERRUPTION_DELAY = 0.3       # 持续语音确认打断延迟（秒），per D-09

    def __init__(self, voice_player: "VoicePlayer"):
        super().__init__()

        self._voice_player = voice_player
        self._bot_user_id: Optional[int] = None

        # 语音状态追踪
        self._buffer = bytearray()
        self._is_speaking = False
        self._speech_start_time: float = 0.0
        self._last_speech_time: float = 0.0

        # 打断确认追踪
        self._sustained_speech_start: float = 0.0

    def wants_opus(self) -> bool:
        """返回 False 以接收解码后的 PCM 数据（而非原始 Opus）。"""
        return False

    def write(self, user, data) -> None:
        """接收音频数据包 -- 在独立线程中调用，必须快速且线程安全。

        Args:
            user: discord.Member | discord.User | None
            data: voice_recv.VoiceData，包含 .pcm (bytes) 和 .opus (bytes)
        """
        # 过滤无效用户和 bot 自身
        if user is None:
            return
        if self._bot_user_id is not None and user.id == self._bot_user_id:
            return

        pcm = data.pcm
        if not pcm:
            return

        has_energy = self._has_speech_energy(pcm)
        now = time.monotonic()

        if has_energy:
            if not self._is_speaking:
                # 语音开始
                self._is_speaking = True
                self._speech_start_time = now
                self._sustained_speech_start = now
            else:
                # 语音持续中 -- 检查打断条件
                if (self._voice_player._is_playing
                        and self._sustained_speech_start > 0
                        and (now - self._sustained_speech_start) >= self.INTERRUPTION_DELAY):
                    self._voice_player.trigger_interruption()

            self._last_speech_time = now
            self._buffer.extend(pcm)

        elif self._is_speaking:
            # 语音后静音 -- 继续收集（包含尾部静音）
            self._buffer.extend(pcm)
            silence_duration = now - self._last_speech_time
            if silence_duration >= self.SILENCE_DURATION:
                self._flush_segment()
                # 重置打断追踪
                self._sustained_speech_start = 0.0

    def _has_speech_energy(self, pcm_bytes: bytes) -> bool:
        """检测 PCM 数据是否超过能量阈值。

        将 PCM 字节解析为 16-bit signed 样本，检查最大绝对振幅。
        """
        if len(pcm_bytes) < 2:
            return False
        try:
            sample_count = len(pcm_bytes) // 2
            samples = struct.unpack_from(f'<{sample_count}h', pcm_bytes)
            max_amplitude = max(abs(s) for s in samples)
            return max_amplitude > self.SILENCE_THRESHOLD
        except struct.error:
            return False

    def _flush_segment(self) -> None:
        """将累积的音频刷新为一个完整语音段。

        检查最短语音时长，满足条件则调度到事件循环处理。
        """
        self._is_speaking = False
        duration = time.monotonic() - self._speech_start_time

        if duration < self.MIN_SPEECH_DURATION or len(self._buffer) < 1:
            self._buffer.clear()
            return

        audio_data = bytes(self._buffer)
        self._buffer.clear()

        # 获取 Bot 的事件循环，线程安全调度异步处理
        try:
            loop = self.voice_client.client.loop
            asyncio.run_coroutine_threadsafe(
                self._voice_player._on_speech_segment(audio_data),
                loop,
            )
        except Exception as e:
            logger.error(f"调度语音段处理失败: {e}")

    def cleanup(self) -> None:
        """清理资源 -- sink 被移除时调用。"""
        if self._buffer:
            self._buffer.clear()


# ---------------------------------------------------------------------------
# VoicePlayer -- 语音播放器
# ---------------------------------------------------------------------------


class VoicePlayer:
    """语音播放器 -- Discord 语音频道连接、TTS 播放、语音接收与打断。

    职责：
    - connect(): 加入 Discord 语音频道并开始接收用户语音
    - disconnect(): 断开语音频道连接并清理资源
    - play_sentences(): 播放 MP3 音频块队列
    - trigger_interruption(): 用户说话时打断当前播放

    生命周期：由 DiscordSource 通过 set_bot() 注入 Bot 实例。
    """

    def __init__(self):
        self._connected: bool = False
        self._voice_client = None       # VoiceRecvClient 实例
        self._bot = None                # DiscordSource 的 Bot 实例
        self._bot_user_id: Optional[int] = None

        # 消息处理回调（与 DiscordSource 共享同一个 handler）
        self._message_handler: Optional[Callable[[AgentMessage], Awaitable[None]]] = None

        # 播放状态
        self._interrupted: bool = False
        self._play_queue: List[bytes] = []
        self._is_playing: bool = False

    # ------------------------------------------------------------------
    # 外部注入方法
    # ------------------------------------------------------------------

    def set_bot(self, bot) -> None:
        """存储 Bot 实例引用，记录 bot 自身 user ID 用于 sink 过滤。

        由 DiscordSource.connect() 成功后调用。
        """
        self._bot = bot
        if bot.user:
            self._bot_user_id = bot.user.id
        logger.info(f"VoicePlayer: Bot 实例已设置, bot_user_id={self._bot_user_id}")

    def set_message_handler(self, handler: Callable[[AgentMessage], Awaitable[None]]) -> None:
        """设置消息处理器回调（Brain 的入口方法）。

        与 DiscordSource 使用相同的 handler（debounce 管道）。
        """
        self._message_handler = handler
        logger.info("VoicePlayer: 消息处理器已设置")

    # ------------------------------------------------------------------
    # 连接管理
    # ------------------------------------------------------------------

    def is_connected(self) -> bool:
        """是否已连接到语音频道。"""
        return self._connected

    async def connect(self, channel_id: str) -> bool:
        """连接到 Discord 语音频道。

        前置检查：Bot 就绪、libopus 已加载、discord-ext-voice-recv 可用。
        连接后立即开始接收用户语音（通过 SilenceSegmentingSink）。

        Args:
            channel_id: Discord 语音频道 ID 字符串

        Returns:
            True 表示连接成功

        Raises:
            RuntimeError: libopus 或 discord-ext-voice-recv 不可用
        """
        # 1. 前置检查：Bot 实例
        if not self._bot or not self._bot.is_ready():
            logger.warning("VoicePlayer.connect: Bot 未就绪")
            return False

        if not _DISCORD_AVAILABLE:
            raise RuntimeError("discord.py 未安装。请运行: pip install discord.py")

        # 2. 检查 libopus
        if not discord.opus.is_loaded():
            try:
                discord.opus.load_opus('opus')
            except Exception:
                pass
            if not discord.opus.is_loaded():
                raise RuntimeError(
                    "libopus 未找到。请安装 opus.dll 并确保其在系统 PATH 中，"
                    "或放置在工作目录下。"
                )

        # 3. 检查 discord-ext-voice-recv (per D-06: 强制可用)
        try:
            from discord.ext import voice_recv
        except ImportError:
            raise RuntimeError(
                "discord-ext-voice-recv 未安装。"
                "请运行: pip install discord-ext-voice-recv"
            )

        # 4. 获取语音频道
        channel = self._bot.get_channel(int(channel_id))
        if not channel:
            logger.error(f"VoicePlayer.connect: 语音频道不存在: {channel_id}")
            return False

        # 5. 已连接则先断开
        if self._connected and self._voice_client:
            await self.disconnect()

        # 6. 连接语音频道
        try:
            self._voice_client = await channel.connect(cls=voice_recv.VoiceRecvClient)
        except Exception as e:
            logger.error(f"VoicePlayer.connect: 连接语音频道失败: {e}")
            self._voice_client = None
            return False

        # 7. 创建并附加 sink，开始接收用户语音
        sink = SilenceSegmentingSink(self)
        sink._bot_user_id = self._bot_user_id
        try:
            self._voice_client.listen(sink)
        except Exception as e:
            logger.error(f"VoicePlayer.connect: 启动语音接收失败: {e}")
            # 仍然标记为连接（可以播放，只是无法接收）
            self._connected = True
            return True

        self._connected = True
        logger.info(f"VoicePlayer: 已连接到语音频道 {channel.name} (id={channel_id})")
        return True

    async def disconnect(self) -> None:
        """断开语音频道连接，清理所有资源。"""
        if self._voice_client:
            try:
                if hasattr(self._voice_client, 'is_listening') and self._voice_client.is_listening():
                    self._voice_client.stop_listening()
            except Exception as e:
                logger.warning(f"VoicePlayer.disconnect: 停止接收失败: {e}")

            try:
                await self._voice_client.disconnect(force=True)
            except Exception as e:
                logger.warning(f"VoicePlayer.disconnect: 断开语音连接失败: {e}")

        self._connected = False
        self._voice_client = None
        self._is_playing = False
        self._interrupted = False
        self._play_queue.clear()
        logger.info("VoicePlayer: 已断开语音频道连接")

    # ------------------------------------------------------------------
    # 播放控制
    # ------------------------------------------------------------------

    async def play_sentences(self, audio_chunks: List[bytes]) -> bool:
        """播放 MP3 音频块队列。

        将音频块加入播放队列，按顺序逐个播放。
        每个音频块通过 FFmpegOpusAudio 转换为 Opus 格式播放（最低延迟）。

        Args:
            audio_chunks: MP3 bytes 列表，每个元素是一句话的 TTS 音频

        Returns:
            True 表示开始播放（已入队列）
        """
        if not self._connected or not self._voice_client:
            return False

        self._play_queue = list(audio_chunks)
        self._is_playing = True
        self._interrupted = False

        # 开始播放第一个块
        self._play_next_chunk()
        return True

    def _play_next_chunk(self) -> None:
        """播放队列中的下一个音频块。

        由 _on_play_done 回调链式调用，顺序播放所有队列中的块。
        """
        if self._interrupted or not self._play_queue:
            self._is_playing = False
            return

        chunk = self._play_queue.pop(0)

        try:
            # D-12: FFmpegOpusAudio + pipe=True 最低延迟 (research R-03)
            bio = io.BytesIO(chunk)
            source = discord.FFmpegOpusAudio(bio, pipe=True)
            self._voice_client.play(source, after=self._on_play_done)
        except Exception as e:
            logger.error(f"VoicePlayer._play_next_chunk: 播放失败: {e}")
            self._is_playing = False

    def _on_play_done(self, error) -> None:
        """播放完成回调 -- 在独立线程中调用。

        自然完成时播放下一个块；打断时不继续播放。
        """
        if self._interrupted:
            self._is_playing = False
            return

        if error:
            logger.error(f"VoicePlayer._on_play_done: 播放错误: {error}")
            self._is_playing = False
            return

        # 自然完成，播放下一个块
        self._play_next_chunk()

    # ------------------------------------------------------------------
    # 打断机制
    # ------------------------------------------------------------------

    def trigger_interruption(self) -> None:
        """打断当前 TTS 播放 -- 由 SilenceSegmentingSink.write() 调用。

        线程安全：仅操作简单标志和方法，不做异步操作。

        Per D-09/D-10/D-11:
        - 停止当前播放（stop_playing 只停播放，不停接收）
        - 清空播放队列
        - 设置打断标志防止队列继续
        """
        if not self._voice_client:
            return

        try:
            if hasattr(self._voice_client, 'is_playing') and self._voice_client.is_playing():
                self._interrupted = True
                self._play_queue.clear()
                # R-05: stop_playing() 只停止播放，保持语音接收
                self._voice_client.stop_playing()
                logger.info("VoicePlayer: TTS 播放被用户语音打断")
        except Exception as e:
            logger.error(f"VoicePlayer.trigger_interruption: 打断失败: {e}")

    # ------------------------------------------------------------------
    # 语音段处理
    # ------------------------------------------------------------------

    async def _on_speech_segment(self, audio_data: bytes) -> None:
        """处理一个完整的用户语音段。

        由 SilenceSegmentingSink 通过 run_coroutine_threadsafe 调度到事件循环。

        流程：48kHz 立体声 PCM -> WAV bytes -> VoiceService.transcribe() -> AgentMessage
        """
        if not self._message_handler:
            logger.warning("VoicePlayer._on_speech_segment: 消息处理器未设置，丢弃语音段")
            return

        try:
            # 将 48kHz 立体声 PCM 包装为 WAV bytes
            # VoiceService._convert_to_pcm() 会自动重采样为 16kHz mono
            with io.BytesIO() as wav_buffer:
                with wave.open(wav_buffer, 'wb') as wf:
                    wf.setnchannels(2)
                    wf.setsampwidth(2)
                    wf.setframerate(48000)
                    wf.writeframes(audio_data)
                wav_bytes = wav_buffer.getvalue()

            # 转写
            text = await voice_service.transcribe(wav_bytes)
            if not text or not text.strip():
                return

            # 创建 AgentMessage
            channel_id = "voice_unknown"
            if self._voice_client and hasattr(self._voice_client, 'channel') and self._voice_client.channel:
                channel_id = str(self._voice_client.channel.id)

            agent_msg = AgentMessage(
                source="discord",
                group_id=f"voice_{channel_id}",
                user_id="discord_voice",
                sender_nickname="语音频道用户",
                content=text,
                raw_message="discord:voice",
                is_mentioned=True,   # 语音频道消息始终视为对 bot 说话
                is_private=False,
                priority=10,
            )

            await self._message_handler(agent_msg)
            logger.info(f"VoicePlayer: 语音段转写完成: {text[:80]}")

        except Exception as e:
            logger.error(f"VoicePlayer._on_speech_segment: 处理语音段失败: {e}", exc_info=True)


# Module-level singleton
voice_player = VoicePlayer()
