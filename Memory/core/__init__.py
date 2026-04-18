"""核心层模块。

DEPRECATED: 本模块已废弃。核心层数据现通过 Backend HTTP API (GET /api/core/identity) 获取，
不再由 Memory 服务本地管理。参见 Memory/api/memory_api.py load_core()。

本模块提供AI人格DNA的定义、加载和解析功能。
核心层包含三层同心圆结构：不变层、稳定层、可塑层。

注意：阀门过滤和修改逻辑已移至主系统（backend/services/core/）。
"""

from Memory.core.loader import Identity, IdentityLoader, load_identity
from Memory.core.parser import IdentityParser, parse_three_layers, extract_anchors
from Memory.core.filter import FilterResult
from Memory.core.modifier import ModificationResult

__all__ = [
    # 数据类
    "Identity",
    "FilterResult",
    "ModificationResult",
    # 加载器
    "IdentityLoader",
    "load_identity",
    # 解析器
    "IdentityParser",
    "parse_three_layers",
    "extract_anchors",
]
