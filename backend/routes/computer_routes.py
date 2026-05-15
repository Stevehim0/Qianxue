"""本地电脑 WebSocket 端点 — 千雪的"家"入口."""

import asyncio
import base64
import json
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)
router = APIRouter(tags=["computer"])

# 模块级 WebSocket 连接引用（单例模式，同 voice_player）
_active_ws: Optional[WebSocket] = None
_ws_lock = asyncio.Lock()

# 语音开关状态（前端同步过来）
_voice_enabled: bool = False

# 连接时间追踪
_connected_since: Optional[datetime] = None

# 消息处理回调 — 由 main.py 在启动时注入
_message_handler = None


def set_message_handler(handler):
    """设置消息处理回调（进入 debounce 队列的入口）."""
    global _message_handler
    _message_handler = handler


async def send_to_computer(text: str) -> bool:
    """向前端推送一条文本句子."""
    if _active_ws is None:
        return False
    try:
        await _active_ws.send_json({"type": "sentence", "text": text})
        return True
    except Exception as e:
        logger.warning(f"推送文本到电脑前端失败: {e}")
        return False


async def send_token_to_computer(token: str) -> bool:
    """向前端推送单个 token（逐字显示）."""
    if _active_ws is None:
        return False
    try:
        await _active_ws.send_json({"type": "token", "text": token})
        return True
    except Exception as e:
        logger.warning(f"推送 token 到电脑前端失败: {e}")
        return False


async def send_audio_to_computer(mp3_bytes: bytes, seq: int = 0) -> bool:
    """向前端推送一段完整音频（base64 编码，兼容 EdgeTTS）."""
    if _active_ws is None:
        return False
    try:
        b64 = base64.b64encode(mp3_bytes).decode("ascii")
        await _active_ws.send_json({"type": "audio", "seq": seq, "data": b64})
        return True
    except Exception as e:
        logger.warning(f"推送音频到电脑前端失败: {e}")
        return False


async def send_audio_begin(seq: int, text: str) -> bool:
    """通知前端：第 seq 句开始 TTS 合成."""
    if _active_ws is None:
        return False
    try:
        await _active_ws.send_json({"type": "audio_begin", "seq": seq, "text": text})
        return True
    except Exception as e:
        logger.warning(f"推送 audio_begin 失败: {e}")
        return False


async def send_audio_chunk(seq: int, idx: int, pcm_bytes: bytes) -> bool:
    """推送一个 PCM 音频块（24kHz 16-bit mono，~20ms）."""
    if _active_ws is None:
        return False
    try:
        b64 = base64.b64encode(pcm_bytes).decode("ascii")
        await _active_ws.send_json({"type": "audio_chunk", "seq": seq, "idx": idx, "data": b64})
        return True
    except Exception as e:
        logger.warning(f"推送 audio_chunk 失败: {e}")
        return False


async def send_audio_end(seq: int) -> bool:
    """通知前端：第 seq 句 TTS 合成完毕."""
    if _active_ws is None:
        return False
    try:
        await _active_ws.send_json({"type": "audio_end", "seq": seq})
        return True
    except Exception as e:
        logger.warning(f"推送 audio_end 失败: {e}")
        return False


async def send_done_to_computer() -> bool:
    """通知前端当前回复已结束."""
    if _active_ws is None:
        return False
    try:
        await _active_ws.send_json({"type": "done"})
        return True
    except Exception:
        return False


def is_connected() -> bool:
    """是否有活跃的电脑前端连接."""
    return _active_ws is not None


def is_voice_enabled() -> bool:
    """前端语音播放是否开启."""
    return _voice_enabled


