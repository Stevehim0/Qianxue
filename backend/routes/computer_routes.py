"""本地电脑 WebSocket 端点 — 千雪的"家"入口."""

import asyncio
import base64
import json
import logging
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)
router = APIRouter(tags=["computer"])

# 模块级 WebSocket 连接引用（单例模式，同 voice_player）
_active_ws: Optional[WebSocket] = None
_ws_lock = asyncio.Lock()

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


async def send_audio_to_computer(mp3_bytes: bytes) -> bool:
    """向前端推送一段音频（base64 编码的 mp3）."""
    if _active_ws is None:
        return False
    try:
        b64 = base64.b64encode(mp3_bytes).decode("ascii")
        await _active_ws.send_json({"type": "audio", "data": b64})
        return True
    except Exception as e:
        logger.warning(f"推送音频到电脑前端失败: {e}")
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


@router.websocket("/ws/computer")
async def computer_websocket(websocket: WebSocket):
    """本地电脑聊天 WebSocket.

    接收协议:
        {"type": "message", "content": "你好"}
        {"type": "ping"}

    推送协议:
        {"type": "sentence", "text": "你好呀~"}
        {"type": "audio", "data": "<base64 mp3>"}
        {"type": "done"}
        {"type": "pong"}
        {"type": "error", "message": "..."}
    """
    global _active_ws

    await websocket.accept()
    logger.info("电脑前端 WebSocket 已连接")

    async with _ws_lock:
        # 如果已有连接，替换（旧连接由前端自行断开）
        _active_ws = websocket

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
        logger.info("电脑前端连接已清理")
