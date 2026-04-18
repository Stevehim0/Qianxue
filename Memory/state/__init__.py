"""状态层模块。

本模块提供AI状态的定义、管理和更新功能。
状态层包含四个变量：mood（情绪）、energy（精力）、focus（注意力）、confidence（信心）。

Phase 4实现：
    - Protocol接口定义（StateManager/StateUpdater/StateConstraints）
    - 默认实现返回中性默认值
    - 占位更新方法使用pass

Phase 9实现：
    - 完整的双触发更新机制
    - 回归公式和核心层约束检查
"""

from typing import Protocol, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


# ========== 数据类 ==========


@dataclass
class MoodState:
    """情绪状态数据类。

    采用Russell情绪环形模型，使用二维坐标表示情绪。

    Attributes:
        valence: 效价（-1到1，负面到正面）
        arousal: 唤醒度（0到1，平静到激动）
        label: 自然语言标签（如"平静"、"兴奋"）
    """

    valence: float  # -1 to 1
    arousal: float  # 0 to 1
    label: str

    def __post_init__(self):
        """验证数据范围。"""
        if not -1 <= self.valence <= 1:
            raise ValueError(f"valence必须在[-1, 1]范围内，当前值: {self.valence}")
        if not 0 <= self.arousal <= 1:
            raise ValueError(f"arousal必须在[0, 1]范围内，当前值: {self.arousal}")


@dataclass
class EnergyState:
    """精力状态数据类。

    Attributes:
        value: 精力值（0到1）
        label: 自然语言标签（如"充沛"、"疲惫"）
    """

    value: float  # 0 to 1
    label: str

    def __post_init__(self):
        """验证数据范围。"""
        if not 0 <= self.value <= 1:
            raise ValueError(f"value必须在[0, 1]范围内，当前值: {self.value}")


# ========== Protocol接口定义 ==========


class StateManager(Protocol):
    """状态管理器接口（Protocol）。

    定义状态读取和格式化方法的具体签名。
    实现类只需提供这些方法，无需显式继承。

    Examples:
        >>> manager: StateManager = DefaultStateManager()
        >>> mood = manager.get_mood()
        >>> prompt = manager.format_state_prompt()
    """

    def get_mood(self) -> MoodState:
        """获取当前情绪状态。

        Returns:
            MoodState: 包含valence, arousal, label的情绪状态

        Notes:
            Phase 4: 返回中性默认值
            Phase 9: 从数据库读取实际状态
        """
        ...

    def get_energy(self) -> EnergyState:
        """获取当前精力值。

        Returns:
            EnergyState: 包含value和label的精力状态

        Notes:
            Phase 4: 返回中性默认值
            Phase 9: 从数据库读取实际状态
        """
        ...

    def get_focus(self) -> Optional[str]:
        """获取当前注意力焦点。

        Returns:
            关注对象描述，None表示无焦点

        Notes:
            Phase 4: 返回None
            Phase 9: 从数据库读取实际焦点
        """
        ...

    def get_confidence(self) -> float:
        """获取当前信心值。

        Returns:
            信心值 0-1

        Notes:
            Phase 4: 返回0.5
            Phase 9: 从数据库读取实际信心值
        """
        ...

    def format_state_prompt(self) -> str:
        """格式化状态为prompt注入文本。

        Returns:
            可直接注入LLM prompt的文本

        Examples:
            >>> prompt = manager.format_state_prompt()
            >>> print(prompt)
            [当前状态]
            情绪：平静 (valence:0.0, arousal:0.3)
            精力：正常 (value: 0.5)
            注意力：无
            信心：正常 (value: 0.5)
        """
        ...


class StateUpdater(Protocol):
    """状态更新器接口（Protocol）。

    定义状态更新的触发方法签名。

    Examples:
        >>> updater: StateUpdater = DefaultStateUpdater()
        >>> updater.trigger_immediate_update({"intensity": 0.9})
    """

    def trigger_immediate_update(self, emotion_snapshot: dict) -> None:
        """即时更新状态（由写入层触发）。

        当写入层完成情感快照后，如果intensity>0.8且距上次更新>1分钟，
        立即触发体验驱动路径的状态更新，并重置10分钟定时器。

        Args:
            emotion_snapshot: 包含category, intensity, valence, arousal的情感快照

        Notes:
            Phase 4: 占位实现，使用pass
            Phase 9: 完整实现即时更新逻辑
                - 检查intensity>0.8且间隔>1分钟
                - 调用体验驱动路径（复用定时更新的逻辑）
                - 重置10分钟定时器
        """
        ...

    def trigger_timed_update(self) -> None:
        """定时更新状态（每10分钟触发）。

        由后台定时器调用，每10分钟检查一次是否有新体验：
        - 有新体验：调用LLM评估新状态（体验驱动路径）
        - 无新体验：回归基线（基线回归路径）

        Notes:
            Phase 4: 占位实现，使用pass
            Phase 9: 完整实现定时更新逻辑
                - 查询过去10分钟的体验节点
                - 有体验：LLM评估新状态
                - 无体验：应用回归公式
                - 核心层约束检查
                - 写入新状态到数据库
        """
        ...


class StateConstraints(Protocol):
    """核心层约束检查接口（Protocol）。

    定义核心层约束检查的方法签名。

    Examples:
        >>> constraints: StateConstraints = DefaultStateConstraints()
        >>> new_mood = constraints.check_mood_bounds(current_mood, core_layer)
    """

    def check_mood_bounds(self, valence: float, arousal: float, core_layer) -> tuple[float, float]:
        """检查情绪是否在核心层允许的范围内。

        根据核心层性格定义，情绪有波动范围边界。
        超出部分截断到边界值。

        Args:
            valence: 效价值
            arousal: 唤醒度值
            core_layer: 核心层Identity对象

        Returns:
            (valence, arousal) 元组，已截断到允许范围

        Notes:
            Phase 4: 占位实现，返回原值
            Phase 9: 根据核心层性格定义约束边界
        """
        ...

    def check_energy_bounds(self, energy: float, core_layer) -> float:
        """检查精力是否在核心层允许的范围内。

        Args:
            energy: 精力值
            core_layer: 核心层Identity对象

        Returns:
            截断后的精力值

        Notes:
            Phase 4: 占位实现，返回原值
            Phase 9: 根据核心层性格定义约束边界
        """
        ...

    def check_confidence_bounds(self, confidence: float, core_layer) -> float:
        """检查信心是否在核心层允许的范围内。

        Args:
            confidence: 信心值
            core_layer: 核心层Identity对象

        Returns:
            截断后的信心值

        Notes:
            Phase 4: 占位实现，返回原值
            Phase 9: 根据核心层性格定义约束边界
        """
        ...


# 导出列表
__all__ = [
    # 数据类
    "MoodState",
    "EnergyState",
    # Protocol接口
    "StateManager",
    "StateUpdater",
    "StateConstraints",
]
