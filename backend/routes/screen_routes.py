"""屏幕感知 API — 接收本地截屏客户端的帧，识别并写入记忆."""

import asyncio
import base64
import io
import logging
import time
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.services.vision_service import vision_service
from backend.services.context_manager import context_manager
from backend.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/screen", tags=["screen"])

# 上一次截图的描述（用于去重，避免重复识别相似画面）
_last_description: Optional[str] = None
_last_timestamp: float = 0


class ScreenFrameRequest(BaseModel):
    """截屏客户端发送的帧."""
    image_base64: str  # JPEG/PNG base64
    trigger: str = "manual"  # manual | auto | interval
    metadata: Optional[dict] = None  # 客户端附加信息（窗口标题等）


class ScreenFrameResponse(BaseModel):
    success: bool
    description: Optional[str] = None
    message: str = ""


@router.post("/perceive", response_model=ScreenFrameResponse)
async def perceive_screen(req: ScreenFrameRequest):
    """接收屏幕截图 → 识别 → 写入短期记忆."""
    global _last_description, _last_timestamp

    if not settings.vision.enabled:
        raise HTTPException(status_code=503, detail="Vision 服务未启用")

    try:
        # 1. 调 VL 模型识别屏幕内容
        description = await _recognize_frame(req.image_base64)
        if not description:
            return ScreenFrameResponse(success=False, message="识别失败")

        # 2. 去重：和上次描述太相似就跳过
        now = time.time()
        if _last_description and _similarity(description, _last_description) > 0.85:
            if now - _last_timestamp < 30:
                logger.info("屏幕内容未显著变化，跳过")
                return ScreenFrameResponse(
                    success=True,
                    description=description,
                    message="内容未变化，已跳过"
                )

        _last_description = description
        _last_timestamp = now

        # 3. 写入 STM（让千雪"感知到"你在看什么）
        await _write_screen_perception(description, req.trigger, req.metadata)

        return ScreenFrameResponse(
            success=True,
            description=description,
            message="已感知"
        )

    except Exception as e:
        logger.error(f"屏幕感知失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def screen_status():
    """屏幕感知服务状态."""
    return {
        "enabled": settings.vision.enabled,
        "last_perception": _last_timestamp,
        "last_description": (_last_description or "")[:100],
    }


async def _recognize_frame(image_base64: str) -> Optional[str]:
    """调 VL 模型识别屏幕截图."""
    try:
        # 确保 base64 带上 data URI 前缀
        if not image_base64.startswith("data:"):
            image_b64_with_prefix = f"data:image/jpeg;base64,{image_base64}"
        else:
            image_b64_with_prefix = image_base64

        config = {
            "api_key": settings.vision.api_key,
            "base_url": settings.vision.base_url,
            "model": settings.vision.model,
            "max_retries": settings.vision.max_retries,
            "timeout": settings.vision.timeout,
        }

        import httpx

        headers = {
            "Authorization": f"Bearer {config['api_key']}",
            "Content-Type": "application/json",
        }

        prompt = (
            "这是用户的电脑屏幕截图。请简洁描述：1. 用户当前在做什么（看什么网站/应用/游戏）"
            "2. 屏幕上的关键内容（标题、主要文字、界面元素）"
            "3. 如果能看出用户在做什么活动，也请说明。用中文，控制在2-3句话以内。"
        )

        data = {
            "model": config["model"],
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": image_b64_with_prefix}},
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        }

        async with httpx.AsyncClient(timeout=config["timeout"] * 2) as client:
            resp = await client.post(
                f"{config['base_url']}/chat/completions",
                headers=headers,
                json=data,
            )

            if resp.status_code == 200:
                result = resp.json()
                content = result["choices"][0]["message"]["content"]
                if isinstance(content, list):
                    content = next(
                        (item["text"] for item in content if isinstance(item, dict) and item.get("type") == "text"),
                        str(content[0]),
                    )
                logger.info(f"屏幕识别: {content[:100]}")
                return content
            else:
                logger.warning(f"VL API 错误: {resp.status_code} {resp.text[:200]}")
                return None

    except Exception as e:
        logger.error(f"屏幕识别异常: {e}")
        return None


async def _write_screen_perception(description: str, trigger: str, metadata: Optional[dict]):
    """写入 STM 事件，让千雪能感知到用户在看什么."""
    try:
        from backend.services.stm_client import stm_client

        window_title = ""
        if metadata and metadata.get("window_title"):
            window_title = f"（{metadata['window_title']}）"

        await stm_client.record_event(
            event_type="screen_perception",
            source_type="screen_capture",
            group_id="system",
            user_id="screen_agent",
            summary=f"屏幕内容{window_title}: {description[:80]}",
            detail=description,
            importance=0.3,  # 低权重，不触发主动回复
        )
        logger.info(f"屏幕感知已写入 STM: {description[:60]}")

    except Exception as e:
        logger.warning(f"写入 STM 失败: {e}")


def _similarity(a: str, b: str) -> float:
    """简单的文本相似度（字符级 Jaccard）."""
    if not a or not b:
        return 0.0
    set_a = set(a)
    set_b = set(b)
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union else 0.0
