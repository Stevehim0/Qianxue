"""状态更新器实现。

双触发更新机制：
1. 即时更新：写入层完成后，emotion.intensity > 0.8 且间隔 > 1分钟
2. 定时更新：每10分钟一次，有新体验则体验驱动，无则基线回归
"""

import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any

from Memory.state import StateUpdater

logger = logging.getLogger(__name__)

# 回归速率（每10分钟回归的比例）
REGRESSION_RATE_MOOD = 0.2       # 情绪回归慢
REGRESSION_RATE_ENERGY = 0.5     # 精力回归快
REGRESSION_RATE_CONFIDENCE = 0.3 # 信心回归中等

# 基线值
BASELINE_VALENCE = 0.0
BASELINE_AROUSAL = 0.3
BASELINE_ENERGY = 0.7
BASELINE_CONFIDENCE = 0.7

# 即时更新参数
IMMEDIATE_INTENSITY_THRESHOLD = 0.8
MIN_UPDATE_INTERVAL = 60  # 秒


class DefaultStateUpdater:
    """状态更新器实现。

    双触发更新：即时（体验驱动）和定时（体验驱动或基线回归）。
    """

    def __init__(self, llm_client=None, state_store=None, experience_store=None, stable_text: str = ""):
        """初始化状态更新器。

        Args:
            llm_client: LLM 客户端实例（延迟创建）
            state_store: StateStore 实例
            experience_store: ExperienceStore 实例
            stable_text: 稳定层文本（作为 LLM 分析参考）
        """
        self._llm_client = llm_client
        self._state_store = state_store
        self._experience_store = experience_store
        self._stable_text = stable_text
        self._last_immediate_update: Optional[float] = None
        self._prompt_template: Optional[str] = None
        self.logger = logging.getLogger(__name__)

    @property
    def llm_client(self):
        if self._llm_client is None:
            from Memory.llm.factory import LLMFactory
            self._llm_client = LLMFactory.create_client()
        return self._llm_client

    @property
    def state_store(self):
        if self._state_store is None:
            from Memory.storage.state_store import state_store
            self._state_store = state_store
        return self._state_store

    @property
    def experience_store(self):
        if self._experience_store is None:
            from Memory.storage.experience_store import experience_store
            self._experience_store = experience_store
        return self._experience_store

    def trigger_immediate_update(self, emotion_snapshot: dict) -> None:
        """即时更新状态。

        条件：intensity > 0.8 且距上次更新 > 1分钟。
        通过后执行体验驱动路径。

        Args:
            emotion_snapshot: 包含 category, intensity, valence, arousal 的情感快照
        """
        intensity = emotion_snapshot.get("intensity", 0)
        if intensity <= IMMEDIATE_INTENSITY_THRESHOLD:
            self.logger.debug(
                f"即时更新跳过: intensity={intensity} <= {IMMEDIATE_INTENSITY_THRESHOLD}"
            )
            return

        now = time.monotonic()
        if self._last_immediate_update and (now - self._last_immediate_update) < MIN_UPDATE_INTERVAL:
            self.logger.debug(
                f"即时更新跳过: 间隔 {now - self._last_immediate_update:.0f}s < {MIN_UPDATE_INTERVAL}s"
            )
            return

        try:
            self._experience_driven_update(emotion_snapshot)
            self._last_immediate_update = time.monotonic()
            self.logger.info(f"即时状态更新完成: triggered by intensity={intensity}")
        except Exception as e:
            self.logger.error(f"即时状态更新失败: {e}")

    def trigger_timed_update(self) -> None:
        """定时更新状态（每10分钟调用一次）。

        有新体验 → 体验驱动路径
        无新体验 → 基线回归路径
        """
        try:
            # 查询过去10分钟的体验
            cutoff = (datetime.now() - timedelta(minutes=10)).isoformat()
            recent_experiences = self.experience_store.get_since(cutoff)

            if recent_experiences:
                self.logger.info(f"定时更新: 发现 {len(recent_experiences)} 条新体验，走体验驱动")
                # 用最近的体验构建情感快照
                latest = recent_experiences[-1]
                emotion_snapshot = {
                    "category": latest.emotion_category or "neutral",
                    "intensity": latest.emotion_intensity or 0.5,
                    "valence": latest.emotion_valence or 0.0,
                    "arousal": latest.emotion_arousal or 0.3,
                }
                self._experience_driven_update(emotion_snapshot, recent_experiences)
            else:
                self.logger.info("定时更新: 无新体验，走基线回归")
                self._baseline_regression_update()

        except Exception as e:
            self.logger.error(f"定时状态更新失败: {e}")

    def _experience_driven_update(
        self,
        emotion_snapshot: dict,
        extra_experiences=None,
    ) -> None:
        """体验驱动路径：用 LLM 评估新状态。

        Args:
            emotion_snapshot: 触发更新的情感快照
            extra_experiences: 额外的近期体验列表（定时更新时传入）
        """
        # 收集当前状态
        state = self.state_store.get()

        # 收集近期体验的 L0 摘要
        experiences_text = self._format_recent_experiences(emotion_snapshot, extra_experiences)

        # 加载 prompt 模板
        template = self._load_prompt_template()
        prompt = template.format(
            current_mood_label=state.mood_label,
            current_valence=state.mood_valence,
            current_arousal=state.mood_arousal,
            current_energy_label=state.energy_label,
            current_energy=state.energy_value,
            current_focus=state.focus or "无",
            current_confidence_label=state.confidence_label,
            current_confidence=state.confidence_value,
            recent_experiences=experiences_text,
            ai_personality=self._stable_text or "无",
        )

        # LLM 评估
        try:
            result = self.llm_client.call_with_retry(
                prompt=prompt,
                response_format="json",
                temperature=0.3,
                max_tokens=300,
            )

            if isinstance(result, dict):
                data = result
            else:
                data = json.loads(result)

            # 更新状态
            self._apply_state_update(data)

        except Exception as e:
            self.logger.warning(f"LLM 状态评估失败，使用情感快照直接更新: {e}")
            # 降级：直接用情感快照的值偏移当前状态
            self._fallback_update(emotion_snapshot)

    def _baseline_regression_update(self) -> None:
        """基线回归路径：无新体验时，状态缓慢回归到基线。"""
        state = self.state_store.get()

        new_valence = state.mood_valence + (BASELINE_VALENCE - state.mood_valence) * REGRESSION_RATE_MOOD
        new_arousal = state.mood_arousal + (BASELINE_AROUSAL - state.mood_arousal) * REGRESSION_RATE_MOOD
        new_energy = state.energy_value + (BASELINE_ENERGY - state.energy_value) * REGRESSION_RATE_ENERGY
        new_confidence = state.confidence_value + (BASELINE_CONFIDENCE - state.confidence_value) * REGRESSION_RATE_CONFIDENCE

        # focus 在无刺激时清空
        new_focus = None

        # 生成标签
        new_mood_label = self.state_store._generate_mood_label(new_valence, new_arousal)
        new_energy_label = self.state_store._generate_energy_label(new_energy)
        new_confidence_label = self.state_store._generate_confidence_label(new_confidence)

        from Memory.storage.state_store import State
        new_state = State(
            mood_valence=round(new_valence, 3),
            mood_arousal=round(new_arousal, 3),
            mood_label=new_mood_label,
            energy_value=round(new_energy, 3),
            energy_label=new_energy_label,
            focus=new_focus,
            confidence_value=round(new_confidence, 3),
            confidence_label=new_confidence_label,
        )

        self.state_store.update_all(new_state)
        self.logger.info(
            f"基线回归: mood={new_mood_label}({new_valence:.2f},{new_arousal:.2f}), "
            f"energy={new_energy_label}({new_energy:.2f}), confidence={new_confidence_label}({new_confidence:.2f})"
        )

    def _apply_state_update(self, data: dict) -> None:
        """将 LLM 评估结果写入数据库。"""
        from Memory.storage.state_store import State

        new_state = State(
            mood_valence=self._clamp(data.get("mood_valence", 0.0), -1, 1),
            mood_arousal=self._clamp(data.get("mood_arousal", 0.3), 0, 1),
            mood_label=data.get("mood_label", "平静"),
            energy_value=self._clamp(data.get("energy", 0.7), 0, 1),
            energy_label=data.get("energy_label", "正常"),
            focus=data.get("focus"),
            confidence_value=self._clamp(data.get("confidence", 0.7), 0, 1),
            confidence_label=data.get("confidence_label", "正常"),
        )

        self.state_store.update_all(new_state)
        self.logger.info(
            f"状态已更新: mood={new_state.mood_label}({new_state.mood_valence:.2f},{new_state.mood_arousal:.2f}), "
            f"energy={new_state.energy_label}({new_state.energy_value:.2f}), "
            f"focus={new_state.focus or '无'}, "
            f"confidence={new_state.confidence_label}({new_state.confidence_value:.2f})"
        )

    def _fallback_update(self, emotion_snapshot: dict) -> None:
        """降级更新：LLM 失败时，直接用情感快照偏移当前状态。"""
        state = self.state_store.get()

        # 情感快照对状态的轻微影响（不突变）
        influence = 0.3  # 影响系数
        emotion_valence = emotion_snapshot.get("valence", 0.0)
        emotion_arousal = emotion_snapshot.get("arousal", 0.3)

        new_valence = state.mood_valence + (emotion_valence - state.mood_valence) * influence
        new_arousal = state.mood_arousal + (emotion_arousal - state.mood_arousal) * influence
        new_mood_label = self.state_store._generate_mood_label(new_valence, new_arousal)

        from Memory.storage.state_store import State
        new_state = State(
            mood_valence=round(new_valence, 3),
            mood_arousal=round(new_arousal, 3),
            mood_label=new_mood_label,
            energy_value=state.energy_value,
            energy_label=state.energy_label,
            focus=state.focus,
            confidence_value=state.confidence_value,
            confidence_label=state.confidence_label,
        )

        self.state_store.update_all(new_state)
        self.logger.info(f"降级状态更新: mood={new_mood_label}")

    def _format_recent_experiences(self, emotion_snapshot: dict, extra_experiences=None) -> str:
        """格式化近期体验为文本。"""
        lines = []

        # 情感快照作为第一条
        lines.append(
            f"触发体验: 情感={emotion_snapshot.get('category', 'neutral')}, "
            f"强度={emotion_snapshot.get('intensity', 0.5):.1f}, "
            f"效价={emotion_snapshot.get('valence', 0.0):.1f}, "
            f"唤醒度={emotion_snapshot.get('arousal', 0.3):.1f}"
        )

        # 额外体验（定时更新时传入）
        if extra_experiences:
            for exp in extra_experiences[:10]:  # 最多10条
                l0 = exp.L0_text or "（无摘要）"
                emotion = f"({exp.emotion_category})" if exp.emotion_category else ""
                lines.append(f"- {l0} {emotion}")

        return "\n".join(lines)

    def _load_prompt_template(self) -> str:
        """延迟加载 prompt 模板。"""
        if self._prompt_template is None:
            path = Path(__file__).parent.parent / "config" / "prompts" / "state_evaluate.txt"
            if path.exists():
                self._prompt_template = path.read_text(encoding="utf-8")
            else:
                # 降级模板
                self._prompt_template = (
                    "根据以下信息评估AI新状态。\n\n"
                    "AI性格:\n{ai_personality}\n\n"
                    "当前: mood={current_mood_label}({current_valence},{current_arousal}), "
                    "energy={current_energy_label}({current_energy}), "
                    "focus={current_focus}, confidence={current_confidence_label}({current_confidence})\n\n"
                    "近期体验:\n{recent_experiences}\n\n"
                    '返回JSON: {{"mood_valence":0,"mood_arousal":0.3,"mood_label":"平静",'
                    '"energy":0.7,"energy_label":"正常","focus":null,'
                    '"confidence":0.7,"confidence_label":"正常"}}'
                )
        return self._prompt_template

    @staticmethod
    def _clamp(value, min_val, max_val):
        """将值限制在范围内。"""
        try:
            return max(min_val, min(max_val, float(value)))
        except (TypeError, ValueError):
            return 0.0
