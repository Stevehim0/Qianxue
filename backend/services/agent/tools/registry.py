"""工具注册表."""

import logging
from typing import Dict, Type, List, Optional, Any
from .base import Tool


logger = logging.getLogger(__name__)


class ToolRegistry:
    """工具注册表

    负责工具的注册、管理和执行
    """

    def __init__(self):
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool):
        """注册工具

        Args:
            tool: 工具实例
        """
        self._tools[tool.name] = tool
        logger.info(f"已注册工具: {tool.name}")

    def get(self, name: str) -> Optional[Tool]:
        """获取工具

        Args:
            name: 工具名称

        Returns:
            工具实例或None
        """
        return self._tools.get(name)

    def list_tools(self) -> List[str]:
        """列出所有工具

        Returns:
            工具名称列表
        """
        return list(self._tools.keys())

    def get_tool_info(self, name: str) -> Optional[Dict]:
        """获取工具信息

        Args:
            name: 工具名称

        Returns:
            工具信息字典
        """
        tool = self.get(name)
        if not tool:
            return None
        return {
            "name": tool.name,
            "description": tool.description,
            "arguments": [
                {
                    "name": arg.name,
                    "type": arg.type,
                    "description": arg.description,
                    "required": arg.required,
                    "default": arg.default
                }
                for arg in tool.arguments
            ]
        }

    async def execute_tool(self, name: str, **kwargs) -> Any:
        """执行工具

        Args:
            name: 工具名称
            **kwargs: 工具参数

        Returns:
            工具执行结果

        Raises:
            ValueError: 工具不存在
        """
        tool = self.get(name)
        if not tool:
            raise ValueError(f"工具 '{name}' 不存在")

        logger.info(f"执行工具: {name}, 参数: {kwargs}")
        return await tool.execute(**kwargs)
