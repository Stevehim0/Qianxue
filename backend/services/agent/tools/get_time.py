"""获取当前时间工具."""

import logging
from datetime import datetime
from typing import Dict, Any

from .base import Tool


logger = logging.getLogger(__name__)


class GetCurrentTimeTool(Tool):
    """获取当前时间工具"""

    @property
    def name(self) -> str:
        return "get_current_time"

    @property
    def description(self) -> str:
        return "获取当前日期和时间"

    async def execute(self, **kwargs) -> Dict[str, Any]:
        """执行获取当前时间"""
        now = datetime.now()

        # 返回包含多种格式的时间，方便模型选择使用
        time_str = now.strftime("%H:%M")
        date_str = now.strftime("%Y年%m月%d日")
        full_str = f"{date_str} {time_str}"

        return {
            "success": True,
            # 原始格式
            "datetime": now.isoformat(),
            "date": now.strftime("%Y-%m-%d"),
            "time": time_str,
            "weekday": now.strftime("%A"),
            # 友好格式
            "friendly": time_str,  # "14:30"
            "chinese": full_str,  # "2026年02月24日 14:30"
            "short": time_str  # 简洁格式，推荐使用
        }
