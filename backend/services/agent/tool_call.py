"""工具调用数据结构."""

from pydantic import BaseModel, Field
from typing import Optional, Dict, List, Union
from enum import Enum

# 使用 Union 替代 Any，避免与 Pydantic 冲突
AnyType = Union[int, float, str, bool, list, dict, None]


class ToolCallStatus(str, Enum):
    """工具调用状态"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class ToolCall(BaseModel):
    """工具调用记录"""
    # 工具信息
    tool_name: str = Field(description="工具名称")
    tool_id: str = Field(description="唯一调用ID")

    # 状态
    status: ToolCallStatus = Field(default=ToolCallStatus.PENDING)

    # 参数
    arguments: Dict[str, AnyType] = Field(default_factory=dict, description="工具参数")
    resolved_arguments: Dict[str, AnyType] = Field(default_factory=dict, description="解析后的参数(变量替换后)")

    # 执行结果
    result: Optional[AnyType] = Field(default=None, description="工具执行结果")
    error: Optional[str] = Field(default=None, description="错误信息")

    # 依赖信息
    depends_on: List[str] = Field(default_factory=list, description="依赖的工具调用ID")

    # 执行时间
    start_time: Optional[float] = None
    end_time: Optional[float] = None
