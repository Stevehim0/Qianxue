"""核心层模块 - AI人格DNA。

定义AI的自我，规范行为和决策，支持梦境演化外在表现。
"""

from backend.services.core.models import Identity, MalleableState
from backend.services.core.loader import identity_loader, IdentityLoader
from backend.services.core.prompt_builder import build_system_prompt
from backend.services.core.valve_filter import ValveFilter, FilterResult

__all__ = [
    "Identity",
    "MalleableState",
    "identity_loader",
    "IdentityLoader",
    "build_system_prompt",
    "ValveFilter",
    "FilterResult",
]
