"""核心层数据模型。"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional


@dataclass
class Identity:
    """AI人格DNA。

    Attributes:
        invariant_text: 不变层文本（硬约束，不可违反）
        stable_text: 稳定层文本（行为模式，影响决策）
        malleable_yaml: 可塑层YAML文本（表达风格，可被梦境演化）
        malleable_data: 解析后的可塑层字典
        raw_text: 完整原始文本
        source_path: 人设文件路径
    """

    invariant_text: str
    stable_text: str
    malleable_yaml: str
    malleable_data: Optional[Dict] = None
    raw_text: Optional[str] = None
    source_path: Optional[Path] = None

    def to_dict(self) -> Dict:
        """转换为字典。"""
        return {
            "invariant_text": self.invariant_text,
            "stable_text": self.stable_text,
            "malleable_yaml": self.malleable_yaml,
            "malleable_data": self.malleable_data,
        }


@dataclass
class MalleableState:
    """解析后的可塑层状态。

    Attributes:
        style: 表达风格（tone, speech）
        preferences: 偏好（topics, interaction）
        emotional: 情感状态（baseline, expression）
    """

    style: Dict = field(default_factory=dict)
    preferences: Dict = field(default_factory=dict)
    emotional: Dict = field(default_factory=dict)
