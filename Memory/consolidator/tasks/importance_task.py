"""重要性估值任务模块。

计算体验节点的重要性评分：importance = novelty × consequence × connectivity × emotion
"""

import logging
import math
from typing import List, Dict, Any
from pathlib import Path

from Memory.storage.experience_store import Experience
from Memory.storage.experience_store import ExperienceStore
from Memory.storage.experience_edge_store import ExperienceEdgeStore
from Memory.llm.base import BaseLLMClient
from Memory.llm.utils import parse_json

logger = logging.getLogger(__name__)


def calculate_importance(
    experiences: List[Experience],
    llm_client: BaseLLMClient,
    experience_store: ExperienceStore,
    experience_edge_store: ExperienceEdgeStore,
    prompt_template_path: str = None,
) -> Dict[str, Any]:
    """计算体验节点的重要性评分。

    重要性公式：importance = novelty × consequence × connectivity × emotion

    因子说明：
    - novelty: 新颖度（0-1），LLM评估
    - consequence: 后果影响（0-1），LLM评估
    - connectivity: 连接度（0-1），基于边数量归一化
    - emotion: 情感强度（0-1），基于emotion_intensity

    Args:
        experiences: 待处理的体验节点列表
        llm_client: LLM客户端实例
        experience_store: 体验存储实例
        experience_edge_store: 体验边存储实例
        prompt_template_path: Prompt模板路径（可选）

    Returns:
        任务结果摘要 {
            'updated_count': 更新的节点数,
            'total_count': 总节点数,
            'avg_importance': 平均重要性
        }
    """
    # 加载prompt模板（用于novelty和consequence评估）
    if prompt_template_path is None:
        # 使用默认的评估prompt
        prompt_template = """你是一个记忆重要性评估系统。

评估以下体验的重要程度：

体验摘要：{l0_summary}
完整内容：{l3_full}

评估维度：
1. 新颖度（novelty）：这段经历是否包含新的信息、技能或体验？
2. 后果影响（consequence）：这段经历对AI未来有何影响？

返回JSON：
```json
{{
  "novelty": 0.0-1.0,
  "consequence": 0.0-1.0,
  "reason": "简要说明"
}}
```
"""
    else:
        with open(prompt_template_path, "r", encoding="utf-8") as f:
            prompt_template = f.read()

    logger = logging.getLogger(__name__)
    updated_count = 0
    total_importance = 0.0

    for exp in experiences:
        try:
            # ========== 因子1和2: LLM评估novelty和consequence ==========
            prompt = prompt_template.format(
                l0_summary=exp.L0_text or exp.L3_raw[:200], l3_full=exp.L3_raw
            )

            llm_result_text = llm_client.call_with_retry(prompt=prompt, response_format="text")

            try:
                llm_result = parse_json(llm_result_text)
            except ValueError as e:
                logger.error(f"LLM返回JSON解析失败 (exp={exp.id}): {e}")
                # 使用默认值继续处理
                novelty = 0.5
                consequence = 0.5
            else:
                novelty = llm_result.get("novelty", 0.5)
                consequence = llm_result.get("consequence", 0.5)

            # 限制在[0, 1]范围
            novelty = max(0.0, min(1.0, novelty))
            consequence = max(0.0, min(1.0, consequence))

            # ========== 因子3: connectivity（基于边数量） ==========
            edges = experience_edge_store.get_by_from(exp.id)
            edge_count = len(edges)

            # 归一化：使用log平滑，假设最大约20条边
            if edge_count == 0:
                connectivity = 0.3  # 无边的节点有基础连接度
            else:
                connectivity = min(1.0, 0.3 + math.log10(edge_count + 1) / math.log10(20))

            # ========== 因子4: emotion（基于情感强度） ==========
            if exp.emotion_intensity is not None:
                emotion = abs(exp.emotion_intensity)  # 取绝对值
            else:
                emotion = 0.5  # 默认中等情感

            # ========== 计算最终重要性 ==========
            importance = novelty * consequence * connectivity * emotion

            # 更新到数据库
            success = experience_store.update_importance(
                experience_id=exp.id, importance=importance
            )

            if success:
                updated_count += 1
                total_importance += importance
                logger.info(
                    f"Importance计算: {exp.id} = {importance:.3f} "
                    f"(n={novelty:.2f}, c={consequence:.2f}, "
                    f"conn={connectivity:.2f}, emo={emotion:.2f})"
                )
            else:
                logger.warning(f"Importance更新失败: {exp.id}")

        except Exception as e:
            logger.error(f"Importance计算失败 (exp={exp.id}): {e}", exc_info=True)
            # 继续处理下一个节点

    avg_importance = total_importance / updated_count if updated_count > 0 else 0.0

    return {
        "updated_count": updated_count,
        "total_count": len(experiences),
        "avg_importance": avg_importance,
    }
