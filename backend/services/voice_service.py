"""Voice服务模块 - ASR (FunASR) + TTS (可切换后端) + 音频格式转换."""

import logging
import io
import struct
import wave
import asyncio
from typing import Optional

import httpx
import websockets

from backend.db_config import config_manager
from backend.config.loader import settings


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class VoiceError(Exception):
    """语音服务异常 -- ASR/TTS 失败时抛出，不返回 None"""
    pass


class VoiceService:
    """Voice 服务 - 语音识别 (FunASR) + 语音合成 (可切换 TTS 后端)"""

    def __init__(self):
        self.config = config_manager.get_voice_config()
        self.client = httpx.AsyncClient(timeout=120.0)
        self._tts = self._init_tts_backend()

    def _init_tts_backend(self):
        """根据配置选择 TTS 后端."""
        backend = settings.voice.tts_backend
        if backend == "qwen3":
            from .tts_qwen3 import Qwen3TTSBackend
            logger.info(f"TTS 后端: Qwen3-TTS ({settings.voice.qwen3_tts_url})")
            return Qwen3TTSBackend(
                api_url=settings.voice.qwen3_tts_url,
                model=settings.voice.qwen3_tts_model,
                voice=settings.voice.qwen3_tts_voice,
                timeout=settings.voice.tts_timeout,
            )
        else:
            from .tts_edge import EdgeTTSBackend
            logger.info(f"TTS 后端: Edge TTS (voice={settings.voice.tts_default_voice})")
            return EdgeTTSBackend(
                default_voice=settings.voice.tts_default_voice,
                rate=settings.voice.tts_rate,
                volume=settings.voice.tts_volume,
                timeout=settings.voice.tts_timeout,
            )

    def reload_config(self):
        """重新加载配置（从 config_manager 刷新）."""
        self.config = config_manager.get_voice_config()
        self._tts = self._init_tts_backend()
        logger.info("Voice配置已重新加载")

    # ------------------------------------------------------------------
    # 音频格式转换
    # ------------------------------------------------------------------

    def _detect_format(self, audio_data: bytes) -> str:
        """检测音频数据格式（基于文件头魔数）"""
        if audio_data[:4] == b'RIFF':
            return 'wav'
        if audio_data[:2] in (b'\xff\xfb', b'\xff\xf3', b'\xff\xf2'):
            return 'mp3'
        if audio_data[:4] == b'OggS':
            return 'ogg'
        return 'pcm'

    async def _convert_to_pcm(self, audio_data: bytes) -> bytes:
        """将音频数据转换为 16kHz mono 16-bit PCM bytes.

        支持输入格式: WAV, MP3, OGG, raw PCM.
        返回: 16-bit signed little-endian, 16000 Hz, mono PCM bytes.
        """
        fmt = self._detect_format(audio_data)
        target_rate = settings.voice.audio_target_sample_rate
        target_channels = settings.voice.audio_target_channels

        # WAV: 直接用 wave 模块提取 PCM
        if fmt == 'wav':
            try:
                pcm_data, sample_rate, channels = self._extract_wav_pcm(audio_data)
                if sample_rate != target_rate or channels != target_channels:
                    pcm_data = self._resample_pcm(pcm_data, sample_rate, target_rate, channels, target_channels)
                return pcm_data
            except Exception as e:
                logger.warning(f"WAV解析失败，尝试ffmpeg: {e}")
                return await self._ffmpeg_convert(audio_data)

        # MP3 / OGG: 必须用 ffmpeg
        if fmt in ('mp3', 'ogg'):
            return await self._ffmpeg_convert(audio_data)

        # 假定 raw PCM (16-bit signed LE)，直接返回
        return audio_data

    def _extract_wav_pcm(self, audio_data: bytes):
        """从 WAV 数据中提取原始 PCM，返回 (pcm_bytes, sample_rate, channels)."""
        with wave.open(io.BytesIO(audio_data), 'rb') as wf:
            channels = wf.getnchannels()
            sample_width = wf.getsampwidth()
            sample_rate = wf.getframerate()
            n_frames = wf.getnframes()
            raw = wf.readframes(n_frames)

        # 转换为 16-bit 如果不是
        if sample_width == 2:
            pcm = raw
        elif sample_width == 1:
            # 8-bit unsigned -> 16-bit signed
            pcm = b''
            for byte in raw:
                sample = (byte - 128) * 256
                pcm += struct.pack('<h', sample)
        elif sample_width == 4:
            # 32-bit -> 16-bit
            pcm = b''
            for i in range(0, len(raw), 4):
                sample = struct.unpack('<i', raw[i:i + 4])[0]
                pcm += struct.pack('<h', sample >> 16)
        else:
            pcm = raw

        return pcm, sample_rate, channels

    @staticmethod
    def _resample_pcm(pcm_data: bytes, orig_rate: int, target_rate: int,
                      orig_channels: int, target_channels: int) -> bytes:
        """简单的 PCM 重采样（线性插值），处理采样率和声道数转换。"""
        import array

        samples = array.array('h', pcm_data)

        # 先处理声道: 立体声 -> 单声道（取平均）
        if orig_channels > target_channels:
            mono = array.array('h')
            frame_count = len(samples) // orig_channels
            for i in range(frame_count):
                total = sum(samples[i * orig_channels + c] for c in range(orig_channels))
                mono.append(total // orig_channels)
            samples = mono
        elif orig_channels < target_channels:
            # 单声道 -> 立体声（复制）
            stereo = array.array('h')
            for s in samples:
                stereo.append(s)
                stereo.append(s)
            samples = stereo

        # 重采样（线性插值）
        if orig_rate != target_rate:
            ratio = target_rate / orig_rate
            new_len = int(len(samples) * ratio)
            resampled = array.array('h')
            for i in range(new_len):
                src_pos = i / ratio
                src_idx = int(src_pos)
                frac = src_pos - src_idx
                if src_idx + 1 < len(samples):
                    val = int(samples[src_idx] * (1 - frac) + samples[src_idx + 1] * frac)
                else:
                    val = samples[min(src_idx, len(samples) - 1)]
                resampled.append(max(-32768, min(32767, val)))
            samples = resampled

        return samples.tobytes()

    async def _ffmpeg_convert(self, audio_data: bytes) -> bytes:
        """用 ffmpeg 将音频转换为 16kHz mono 16-bit PCM."""
        target_rate = settings.voice.audio_target_sample_rate
        target_channels = settings.voice.audio_target_channels

        try:
            proc = await asyncio.create_subprocess_exec(
                'ffmpeg', '-i', 'pipe:0', '-f', 's16le', '-acodec', 'pcm_s16le',
                '-ar', str(target_rate), '-ac', str(target_channels), 'pipe:1',
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate(input=audio_data)
            if proc.returncode != 0:
                err_msg = stderr.decode('utf-8', errors='replace')[:200]
                raise VoiceError(f"ffmpeg转换失败 (code={proc.returncode}): {err_msg}")
            return stdout
        except FileNotFoundError:
            raise VoiceError(
                "ffmpeg未安装，无法转换此音频格式。请安装ffmpeg: "
                "https://ffmpeg.org/download.html"
            )

    # ------------------------------------------------------------------
    # ASR: 语音转文字 (FunASR WebSocket)
    # ------------------------------------------------------------------

    async def transcribe(self, audio_source) -> str:
        """语音识别 -- 将音频转为文字.

        Args:
            audio_source: URL 字符串（下载后转换）或 bytes（直接转换）

        Returns:
            转写后的文字字符串

        Raises:
            VoiceError: ASR 失败时抛出
        """
        # 1. 获取音频 bytes
        if isinstance(audio_source, str) and (audio_source.startswith('http://') or audio_source.startswith('https://')):
            try:
                resp = await self.client.get(audio_source, timeout=settings.voice.funasr_timeout)
                if resp.status_code != 200:
                    raise VoiceError(f"下载音频失败: HTTP {resp.status_code}")
                audio_bytes = resp.content
            except VoiceError:
                raise
            except Exception as e:
                raise VoiceError(f"下载音频失败: {e}")
        elif isinstance(audio_source, bytes):
            audio_bytes = audio_source
        else:
            raise VoiceError(f"不支持的音频源类型: {type(audio_source)}")

        # 2. 转换为 PCM
        pcm_data = await self._convert_to_pcm(audio_bytes)

        # 3. 连接 FunASR WebSocket 并发送
        ws_url = settings.voice.funasr_websocket_url
        timeout = settings.voice.funasr_timeout

        try:
            result_text = await asyncio.wait_for(
                self._send_to_funasr(ws_url, pcm_data),
                timeout=timeout
            )
            if not result_text:
                logger.info("ASR转写返回空结果（可能是噪音或静音）")
                return ""
            logger.info(f"ASR转写成功: {result_text[:100]}")
            return result_text
        except VoiceError:
            raise
        except asyncio.TimeoutError:
            raise VoiceError(f"ASR超时 ({timeout}秒)")
        except Exception as e:
            raise VoiceError(f"ASR失败: {e}")

    async def _send_to_funasr(self, ws_url: str, pcm_data: bytes) -> str:
        """通过 FunASR WebSocket 协议发送音频并获取转写结果。"""
        import json

        # 诊断：检查重采样后 PCM 振幅
        pcm_samples = len(pcm_data) // 2
        if pcm_samples > 0:
            import struct as _struct
            raw = _struct.unpack_from(f'<{pcm_samples}h', pcm_data)
            max_amp = max(abs(s) for s in raw)
            mean_amp = sum(abs(s) for s in raw) / len(raw)
            logger.info(f"FunASR: PCM诊断 size={len(pcm_data)} samples={pcm_samples} max_amp={max_amp} mean_amp={mean_amp:.1f}")

        async with websockets.connect(ws_url) as ws:
            # FunASR C++ server 要求第一条消息为 JSON 配置
            # 2pass 模式：先返回在线（快速）结果，再返回离线（准确）结果
            await ws.send(json.dumps({
                "mode": "2pass",
                "chunk_size": [5, 10, 5],
                "chunk_interval": 10,
                "wav_name": "audio",
                "is_speaking": True,
            }))

            # 分块发送音频数据
            chunk_size = 4096
            for i in range(0, len(pcm_data), chunk_size):
                chunk = pcm_data[i:i + chunk_size]
                await ws.send(chunk)

            # 发送结束标记 — FunASR 用 is_speaking: false 通知音频结束
            await ws.send(json.dumps({"is_speaking": False}))

            # 接收结果 — 2pass 模式返回多次，取最终离线结果
            result_text = ""
            msg_count = 0
            async for message in ws:
                try:
                    data = json.loads(message)
                    msg_count += 1
                    text = data.get("text", "")
                    mode = data.get("mode", "")
                    is_final = data.get("is_final", False)
                    logger.info(f"FunASR: 收到消息#{msg_count} mode={mode} is_final={is_final} text='{text[:100]}'")
                    if text:
                        result_text = text
                    # 离线模式返回的是最终结果
                    if mode == "offline":
                        break
                    if is_final:
                        break
                except json.JSONDecodeError:
                    continue

            logger.info(f"FunASR: 共收到{msg_count}条消息，最终结果='{result_text[:100]}'")
            return result_text

    # ------------------------------------------------------------------
    # TTS: 文字转语音（委托给可配置的后端）
    # ------------------------------------------------------------------

    async def synthesize(self, text: str, voice: Optional[str] = None) -> bytes:
        """语音合成 -- 将文字转为音频.

        委托给当前配置的 TTS 后端（Edge TTS）。
        Edge TTS 返回 MP3 bytes。

        Raises:
            VoiceError: TTS 失败时抛出
        """
        timeout = settings.voice.tts_timeout
        try:
            audio_bytes = await asyncio.wait_for(
                self._tts.synthesize(text, voice),
                timeout=timeout
            )
            if not audio_bytes:
                raise VoiceError("TTS生成空音频")
            logger.info(f"TTS合成成功: {len(audio_bytes)} bytes")
            return audio_bytes
        except VoiceError:
            raise
        except asyncio.TimeoutError:
            raise VoiceError(f"TTS超时 ({timeout}秒)")
        except Exception as e:
            raise VoiceError(f"TTS失败: {e}")

    async def synthesize_chunks(self, text: str, voice: Optional[str] = None):
        """流式 TTS — 边合成边 yield 音频 chunk.

        委托给当前配置的 TTS 后端。
        Edge TTS yield MP3 chunk。
        """
        async for chunk in self._tts.synthesize_stream(text, voice):
            yield chunk

    async def synthesize_stream(self, sentences: list[str], voice: Optional[str] = None) -> list[bytes]:
        """流式 TTS — 逐句合成，返回句子级音频列表。"""
        results = []
        for sentence in sentences:
            if not sentence.strip():
                continue
            try:
                audio = await self.synthesize(sentence, voice)
                results.append(audio)
            except VoiceError as e:
                logger.warning(f"流式TTS跳过句子: {sentence[:30]}... 错误: {e}")
        return results

    async def synthesize_stream_pcm(self, text: str, voice: Optional[str] = None):
        """流式 TTS — yield 原始 PCM chunks（24kHz 16-bit mono LE）.

        委托给 TTS 后端的 synthesize_stream_pcm()。
        """
        async for chunk in self._tts.synthesize_stream_pcm(text, voice):
            yield chunk


# 模块级单例
voice_service = VoiceService()
