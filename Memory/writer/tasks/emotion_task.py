"""情感快照分析和状态更新检查任务。

使用LLM分析情感快照（category/intensity/valence/arousal/target），
检查是否需要触发即时状态更新。
"""

import json
import logging
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

from Memory.llm.base import BaseLLMClient
from Memory.config.settings import settings
from Memory.storage.experience_store import ExperienceStore, Experience

logger = logging.getLogger(__name__)


@dataclass
class EmotionSnapshot:
    """情感快照数据类。

    Attributes:
        category: 情感类别（joy/sadness/anger/fear/surprise/disinterest/curiosity/neutral）
        intensity: 强度（0-1）
        valence: 效价（-1到1）
        arousal: 唤醒度（0-1）
        target: 情感对象（可选）
    """

    category: str
    intensity: float
    valence: float
    arousal: float
    target: Optional[str] = None


def analyze_emotion_and_check_state(
    experience_id: str,
    dialogue: str,
    state_focus: Optional[str],
    state_mood_label: str,
    llm_client: BaseLLMClient,
    experience_store: ExperienceStore,
    stable_text: str = "",
) -> Optional[EmotionSnapshot]:
    """分析情感快照并检查是否需要触发状态更新。

    Args:
        experience_id: 体验节点ID
        dialogue: 长对话（多轮对话，标注说话者）
        state_focus: 当前注意力焦点（从状态层读取）
        state_mood_label: 当前情绪标签（从状态层读取）
        llm_client: LLM客户端实例
        experience_store: 体验存储实例

    Returns:
        情感快照对象，如果分析失败返回None

    Raises:
        Exception: LLM调用失败时抛出异常（不降级）

    Examples:
        >>> from Memory.llm.factory import LLMFactory
        >>> from Memory.storage.experience_store import experience_store
        >>>
        >>> llm_client = LLMFactory.create_client()
        >>> dialogue = \"\"\"
        ... 张三：今天天气真好
        ... AI：是啊，这样的天气让人心情很愉快
        ... \"\"\"
        >>> emotion = analyze_emotion_and_check_state(
        ...     experience_id="exp_20260331_120000",
        ...     dialogue=dialogue,
        ...     state_focus=None,
        ...     state_mood_label="平静",
        ...     llm_client=llm_client,
        ...     experience_store=experience_store
        ... )
        >>> print(emotion.category)
        joy
    """
    # ========== Step 1: 构建Prompt（包含状态层上下文） ==========
    prompt_template = _load_prompt_template()
    prompt = prompt_template.format(
        dialogue=dialogue,
        state_focus=state_focus if state_focus else "无",
        state_mood_label=state_mood_label,
        ai_personality=stable_text or "无",
        bot_name=settings.writer.bot_name,
    )

    logger.debug(f"Analyzing emotion for {experience_id}")

    # ========== Step 2: 调用LLM分析情感 ==========
    try:
        result_json = llm_client.call_with_retry(
            prompt=prompt,
            response_format="json",
            temperature=0.3,  # 低温度保证分析稳定
            max_tokens=300,
        )

        # 解析JSON (处理可能的dict返回)
        if isinstance(result_json, dict):
            result = result_json
        else:
            result = json.loads(result_json)

        emotion = EmotionSnapshot(
            category=result.get("category", "neutral"),
            intensity=float(result.get("intensity", 0.5)),
            valence=float(result.get("valence", 0.0)),
            arousal=float(result.get("arousal", 0.3)),
            target=result.get("target"),
        )

        logger.debug(
            f"LLM analyzed emotion: {emotion.category}, " f"intensity={emotion.intensity:.2f}"
        )

    except Exception as e:
        logger.error(f"LLM call failed for emotion analysis: {e}")
        # 不降级，直接抛出异常（全部失败策略）
        raise

    # ========== Step 3: 存储到数据库（experiences表） ==========
    # 获取现有Experience对象
    experience = experience_store.get(experience_id)
    if experience is None:
        raise ValueError(f"Experience {experience_id} not found")

    # 更新情感字段
    experience.emotion_category = emotion.category
    experience.emotion_intensity = emotion.intensity
    experience.emotion_valence = emotion.valence
    experience.emotion_arousal = emotion.arousal
    experience.emotion_target = None  # 固定写None（情感对整个体验，不指向具体实体）

    success = experience_store.update(experience)
    if not success:
        raise RuntimeError(f"Failed to update experience {experience_id} with emotion snapshot")

    logger.debug(f"Updated experience {experience_id} with emotion snapshot")

    return emotion


def _load_prompt_template() -> str:
    """加载情感快照分析Prompt模板。

    Returns:
        Prompt模板字符串

    Raises:
        FileNotFoundError: 模板文件不存在
    """
    prompt_path = Path(__file__).parent.parent.parent / "config" / "prompts" / "write_emotion_snapshot.txt"

    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt template not found: {prompt_path}")

    with open(prompt_path, "r", encoding="utf-8") as f:
        template = f.read()

    return template
