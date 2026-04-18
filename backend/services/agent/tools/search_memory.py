"""搜索记忆工具 - 通过 memory_interface 调用记忆系统."""

import logging
from datetime import datetime
from typing import Dict, Any

from .base import Tool, ToolArgument
import backend.services.memory_interface as mem_mod
from backend.services.context_manager import context_manager


logger = logging.getLogger(__name__)


class SearchMemoryTool(Tool):
    """搜索记忆工具"""

    @property
    def name(self) -> str:
        return "search_memory"

    @property
    def description(self) -> str:
        return (
            "用关键词搜索相关记忆，返回记忆简报文本。"
            "返回的内容仅供你参考，你需要自己判断哪些信息相关、是否准确，"
            "然后自然地融入回复中——不要直接复述或逐条念出搜索结果。"
        )

    @property
    def arguments(self) -> list:
        return [
            ToolArgument(
                name="query",
                type="string",
                description="搜索关键词，多个关键词用空格分隔",
                required=True
            ),
            ToolArgument(
                name="group_id",
                type="string",
                description="当前群聊ID（自动注入，无需手动填写）",
                required=False
            ),
        ]

    async def execute(self, **kwargs) -> Dict[str, Any]:
        """执行记忆搜索，返回记忆简报"""
        query = kwargs.get("query")

        if not query:
            return {"success": False, "error": "缺少查询文本"}

        try:
            # 尝试从 ContextManager 获取最近对话历史
            recall_context = None
            group_id = kwargs.get("group_id")
            if group_id:
                try:
                    messages = await context_manager.get_group_context(
                        group_id=group_id,
                        limit=10,
                        time_window_minutes=60,
                    )
                    recent_history = []
                    for msg in messages:
                        role = "user" if msg.role == "user" else "assistant"
                        recent_history.append({
                            "role": role,
                            "content": f"{msg.sender_nickname}: {msg.content}",
                        })
                    recall_context = {
                        "recent_history": recent_history,
                        "ai_state": await mem_mod.memory_provider.get_ai_state(),
                        "current_time": datetime.now().isoformat(),
                    }
                except Exception as e:
                    logger.warning(f"获取群聊上下文失败，使用空上下文: {e}")

            logger.info(f"[search_memory] query: {query}, has_context: {recall_context is not None}")
            briefing = await mem_mod.memory_provider.retrieve_briefing(
                query=query,
                context=recall_context,
            )
            logger.info(f"[search_memory] result briefing: {briefing}")

            if briefing:
                return {
                    "success": True,
                    "briefing": briefing,
                    "query": query,
                }
            else:
                return {
                    "success": True,
                    "briefing": None,
                    "query": query,
                }

        except Exception as e:
            logger.error(f"记忆搜索失败: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
