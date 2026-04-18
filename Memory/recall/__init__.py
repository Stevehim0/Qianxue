"""召回层模块。

本模块提供召回层的核心组件导出。
"""

# 导入所有组件
from .detector import TriggerDetector
from .result import RecallResult, EntityRecallResult
from .manager import RecallManager
from .adjacency_cache import AdjacencyCache
from .briefing import BriefingGenerator
from .profile_manager import ProfileManager
from .profile_data import PersonProfile, InteractionStyle

__all__ = [
    "TriggerDetector",
    "RecallResult",
    "EntityRecallResult",
    "RecallManager",
    "AdjacencyCache",
    "BriefingGenerator",
    "ProfileManager",
    "PersonProfile",
    "InteractionStyle",
]
