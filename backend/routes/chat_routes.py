"""聊天相关API路由."""

import logging
from fastapi import APIRouter, HTTPException, Body

from backend.database.db import get_db
from backend.database.models import ApiResponse, Group, GroupListResponse, ContextListResponse
from backend.services.context_manager import context_manager


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["chat"])


@router.get("/groups")
async def get_all_groups():
    """获取所有群聊"""
    try:
        conn = await get_db()

        cursor = await conn.execute(
            """
            SELECT group_id, group_name, enabled, auto_reply_enabled, reply_delay_seconds
            FROM groups
            ORDER BY group_id
            """
        )

        rows = await cursor.fetchall()

        groups = []
        for row in rows:
            groups.append(Group(
                group_id=row[0],
                group_name=row[1],
                enabled=bool(row[2]),
                auto_reply_enabled=bool(row[3]),
                reply_delay_seconds=row[4]
            ))

        return GroupListResponse(success=True, message="获取成功", data=groups)

    except Exception as e:
        logger.error(f"获取群聊列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/groups/{group_id}/toggle")
async def toggle_group(group_id: str, enabled: bool = Body(..., embed=True)):
    """切换群聊启用状态"""
    try:
        conn = await get_db()

        # 检查群聊是否存在
        cursor = await conn.execute(
            "SELECT group_id FROM groups WHERE group_id = ?",
            (group_id,)
        )
        exists = await cursor.fetchone()

        if not exists:
            raise HTTPException(status_code=404, detail="群聊不存在")

        # 更新启用状态
        await conn.execute(
            "UPDATE groups SET enabled = ? WHERE group_id = ?",
            (1 if enabled else 0, group_id)
        )
        await conn.commit()

        logger.info(f"群聊 {group_id} 已{'启用' if enabled else '禁用'}")

        return ApiResponse(
            success=True,
            message=f"群聊已{'启用' if enabled else '禁用'}"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"切换群聊状态失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/groups/{group_id}/auto-reply")
async def toggle_auto_reply(group_id: str, enabled: bool = Body(..., embed=True)):
    """切换群聊自动回复状态"""
    try:
        conn = await get_db()

        # 检查群聊是否存在
        cursor = await conn.execute(
            "SELECT group_id FROM groups WHERE group_id = ?",
            (group_id,)
        )
        exists = await cursor.fetchone()

        if not exists:
            raise HTTPException(status_code=404, detail="群聊不存在")

        # 更新自动回复状态
        await conn.execute(
            "UPDATE groups SET auto_reply_enabled = ? WHERE group_id = ?",
            (1 if enabled else 0, group_id)
        )
        await conn.commit()

        logger.info(f"群聊 {group_id} 自动回复已{'启用' if enabled else '禁用'}")

        return ApiResponse(
            success=True,
            message=f"自动回复已{'启用' if enabled else '禁用'}"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"切换自动回复状态失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/groups/{group_id}/delay")
async def set_reply_delay(group_id: str, delay_seconds: int = Body(..., embed=True)):
    """设置回复延迟时间"""
    try:
        if delay_seconds < 1 or delay_seconds > 60:
            return ApiResponse(
                success=False,
                message="延迟时间必须在1-60秒之间"
            )

        conn = await get_db()

        # 检查群聊是否存在
        cursor = await conn.execute(
            "SELECT group_id FROM groups WHERE group_id = ?",
            (group_id,)
        )
        exists = await cursor.fetchone()

        if not exists:
            raise HTTPException(status_code=404, detail="群聊不存在")

        # 更新延迟时间
        await conn.execute(
            "UPDATE groups SET reply_delay_seconds = ? WHERE group_id = ?",
            (delay_seconds, group_id)
        )
        await conn.commit()

        logger.info(f"群聊 {group_id} 延迟时间已设置为 {delay_seconds} 秒")

        return ApiResponse(
            success=True,
            message=f"延迟时间已设置为 {delay_seconds} 秒"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"设置延迟时间失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/groups/{group_id}/context")
async def get_group_context(group_id: str, limit: int = 50):
    """获取群聊对话上下文"""
    try:
        context = await context_manager.get_group_context(group_id, limit)

        return ContextListResponse(
            success=True,
            message="获取成功",
            data=context
        )

    except Exception as e:
        logger.error(f"获取群聊上下文失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/groups/{group_id}/context")
async def clear_group_context(group_id: str, user_id: str = None):
    """清除群聊对话上下文"""
    try:
        conn = await get_db()

        # 检查群聊是否存在
        cursor = await conn.execute(
            "SELECT group_id FROM groups WHERE group_id = ?",
            (group_id,)
        )
        exists = await cursor.fetchone()

        if not exists:
            raise HTTPException(status_code=404, detail="群聊不存在")

        # 清除上下文
        if user_id:
            await context_manager.clear_context(group_id, user_id)
            message = f"用户 {user_id} 的上下文已清除"
        else:
            await context_manager.clear_context(group_id)
            message = "群聊上下文已清除"

        return ApiResponse(success=True, message=message)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"清除上下文失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def get_stats():
    """获取统计信息"""
    try:
        conn = await get_db()

        # 统计用户数
        cursor = await conn.execute("SELECT COUNT(*) FROM users")
        user_count = (await cursor.fetchone())[0]

        # 统计群聊数
        cursor = await conn.execute("SELECT COUNT(*) FROM groups")
        group_count = (await cursor.fetchone())[0]

        # 统计消息数
        cursor = await conn.execute("SELECT COUNT(*) FROM conversations")
        message_count = (await cursor.fetchone())[0]

        return {
            "success": True,
            "data": {
                "user_count": user_count,
                "group_count": group_count,
                "message_count": message_count,
                "current_api": config_manager.api_config.current_api,
                "api_count": len(config_manager.api_config.apis)
            }
        }

    except Exception as e:
        logger.error(f"获取统计信息失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# 导入config_manager避免循环导入
from backend.config import config_manager
