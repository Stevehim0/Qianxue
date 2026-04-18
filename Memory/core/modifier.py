"""核心层修改机制模块。

本模块提供 ModificationResult 数据类。
核心层修改逻辑已移至主系统（backend/services/core/）。
"""

import logging
from dataclasses import dataclass
from typing import Optional

from Memory.core.loader import Identity

logger = logging.getLogger(__name__)


@dataclass
class ModificationResult:
    """核心层修改结果。

    Attributes:
        accepted: 是否接受修改
        reason: 决策原因
        negotiation: 协商文本（如果需要）
        new_identity: 修改后的Identity对象（如果接受）
    """

    accepted: bool
    reason: str
    negotiation: Optional[str] = None
    new_identity: Optional[Identity] = None
