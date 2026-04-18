"""核心层约束检查实现。

根据 AI 性格定义约束状态波动的边界。
Iris 的性格是"温文尔雅、端庄平和、情绪克制"，
所以 arousal 不会太高，情绪不会太极端。
"""

import logging
from typing import TYPE_CHECKING

from Memory.state import StateConstraints

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class DefaultStateConstraints:
    """核心层约束检查实现。

    根据性格关键词推导状态边界：
    - "温文尔雅" → arousal 上限 0.7（不会狂躁）
    - "情绪克制" → valence 范围 [-0.6, 0.7]（不会极端悲伤或狂喜）
    - "端庄平和" → confidence 范围 [0.3, 0.9]（不会完全没主见也不会过于自负）
    """

    # 基于性格的硬边界
    MOOD_VALENCE_RANGE = (-0.6, 0.7)
    MOOD_AROUSAL_RANGE = (0.0, 0.7)
    ENERGY_RANGE = (0.1, 1.0)
    CONFIDENCE_RANGE = (0.3, 0.9)

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def check_mood_bounds(
        self, valence: float, arousal: float, core_layer: "Identity" = None
    ) -> tuple[float, float]:
        """检查情绪是否在允许范围内。

        Args:
            valence: 效价值（-1到1）
            arousal: 唤醒度值（0到1）
            core_layer: 核心层Identity对象（可选，未来可从性格动态推导）

        Returns:
            (valence, arousal) 元组，已截断到允许范围
        """
        v_min, v_max = self.MOOD_VALENCE_RANGE
        a_min, a_max = self.MOOD_AROUSAL_RANGE

        new_valence = max(v_min, min(v_max, valence))
        new_arousal = max(a_min, min(a_max, arousal))

        if new_valence != valence or new_arousal != arousal:
            self.logger.debug(
                f"情绪约束: ({valence:.2f}, {arousal:.2f}) → ({new_valence:.2f}, {new_arousal:.2f})"
            )

        return new_valence, new_arousal

    def check_energy_bounds(self, energy: float, core_layer: "Identity" = None) -> float:
        """检查精力是否在允许范围内。

        Args:
            energy: 精力值（0到1）
            core_layer: 核心层Identity对象

        Returns:
            截断后的精力值
        """
        e_min, e_max = self.ENERGY_RANGE
        new_energy = max(e_min, min(e_max, energy))
        return new_energy

    def check_confidence_bounds(self, confidence: float, core_layer: "Identity" = None) -> float:
        """检查信心是否在允许范围内。

        Args:
            confidence: 信心值（0到1）
            core_layer: 核心层Identity对象

        Returns:
            截断后的信心值
        """
        c_min, c_max = self.CONFIDENCE_RANGE
        new_confidence = max(c_min, min(c_max, confidence))
        return new_confidence
