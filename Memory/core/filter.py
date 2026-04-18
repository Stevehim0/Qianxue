"""核心层阀门过滤器模块。

阀门过滤逻辑已移至主系统（backend/services/core/valve_filter.py）。
本模块仅保留 FilterResult 数据类。
"""

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class FilterResult:
    """阀门过滤结果。

    Attributes:
        passed: 是否通过过滤
        reason: 未通过的原因（None表示通过）
        requires_negotiation: 是否需要协商
        negotiated_response: 协商响应文本（如果需要协商）
    """

    passed: bool
    reason: Optional[str] = None
    requires_negotiation: bool = False
    negotiated_response: Optional[str] = None
