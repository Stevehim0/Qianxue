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
    # 格式化时长
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


@router.websocket("/ws/computer")
async def computer_websocket(websocket: WebSocket):
    """本地电脑聊天 WebSocket.

    接收协议:
        {"type": "message", "content": "你好"}
        {"type": "set_voice", "enabled": true/false}
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
        {"type": "error", "message": "..."}
    """
    global _active_ws, _voice_enabled, _connected_since

    await websocket.accept()
    logger.info("电脑前端 WebSocket 已连接")

    async with _ws_lock:
        # 如果已有连接，替换（旧连接由前端自行断开）
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
