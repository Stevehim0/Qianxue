"""获取对话上下文工具 - 包装context_manager.get_group_context."""

import logging
from typing import Dict, Any

from .base import Tool, ToolArgument
from backend.services.context_manager import context_manager


logger = logging.getLogger(__name__)


class GetConversationContextTool(Tool):
    """获取对话上下文工具

    包装context_manager.get_group_context
    """

    @property
    def name(self) -> str:
        return "get_conversation_context"

    @property
    def description(self) -> str:
        return "获取群聊的最近对话上下文"

    @property
    def arguments(self) -> list:
        return [
            ToolArgument(
                name="group_id",
                type="string",
                description="群聊ID",
                required=True
            ),
            ToolArgument(
                name="limit",
                type="integer",
                description="返回消息数量限制",
                required=False,
                default=50
            ),
            ToolArgument(
                name="time_window_minutes",
                type="integer",
                description="时间窗口(分钟)",
                required=False,
                default=30
            )
        ]

    async def execute(self, **kwargs) -> Dict[str, Any]:
        """
        执行获取对话上下文

        直接复用context_manager.get_group_context (第461-546行)
        """
        group_id = kwargs.get("group_id")
        limit = kwargs.get("limit", 50)
        time_window_minutes = kwargs.get("time_window_minutes", 30)

        if not group_id:
            return {"success": False, "error": "缺少群聊ID"}

        try:
            messages = await context_manager.get_group_context(
                group_id=group_id,
                limit=limit,
                time_window_minutes=time_window_minutes
            )

            # 格式化上下文
            formatted_context = context_manager.format_group_context_for_llm(messages)

            return {
                "success": True,
                "count": len(messages),
                "context": formatted_context,
                "time_window_minutes": time_window_minutes
            }

        except Exception as e:
            logger.error(f"获取对话上下文失败: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
