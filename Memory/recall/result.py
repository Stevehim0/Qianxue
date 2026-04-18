"""召回结果数据类模块。

本模块定义召回过程中的中间结果和最终结果数据结构。
"""

from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class RecallResult:
    """体验层召回结果。

    Attributes:
        experience_id: 体验节点ID
        L1_text: L1要点文本（最终只返回L1）
        L0_text: L0摘要文本（内部使用，排序/扩散时用）
        recall_hint: 巩固阶段生成的recall_hint
        importance: 重要度评分（0-1）
        emotion_category: 情感类别
        time_distance_days: 时间距离（天数）
        activation_score: 激活分数
        source_type: 来源类型
        rank_score: 排序分数
        related_entities: 关联的信息层实体摘要（通过跨层边获取）
    """

    experience_id: str
    L1_text: Optional[str] = None
    L0_text: str = ""
    recall_hint: Optional[str] = None
    importance: float = 0.0
    emotion_category: Optional[str] = None
    time_distance_days: float = 0.0
    activation_score: float = 0.0
    source_type: str = "vector_search"
    rank_score: float = 0.0
    related_entities: Optional[List[dict]] = None


@dataclass
class EntityRecallResult:
    """信息层实体召回结果。

    Attributes:
        entity_id: 实体ID
        name: 实体名
        type: 实体类型（person/place/concept/event/skill/other）
        properties: 实体属性字典
        activation_score: 激活分数
        source_type: 来源类型
    """

    entity_id: str
    name: str
    type: str
    properties: Optional[dict] = None
    activation_score: float = 0.0
    source_type: str = "entity_vector_search"
