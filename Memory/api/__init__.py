"""MemoryAPI 统一接口模块。

提供记忆系统的 Facade 接口，隐藏内部复杂性。
"""

from Memory.api.memory_api import MemoryAPI
from Memory.api.exceptions import (
    MemoryAPIError,
    InputError,
    RecallError,
    ConsolidationError,
    StateError,
    CoreError,
)

__all__ = [
    "MemoryAPI",
    "MemoryAPIError",
    "InputError",
    "RecallError",
    "ConsolidationError",
    "StateError",
    "CoreError",
]
