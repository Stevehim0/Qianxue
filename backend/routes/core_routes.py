"""核心层 API 路由 - 供 Memory 服务调用。"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.services.core.loader import identity_loader

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/core", tags=["core"])


@router.post("/shutdown")
async def graceful_shutdown():
    """触发优雅关闭 — 断开 Discord/FunASR 等外部连接，然后退出进程。"""
    import asyncio

    logger.info("收到关闭请求，开始优雅退出...")

    # 直接执行清理（断开 Discord 等）
    try:
        from backend.main import _graceful_shutdown
        await _graceful_shutdown()
    except Exception as e:
        logger.warning(f"清理异常: {e}")

    # 延迟退出，让 HTTP 响应先发出去
    async def _exit():
        await asyncio.sleep(0.5)
        import os
        os._exit(0)

    asyncio.create_task(_exit())
    return {"status": "shutting_down"}


class MalleableUpdateRequest(BaseModel):
    """可塑层更新请求。"""
    malleable_yaml: str
    reason: Optional[str] = None


class MalleableUpdateResponse(BaseModel):
    """可塑层更新响应。"""
    success: bool
    message: str


@router.get("/identity")
async def get_identity():
    """返回核心层信息（供 Memory 梦境系统获取）。

    Returns:
        stable_text: 稳定层文本
        malleable_yaml: 当前可塑层 YAML
    """
    identity = identity_loader.identity
    return {
        "stable_text": identity.stable_text,
        "malleable_yaml": identity.malleable_yaml,
    }


@router.post("/malleable", response_model=MalleableUpdateResponse)
async def update_malleable(request: MalleableUpdateRequest):
    """接收新的可塑层 YAML（由 Memory 梦境系统推送）。

    校验一致性后更新 identity.md 并重载核心层。
    """
    if not request.malleable_yaml or not request.malleable_yaml.strip():
        raise HTTPException(status_code=400, detail="malleable_yaml 不能为空")

    try:
        # 更新可塑层并重载
        identity_loader.update_malleable(request.malleable_yaml)
        logger.info(f"可塑层已更新: {request.reason or '梦境演化'}")

        # 重置阀门过滤器（如果 identity 变了）
        from backend.services.agent.tools.send_message import _valve_filter
        global _valve_filter
        if _valve_filter is not None:
            from backend.services.core.valve_filter import ValveFilter
            _valve_filter = ValveFilter(identity_loader.identity)

        return MalleableUpdateResponse(
            success=True,
            message="可塑层更新成功",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"可塑层更新失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