def get_computer_status() -> dict:
    """获取电脑前端连接状态，供千雪感知使用。"""
    if _active_ws is None:
        return {"online": False, "connected_since": None, "duration": None}
    now = datetime.now()
    duration = (now - _connected_since).total_seconds() if _connected_since else 0
    hours = int(duration // 3600)
    minutes = int((duration % 3600) // 60)
    if hours > 0:
        duration_str = f"{hours}小时{minutes}分钟"
    else:
        duration_str = f"{minutes}分钟"
    return {
        "online": True,
        "connected_since": _connected_since.strftime("%H:%M") if _connected_since else None,
        "duration": duration_str,
    }


# ------------------------------------------------------------------
# 语音输入消息处理
# ------------------------------------------------------------------


def to_ms(t_start: float, t_end: float) -> int:
    """两个 monotonic 时间戳之间的毫秒数。"""
    return int((t_end - t_start) * 1000)


async def _handle_voice_start() -> None:
    """处理 voice_start: 打断当前 TTS + 开始新语音输入."""
    from backend.services.voice_manager import voice_manager

    # 如果 AI 正在说话，打断
    if voice_manager.computer_voice_active:
        await voice_manager.interrupt_computer()

    voice_manager.start_computer_voice()
    await _send_if_active({"type": "voice_ready"})


async def _handle_audio_input(data_b64: str) -> None:
    """处理 audio_input: 缓冲前端发来的 PCM chunk."""
    from backend.services.voice_manager import voice_manager
    try:
        pcm = base64.b64decode(data_b64)
        voice_manager.feed_computer_audio(pcm)
    except Exception as e:
        logger.warning(f"audio_input 解码失败: {e}")


async def _handle_voice_end(data_b64: Optional[str] = None) -> None:
    """处理 voice_end: 结束语音输入，转写，发送给 Brain."""
    import time
    from backend.services.voice_manager import voice_manager

    t0 = time.monotonic()

    # voice_end 携带完整音频：清空之前的 chunk 缓冲，只用完整音频（避免重复）
    if data_b64:
        try:
            pcm = base64.b64decode(data_b64)
            voice_manager._computer_audio_buffer.clear()
            voice_manager.feed_computer_audio(pcm)
        except Exception as e:
            logger.warning(f"voice_end 音频解码失败: {e}")

    t_decode = time.monotonic()
    text = await voice_manager.end_computer_voice()
    t_stt = time.monotonic()

    if not text or not text.strip():
        logger.info(f"[VOICE_PERF] decode={to_ms(t0,t_decode)}ms stt={to_ms(t_decode,t_stt)}ms → 空结果，丢弃")
        return

    logger.info(f"[VOICE_PERF] decode={to_ms(t0,t_decode)}ms stt={to_ms(t_decode,t_stt)}ms total={to_ms(t0,t_stt)}ms → {text[:60]}")

    # 通知前端转写结果
    await _send_if_active({"type": "stt_final", "text": text})

    # 构建 AgentMessage 并发送到对话管道
    if _message_handler is None:
        logger.warning("消息处理器未初始化，丢弃语音转写")
        return

    from backend.services.agent.sources.computer_source import build_computer_message
    agent_msg = build_computer_message(text)
    await _message_handler(agent_msg)


async def _handle_voice_cancel() -> None:
    """处理 voice_cancel: 取消当前语音输入."""
    from backend.services.voice_manager import voice_manager
    voice_manager.cancel_computer_voice()


async def _send_if_active(msg: dict) -> None:
    """向前端发送 JSON 消息（如果连接活跃）."""
    if _active_ws is not None:
        try:
            await _active_ws.send_json(msg)
        except Exception:
            pass


# ------------------------------------------------------------------
# WebSocket 端点
# ------------------------------------------------------------------

@router.websocket("/ws/computer")
async def computer_websocket(websocket: WebSocket):
    """本地电脑聊天 WebSocket.

    接收协议:
        {"type": "message", "content": "你好"}
        {"type": "set_voice", "enabled": true/false}
        {"type": "voice_start"}                          // 全双工: 开始语音输入
        {"type": "audio_input", "data": "<base64 PCM>"}  // 全双工: 音频 chunk
        {"type": "voice_end", "data": "<base64 PCM>"}    // 全双工: 结束语音 + 完整音频
        {"type": "voice_cancel"}                         // 全双工: 取消语音输入
        {"type": "ping"}

    推送协议:
        {"type": "token", "text": "你"}
        {"type": "sentence", "text": "你好呀~"}
        {"type": "audio_begin", "seq": 0, "text": "你好呀~"}
        {"type": "audio_chunk", "seq": 0, "idx": 0, "data": "<base64 pcm>"}
        {"type": "audio_end", "seq": 0}
        {"type": "audio", "seq": 0, "data": "<base64 mp3>"}  # EdgeTTS 兼容
        {"type": "done"}
        {"type": "pong"}
        {"type": "voice_ready"}                          // 全双工: STT 就绪
        {"type": "stt_final", "text": "你好"}            // 全双工: 转写结果
        {"type": "interrupt_ack"}                        // 全双工: 打断确认
        {"type": "error", "message": "..."}
    """
    global _active_ws, _voice_enabled, _connected_since

    await websocket.accept()
    logger.info("电脑前端 WebSocket 已连接")

    async with _ws_lock:
        _active_ws = websocket
        _connected_since = datetime.now()

    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "无效的 JSON"})
                continue

            msg_type = msg.get("type", "")

            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})

            elif msg_type == "set_voice":
                _voice_enabled = bool(msg.get("enabled", False))
                logger.info(f"电脑前端语音状态: {_voice_enabled}")

            elif msg_type == "message":
                content = msg.get("content", "").strip()
                if not content:
                    continue

                if _message_handler is None:
                    await websocket.send_json({"type": "error", "message": "消息处理器未初始化"})
                    continue

                from backend.services.agent.sources.computer_source import build_computer_message
                agent_msg = build_computer_message(content)
                await _message_handler(agent_msg)

            elif msg_type == "voice_start":
                await _handle_voice_start()

            elif msg_type == "audio_input":
                await _handle_audio_input(msg.get("data", ""))

            elif msg_type == "voice_end":
                await _handle_voice_end(msg.get("data"))

            elif msg_type == "voice_cancel":
                await _handle_voice_cancel()

            else:
                await websocket.send_json({"type": "error", "message": f"未知消息类型: {msg_type}"})

    except WebSocketDisconnect:
        logger.info("电脑前端 WebSocket 已断开")
    except Exception as e:
        logger.error(f"电脑 WebSocket 异常: {e}", exc_info=True)
    finally:
        async with _ws_lock:
            if _active_ws is websocket:
                _active_ws = None
                _connected_since = None
        _voice_enabled = False
        logger.info("电脑前端连接已清理")
