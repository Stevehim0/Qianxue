"""语音依赖健康检查模块.

在 backend main.py lifespan 中调用，检查 5 项语音依赖：
- FunASR WebSocket (D-07)
- FFmpeg (D-08)
- Opus (D-09)
- Edge-TTS (D-10)
- discord-ext-voice-recv (D-11)

所有检查失败仅 WARNING，不阻塞启动 (D-04)。
"""

import asyncio
import importlib.util
import logging
from typing import Tuple

import websockets

from backend.config import settings

logger = logging.getLogger(__name__)


async def check_funasr(url: str, timeout: float = 5.0) -> Tuple[bool, str]:
    """检查 FunASR WebSocket 连接可用性 (D-07)."""
    try:
        async with websockets.connect(url, timeout=timeout):
            return (True, "OK")
    except Exception as e:
        return (False, f"不可用: {url} ({e})")


async def check_ffmpeg(timeout: float = 5.0) -> Tuple[bool, str]:
    """检查 FFmpeg 二进制可用性 (D-08)."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(proc.wait(), timeout=timeout)
        if proc.returncode == 0:
            return (True, "OK")
        return (False, f"ffmpeg 返回非零退出码: {proc.returncode}")
    except FileNotFoundError:
        return (False, "未找到 ffmpeg。请安装: https://ffmpeg.org/download.html")
    except asyncio.TimeoutError:
        return (False, "ffmpeg 检查超时")
    except Exception as e:
        return (False, f"ffmpeg 检查失败: {e}")


async def check_opus() -> Tuple[bool, str]:
    """检查 Opus 库可用性 (D-09).

    使用延迟导入 discord，避免模块加载时依赖。
    """
    try:
        import discord
        if discord.opus.is_loaded():
            return (True, "OK")
        try:
            discord.opus.load_opus("opus")
        except Exception:
            pass
        if discord.opus.is_loaded():
            return (True, "OK")
        return (False, "libopus 未加载。请下载 opus.dll 放到工作目录或系统 PATH")
    except Exception as e:
        return (False, str(e))


async def check_edge_tts(voice: str, timeout: float = 10.0) -> Tuple[bool, str]:
    """检查 Edge-TTS 合成能力 (D-10).

    使用延迟导入 edge_tts，避免模块加载时依赖。
    """
    try:
        import edge_tts
        communicate = edge_tts.Communicate("测试", voice)

        async def _check():
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    return True
            return False

        found = await asyncio.wait_for(_check(), timeout=timeout)
        if found:
            return (True, "OK")
        return (False, "Edge-TTS 未返回音频数据")
    except asyncio.TimeoutError:
        return (False, "Edge-TTS 检查超时")
    except Exception as e:
        return (False, f"Edge-TTS 不可用: {e}")


def check_voice_recv() -> Tuple[bool, str]:
    """检查 discord-ext-voice-recv 包可用性 (D-11)."""
    spec = importlib.util.find_spec("discord.ext.voice_recv")
    if spec is not None:
        return (True, "OK")
    return (False, "未安装。请运行: pip install discord-ext-voice-recv")


async def check_voice_dependencies() -> dict:
    """编排所有语音依赖检查，返回结果 dict。

    每项检查结果通过 logger.info/warning 输出，
    格式: "[语音依赖] {name}: {OK/WARNING} -- {detail}" (D-06)。

    返回:
        dict[str, tuple[bool, str]]: 各检查项结果
    """
    results = {}

    # 1. FunASR
    ok, msg = await check_funasr(settings.voice.funasr_websocket_url)
    results["funasr"] = (ok, msg)
    _log_result("FunASR", ok, msg)

    # 2. FFmpeg
    ok, msg = await check_ffmpeg()
    results["ffmpeg"] = (ok, msg)
    _log_result("FFmpeg", ok, msg)

    # 3. Opus
    ok, msg = await check_opus()
    results["opus"] = (ok, msg)
    _log_result("Opus", ok, msg)

    # 4. Edge-TTS
    ok, msg = await check_edge_tts(settings.voice.tts_default_voice)
    results["edge_tts"] = (ok, msg)
    _log_result("Edge-TTS", ok, msg)

    # 5. voice_recv
    ok, msg = check_voice_recv()
    results["voice_recv"] = (ok, msg)
    _log_result("voice_recv", ok, msg)

    return results


def _log_result(name: str, ok: bool, detail: str):
    """统一格式输出检查结果 (D-06)."""
    if ok:
        logger.info(f"[语音依赖] {name}: OK -- {detail}")
    else:
        logger.warning(f"[语音依赖] {name}: WARNING -- {detail}")
