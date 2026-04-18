"""状态管理器实现。

Phase 4: 返回中性默认值，不从数据库读取。
Phase 9: 完整实现，从数据库读取实际状态。
"""

import logging
from typing import Optional

from Memory.state import MoodState, EnergyState, StateManager

logger = logging.getLogger(__name__)


class DefaultStateManager:
    """状态管理器实现。

    从 StateStore 读取数据库中的真实状态。
    如果数据库未初始化或读取失败，降级返回中性默认值。

    Examples:
        >>> manager = DefaultStateManager()
        >>> mood = manager.get_mood()
        >>> print(mood.label)
        平静
    """

    # 基线默认值（降级时使用）
    DEFAULT_MOOD_VALENCE = 0.0
    DEFAULT_MOOD_AROUSAL = 0.3
    DEFAULT_MOOD_LABEL = "平静"

    DEFAULT_ENERGY_VALUE = 0.7
    DEFAULT_ENERGY_LABEL = "正常"

    DEFAULT_FOCUS = None
    DEFAULT_CONFIDENCE = 0.7
    DEFAULT_CONFIDENCE_LABEL = "正常"

    def __init__(self, state_store=None):
        """初始化状态管理器。

        Args:
            state_store: StateStore 实例。如果为 None，延迟导入全局实例。
        """
        self._state_store = state_store
        self.logger = logging.getLogger(__name__)

    @property
    def state_store(self):
        """延迟导入 StateStore，避免循环依赖。"""
        if self._state_store is None:
            from Memory.storage.state_store import state_store
            self._state_store = state_store
        return self._state_store

    def _load_state(self):
        """从数据库加载状态，失败时返回 None。"""
        try:
            return self.state_store.get()
        except Exception as e:
            self.logger.debug(f"Failed to load state from DB, using defaults: {e}")
            return None

    def get_mood(self) -> MoodState:
        """获取当前情绪状态。

        从数据库读取实际值，读取失败时降级返回默认值。

        Returns:
            MoodState: 情绪状态
        """
        state = self._load_state()
        if state:
            return MoodState(
                valence=state.mood_valence,
                arousal=state.mood_arousal,
                label=state.mood_label,
            )
        return MoodState(
            valence=self.DEFAULT_MOOD_VALENCE,
            arousal=self.DEFAULT_MOOD_AROUSAL,
            label=self.DEFAULT_MOOD_LABEL,
        )

    def get_energy(self) -> EnergyState:
        """获取当前精力值。

        Returns:
            EnergyState: 精力状态
        """
        state = self._load_state()
        if state:
            return EnergyState(value=state.energy_value, label=state.energy_label)
        return EnergyState(value=self.DEFAULT_ENERGY_VALUE, label=self.DEFAULT_ENERGY_LABEL)

    def get_focus(self) -> Optional[str]:
        """获取当前注意力焦点。

        Returns:
            关注对象描述，None表示无焦点
        """
        state = self._load_state()
        if state:
            return state.focus
        return self.DEFAULT_FOCUS

    def get_confidence(self) -> float:
        """获取当前信心值。

        Returns:
            信心值 0-1
        """
        state = self._load_state()
        if state:
            return state.confidence_value
        return self.DEFAULT_CONFIDENCE

    def format_state_prompt(self) -> str:
        """格式化状态为prompt注入文本。

        Returns:
            包含四变量状态的prompt文本
        """
        mood = self.get_mood()
        energy = self.get_energy()
        focus = self.get_focus()
        confidence = self.get_confidence()

        # 构建状态描述
        lines = [
            "[当前状态]",
            f"情绪：{mood.label} (valence:{mood.valence}, arousal:{mood.arousal})",
            f"精力：{energy.label} (value: {energy.value})",
            f"注意力：{focus if focus else '无'}",
            f"信心：{self._confidence_label(confidence)} (value: {confidence})",
            "",
            "[状态影响指导]",
        ]

        # 根据状态值生成指导文本
        if mood.arousal < 0.3:
            lines.append("- 当前状态平静，可以正常交流")
        else:
            lines.append("- 当前状态较为兴奋，表达可以更主动")

        if focus:
            lines.append(f"- 你的注意力在{focus}上，相关话题可以深入展开")
        else:
            lines.append("- 无特定注意力焦点，跟随对话方向")

        if confidence > 0.7:
            lines.append("- 你很确定当前方向，表达可以果断")
        elif confidence < 0.3:
            lines.append("- 你不太确定，表达可以更谨慎")
        else:
            lines.append("- 信心中等，正常表达即可")

        return "\n".join(lines)

    def _confidence_label(self, value: float) -> str:
        """根据信心值生成标签。"""
        if value > 0.8:
            return "自信"
        elif value > 0.5:
            return "正常"
        elif value > 0.3:
            return "犹豫"
        else:
            return "迷茫"
