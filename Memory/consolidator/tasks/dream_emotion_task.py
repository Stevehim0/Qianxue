"""梦境情感加工任务模块。

重新评估记忆的情感色彩，模拟做梦时的情感强化或弱化。
"""

import json
import logging
from typing import List, Dict, Any
from pathlib import Path

from Memory.storage.experience_store import Experience, ExperienceStore
from Memory.llm.base import BaseLLMClient

logger = logging.getLogger(__name__)


def dream_emotion(
    memories: List[Experience], llm_client: BaseLLMClient, experience_store: ExperienceStore
) -> Dict[str, Any]:
    """情感加工任务：重新评估记忆的情感色彩，模拟做梦时的情感强化或弱化。

    Per D-13: 单个记忆失败记录警告，其他继续。
    Per D-14: 任务内某个记忆处理超时，跳过该记忆。

    Args:
        memories: 待情感加工的体验节点列表
        llm_client: LLM客户端实例
        experience_store: 体验存储实例（用于更新emotion_snapshot）

    Returns:
        统计信息字典 {
            'processed_count': 处理的节点数,
            'updated_count': 更新的节点数,
            'failed_count': 失败的节点数,
            'duration_seconds': 执行时长
        }
    """
    import time

    start_time = time.time()

    processed_count = 0
    updated_count = 0
    failed_count = 0

    # Load prompts
    system_prompt_path = (
        Path(__file__).parent.parent.parent / "config" / "prompts" / "dream_system.txt"
    )
    with open(system_prompt_path, "r", encoding="utf-8") as f:
        system_prompt = f.read()

    task_prompt_path = (
        Path(__file__).parent.parent.parent / "config" / "prompts" / "dream_emotion.txt"
    )
    with open(task_prompt_path, "r", encoding="utf-8") as f:
        task_template = f.read()

    for memory in memories:
        try:
            processed_count += 1

            # Build prompt with memory context
            prompt = task_template.format(
                L0_summary=memory.L0_text or memory.L3_raw[:200],
                L1_details=memory.L1_text or "",
                current_emotion=memory.emotion_category or "neutral",
                current_intensity=memory.emotion_intensity or 0.5,
            )

            # Call LLM
            response = llm_client.call_json(
                prompt=prompt, system_prompt=system_prompt
            )

            # Update emotion snapshot
            new_emotion = {
                "category": response.get("emotion_category", memory.emotion_category),
                "intensity": response.get("emotion_intensity", memory.emotion_intensity),
                "valence": response.get("valence", memory.emotion_valence),
                "arousal": response.get("arousal", memory.emotion_arousal),
                "target": response.get("target", memory.emotion_target),
            }

            # Update database using update method with Experience object
            # Note: We need to pass all existing fields to avoid overwriting
            updated_exp = Experience(
                id=memory.id,
                L3_raw=memory.L3_raw,
                L0_text=memory.L0_text,
                L1_text=memory.L1_text,
                L2_text=memory.L2_text,
                L0_embedding=memory.L0_embedding,
                emotion_category=new_emotion["category"],
                emotion_intensity=new_emotion["intensity"],
                emotion_valence=new_emotion["valence"],
                emotion_arousal=new_emotion["arousal"],
                emotion_target=new_emotion["target"],
                context_focus=memory.context_focus,
                context_mood=memory.context_mood,
                context_time_of_day=memory.context_time_of_day,
                context_silence_before=memory.context_silence_before,
                context_task=memory.context_task,
                context_extra=memory.context_extra,
                importance=memory.importance,
                twist_level=memory.twist_level,
                consolidated=memory.consolidated,
                L0_decayed=memory.L0_decayed,
                L1_decayed=memory.L1_decayed,
                L2_decayed=memory.L2_decayed,
                L3_decayed=memory.L3_decayed,
                distorted=memory.distorted,
                created_at=memory.created_at,
            )
            success = experience_store.update(updated_exp)

            if success:
                updated_count += 1
                logger.info(f"Dream emotion: updated {memory.id} to {new_emotion['category']}")

        except Exception as e:
            logger.warning(f"Failed to process emotion for {memory.id}: {e}")
            failed_count += 1
            continue  # D-13: skip and continue

    duration = time.time() - start_time

    return {
        "processed_count": processed_count,
        "updated_count": updated_count,
        "failed_count": failed_count,
        "duration_seconds": duration,
    }
