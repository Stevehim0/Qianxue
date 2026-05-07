"""voice_health.py 单元测试.

5 项语音依赖检查的 mock 测试：
- FunASR WebSocket 连接
- FFmpeg 二进制可用性
- Opus 库加载
- Edge-TTS 合成
- discord-ext-voice-recv 包
"""

import asyncio
import pytest
import pytest_asyncio
from unittest.mock import patch, MagicMock, AsyncMock


# ---------------------------------------------------------------------------
# check_funasr 测试
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_check_funasr_ok():
    """mock websockets.connect 成功 -> 返回结果包含 funasr=True"""
    with patch("backend.services.voice_health.websockets") as mock_ws:
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=AsyncMock())
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_ws.connect.return_value = mock_cm

        from backend.services.voice_health import check_funasr
        ok, msg = await check_funasr("ws://localhost:10095")
        assert ok is True
        assert msg == "OK"


@pytest.mark.asyncio
async def test_check_funasr_fail():
    """mock websockets.connect 抛异常 -> 返回结果包含 funasr=False"""
    with patch("backend.services.voice_health.websockets") as mock_ws:
        mock_ws.connect.side_effect = Exception("Connection refused")

        from backend.services.voice_health import check_funasr
        ok, msg = await check_funasr("ws://localhost:10095")
        assert ok is False
        assert "不可用" in msg


# ---------------------------------------------------------------------------
# check_ffmpeg 测试
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_check_ffmpeg_ok():
    """mock subprocess 返回 returncode=0 -> 返回结果包含 ffmpeg=True"""
    mock_proc = MagicMock()
    mock_proc.wait = AsyncMock(return_value=0)
    mock_proc.returncode = 0

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        from backend.services.voice_health import check_ffmpeg
        ok, msg = await check_ffmpeg()
        assert ok is True
        assert msg == "OK"


@pytest.mark.asyncio
async def test_check_ffmpeg_fail():
    """mock FileNotFoundError -> 返回结果包含 ffmpeg=False"""
    with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError):
        from backend.services.voice_health import check_ffmpeg
        ok, msg = await check_ffmpeg()
        assert ok is False
        assert "未找到" in msg or "ffmpeg" in msg


# ---------------------------------------------------------------------------
# check_opus 测试
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_check_opus_ok():
    """mock discord.opus.is_loaded() 返回 True -> 返回结果包含 opus=True"""
    with patch("backend.services.voice_health.discord") as mock_discord:
        mock_discord.opus.is_loaded.return_value = True

        from backend.services.voice_health import check_opus
        ok, msg = await check_opus()
        assert ok is True
        assert msg == "OK"


@pytest.mark.asyncio
async def test_check_opus_fail():
    """mock discord.opus.is_loaded() 返回 False 且 load_opus 失败 -> 返回结果包含 opus=False"""
    with patch("backend.services.voice_health.discord") as mock_discord:
        mock_discord.opus.is_loaded.return_value = False
        mock_discord.opus.load_opus.side_effect = Exception("not found")

        from backend.services.voice_health import check_opus
        ok, msg = await check_opus()
        assert ok is False
        assert "libopus" in msg or "opus" in msg.lower()


# ---------------------------------------------------------------------------
# check_edge_tts 测试
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_check_edgetts_ok():
    """mock edge_tts.Communicate.stream() 返回音频 -> 返回结果包含 edge_tts=True"""
    async def mock_stream():
        yield {"type": "audio", "data": b"fake_audio_bytes"}

    mock_communicate = MagicMock()
    mock_communicate.stream.return_value = mock_stream()

    with patch("backend.services.voice_health.edge_tts") as mock_etts:
        mock_etts.Communicate.return_value = mock_communicate

        from backend.services.voice_health import check_edge_tts
        ok, msg = await check_edge_tts("zh-CN-XiaoxiaoNeural")
        assert ok is True
        assert msg == "OK"


@pytest.mark.asyncio
async def test_check_edgetts_fail():
    """mock 抛异常 -> 返回结果包含 edge_tts=False"""
    with patch("backend.services.voice_health.edge_tts") as mock_etts:
        mock_etts.Communicate.side_effect = Exception("Network error")

        from backend.services.voice_health import check_edge_tts
        ok, msg = await check_edge_tts("zh-CN-XiaoxiaoNeural")
        assert ok is False
        assert "Edge-TTS" in msg or "不可用" in msg


# ---------------------------------------------------------------------------
# check_voice_recv 测试
# ---------------------------------------------------------------------------

def test_check_voice_recv_ok():
    """mock import 成功 -> 返回结果包含 voice_recv=True"""
    with patch("importlib.util.find_spec", return_value=MagicMock()):
        from backend.services.voice_health import check_voice_recv
        ok, msg = check_voice_recv()
        assert ok is True
        assert msg == "OK"


def test_check_voice_recv_fail():
    """mock ImportError -> 返回结果包含 voice_recv=False"""
    with patch("importlib.util.find_spec", return_value=None):
        from backend.services.voice_health import check_voice_recv
        ok, msg = check_voice_recv()
        assert ok is False
        assert "未安装" in msg or "voice-recv" in msg
