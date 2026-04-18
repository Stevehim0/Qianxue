"""个人档案数据类模块。

本模块定义个人档案相关的数据类，包括InteractionStyle和PersonProfile。
"""

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class InteractionStyle:
    """相处方式数据类（6个维度）。

    Attributes:
        warmth: 热情度 (0-1)
        formality: 正式度 (0-1)
        humor: 幽默感 (0-1)
        proactivity: 主动性 (0-1)
        directness: 直接度 (0-1)
        boundaries: 边界感 (0-1)
    """

    warmth: float = 0.5  # 热情度 (0-1)
    formality: float = 0.5  # 正式度 (0-1)
    humor: float = 0.5  # 幽默感 (0-1)
    proactivity: float = 0.5  # 主动性 (0-1)
    directness: float = 0.5  # 直接度 (0-1)
    boundaries: float = 0.5  # 边界感 (0-1)


@dataclass
class PersonProfile:
    """个人档案数据类（扩展版）。

    Attributes:
        id: 档案ID
        basic: 基本信息 {name, type, first_met, relation_to_self}
        interaction_style: 相处方式（InteractionStyle对象）
        preferences: 偏好设置
        notes: 备注
        created_at: 创建时间
        updated_at: 更新时间
    """

    id: str  # 档案ID
    basic: Dict  # 基本信息 {name, type, first_met, ...}
    interaction_style: InteractionStyle  # 相处方式
    preferences: Optional[Dict] = None  # 偏好设置
    notes: Optional[str] = None  # 备注
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
