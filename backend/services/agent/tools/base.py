"""工具基类定义."""

from abc import ABC, abstractmethod
from pydantic import BaseModel, Field
from typing import List, Any


class ToolArgument(BaseModel):
    """工具参数定义"""
    name: str = Field(description="参数名")
    type: str = Field(description="参数类型: string/integer/boolean/array/object")
    description: str = Field(description="参数描述")
    required: bool = Field(default=False, description="是否必填")
    default: Any = Field(default=None, description="默认值")


class Tool(ABC):
    """工具基类

    所有工具都必须继承此类并实现抽象方法
    """
    @property
    @abstractmethod
    def name(self) -> str:
        """工具名称"""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """工具描述"""
        pass

    @property
    def arguments(self) -> List[ToolArgument]:
        """工具参数定义"""
        return []

    @abstractmethod
    async def execute(self, **kwargs) -> Any:
        """执行工具"""
        pass
