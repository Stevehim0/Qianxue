"""错误通知模块 — 系统出错时私聊通知管理员。

功能:
- 出错时通过 NapCat 私聊发送错误摘要给管理员
- 同类错误 60 秒内只通知一次（防刷屏）
- 所有操作 fire-and-forget，绝不阻塞主流程
"""

import asyncio
import logging
import time
from typing import Optional

from backend.config import settings

logger = logging.getLogger(__name__)

# 冷却记录: key → (last_notify_time, repeat_count)
_cooldown_map: dict[str, tuple[float, int]] = {}


def _format_error_message(
    error_type: str,
    source: str,
    error: str,
    repeat_count: int = 0,
) -> str:
    """格式化错误通知消息。"""
    parts = [f"[系统错误] {error_type}"]
    parts.append(f"来源: {source}")
    parts.append(f"错误: {error}")
    if repeat_count > 0:
        parts.append(f"(此类错误已重复 {repeat_count} 次)")
    return "\n".join(parts)


async def notify_error(
    error_type: str,
    source: str,
    error: str,
) -> None:
    """发送错误通知给管理员（fire-and-forget）。

    Args:
        error_type: 错误类型，如 "LLM 调用失败"、"工具执行失败"
        source: 错误来源，如 "群1234 用户消息处理"
        error: 错误详情，如 "ConnectionTimeout - API请求超时"
    """
    try:
        admin_id = settings.admin.qq_id
        if not admin_id:
            return

        # 冷却检查
        cooldown_key = f"{error_type}|{source}"
        now = time.time()
        repeat_count = 0

        if cooldown_key in _cooldown_map:
            last_time, count = _cooldown_map[cooldown_key]
            if now - last_time < settings.admin.cooldown_seconds:
                # 在冷却期内，只增加计数，不发送
                _cooldown_map[cooldown_key] = (last_time, count + 1)
                return
            repeat_count = count

        # 更新冷却记录
        _cooldown_map[cooldown_key] = (now, 0)

        # 构造消息
        msg = _format_error_message(error_type, source, error, repeat_count)

        # 发送私聊消息
        from backend.api.napcat import napcat_client
        success = await napcat_client.send_private_message(int(admin_id), msg)
        if success:
            logger.info(f"已发送错误通知给管理员: {error_type}")
        else:
            logger.warning(f"发送错误通知失败: {error_type}")

    except Exception as e:
        # 通知本身失败不影响主流程
        logger.warning(f"错误通知模块异常: {e}")


def notify_error_sync(
    error_type: str,
    source: str,
    error: str,
) -> None:
    """同步版本：在非 async 上下文中使用，fire-and-forget 创建 task。"""
    try:
        asyncio.create_task(notify_error(error_type, source, error))
    except Exception:
        pass
