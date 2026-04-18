"""核心层数据模型。

DEPRECATED: 本模块已废弃。核心层数据现通过 Backend HTTP API (GET /api/core/identity) 获取。
参见 Memory/api/memory_api.py load_core()。

本模块定义核心层的数据结构。
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class Identity:
    """核心层人设数据类。

    包含AI人格DNA的三层结构和锚点。

    Attributes:
        invariant_text: 不变层文本（底线、风格关键词、价值排序）
        stable_text: 稳定层文本（可协商的偏好和习惯）
        plastic_text: 可塑层文本（灵活可改的信息）
        anchors: 锚点字典（底线、风格、价值等）
        raw_text: 完整的原始人设文本
        source_path: 人设文件路径（用于追踪来源）
    """

    invariant_text: str
    stable_text: str
    plastic_text: str
    anchors: Dict[str, any] = field(default_factory=dict)
    raw_text: Optional[str] = None
    source_path: Optional[Path] = None

    def __str__(self) -> str:
        """返回人设的字符串表示。"""
        parts = []
        if self.invariant_text:
            parts.append(f"## 不变层\n{self.invariant_text}")
        if self.stable_text:
            parts.append(f"## 稳定层\n{self.stable_text}")
        if self.plastic_text:
            parts.append(f"## 可塑层\n{self.plastic_text}")
        return "\n\n".join(parts)

    def to_dict(self) -> Dict[str, any]:
        """转换为字典。"""
        return {
            "invariant_text": self.invariant_text,
            "stable_text": self.stable_text,
            "plastic_text": self.plastic_text,
            "anchors": self.anchors,
            "raw_text": self.raw_text,
        }
