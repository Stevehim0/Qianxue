"""梦境扭曲任务模块。

按重要度×时间远近组合决定扭曲程度，修改记忆表征。
"""

import json
import logging
from typing import List, Dict, Any
from pathlib import Path
from datetime import datetime

from Memory.storage.experience_store import Experience, ExperienceStore
from Memory.llm.base import BaseLLMClient

logger = logging.getLogger(__name__)


def dream_distort(
    memories: List[Experience], llm_client: BaseLLMClient, experience_store: ExperienceStore
) -> Dict[str, Any]:
    """记忆扭曲任务：按重要度×时间远近组合决定扭曲程度，修改记忆表征。

    Per D-03: 扭曲边界：L0可改，L1可微调，L2可模糊细节，L3绝对不改
    Per D-12: 记忆扭曲通过experiences表distorted字段追溯
    Per D-15: L3绝对不改（铁律）

    Args:
        memories: 待扭曲的体验节点列表
        llm_client: LLM客户端实例
        experience_store: 体验存储实例（用于更新L0/L1/L2/distorted）

    Returns:
        统计信息字典 {
            'processed_count': 处理的节点数,
            'distorted_count': 扭曲的节点数,
            'failed_count': 失败的节点数,
            'duration_seconds': 执行时长
        }
    """
    import time

    start_time = time.time()

    processed_count = 0
    distorted_count = 0
    failed_count = 0

    # Load prompts
    system_prompt_path = (
        Path(__file__).parent.parent.parent / "config" / "prompts" / "dream_system.txt"
    )
    with open(system_prompt_path, "r", encoding="utf-8") as f:
        system_prompt = f.read()

    task_prompt_path = (
        Path(__file__).parent.parent.parent / "config" / "prompts" / "dream_distort.txt"
    )
    with open(task_prompt_path, "r", encoding="utf-8") as f:
        task_template = f.read()

    for memory in memories:
        try:
            processed_count += 1

            # Calculate time distance
            time_distance_days = (datetime.now() - datetime.fromisoformat(memory.created_at)).days

            # Build prompt with distortion context
            prompt = task_template.format(
                L0_text=memory.L0_text or "",
                L1_text=memory.L1_text or "",
                L2_text=memory.L2_text or "",
                importance=memory.importance or 0.5,
                time_distance_days=time_distance_days,
                emotion_intensity=memory.emotion_intensity or 0.5,
            )

            # Call LLM
            response = llm_client.call_json(
                prompt=prompt, system_prompt=system_prompt
            )

            # Extract distorted values
            new_L0 = response.get("L0_text", memory.L0_text)
            new_L1 = response.get("L1_text", memory.L1_text)
            new_L2 = response.get("L2_text", memory.L2_text)

            # Create audit trail (D-12)
            distorted_record = {
                "type": "dream_distortion",
                "timestamp": datetime.now().isoformat(),
                "task": "dream_distort",
                "original_values": {
                    "L0_text": memory.L0_text or "",
                    "L1_text": memory.L1_text or "",
                    "L2_text": memory.L2_text or "",
                },
                "distorted_values": {"L0_text": new_L0, "L1_text": new_L1, "L2_text": new_L2},
                "metadata": {
                    "importance": memory.importance or 0.5,
                    "time_distance_days": time_distance_days,
                    "emotion_intensity": memory.emotion_intensity or 0.5,
                },
            }

            # Update database (L3_raw NEVER included - D-15)
            success = experience_store.update_distorted(
                experience_id=memory.id,
                L0_text=new_L0,
                L1_text=new_L1,
                L2_text=new_L2,
                distorted=json.dumps(distorted_record, ensure_ascii=False),
            )

            if success:
                distorted_count += 1
                logger.info(
                    f"Dream distort: distorted {memory.id}, "
                    f"importance={memory.importance:.2f}, "
                    f"time_distance={time_distance_days}d"
                )

        except Exception as e:
            logger.warning(f"Failed to distort {memory.id}: {e}")
            failed_count += 1
            continue

    duration = time.time() - start_time

    return {
        "processed_count": processed_count,
        "distorted_count": distorted_count,
        "failed_count": failed_count,
        "duration_seconds": duration,
    }
