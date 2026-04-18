"""梦境模拟推演任务模块。

基于现有记忆推演新场景，创建新体验节点。
"""

import logging
from typing import List, Dict, Any
from pathlib import Path
from datetime import datetime

from Memory.storage.experience_store import Experience, ExperienceStore
from Memory.llm.base import BaseLLMClient

logger = logging.getLogger(__name__)


def dream_simulate(
    memories: List[Experience], llm_client: BaseLLMClient, experience_store: ExperienceStore
) -> Dict[str, Any]:
    """模拟推演任务：基于现有记忆推演新场景，创建新体验节点。

    Per D-09: 梦境节点标记source_type='dream', confidence=0.3, importance×0.5
    Per D-11: L0记录推演内容，L3标注'这是推演'

    Args:
        memories: 作为推演基础的体验节点列表
        llm_client: LLM客户端实例
        experience_store: 体验存储实例（用于创建新节点）

    Returns:
        统计信息字典 {
            'processed_count': 处理的节点数,
            'created_count': 创建的节点数,
            'failed_count': 失败的节点数,
            'duration_seconds': 执行时长
        }
    """
    import time

    start_time = time.time()

    processed_count = 0
    created_count = 0
    failed_count = 0

    # Load prompts
    system_prompt_path = (
        Path(__file__).parent.parent.parent / "config" / "prompts" / "dream_system.txt"
    )
    with open(system_prompt_path, "r", encoding="utf-8") as f:
        system_prompt = f.read()

    task_prompt_path = (
        Path(__file__).parent.parent.parent / "config" / "prompts" / "dream_simulate.txt"
    )
    with open(task_prompt_path, "r", encoding="utf-8") as f:
        task_template = f.read()

    for memory in memories:
        try:
            processed_count += 1

            # Build prompt with memory context
            prompt = task_template.format(
                original_L0=memory.L0_text or memory.L3_raw[:200],
                original_L1=memory.L1_text or "",
                importance=memory.importance or 0.5,
            )

            # Call LLM with timeout
            response = llm_client.call_json(
                prompt=prompt, system_prompt=system_prompt
            )

            # Extract simulation content
            simulated_L0 = response.get("simulated_L0", "")
            simulated_L1 = response.get("simulated_L1", "")
            simulated_L2 = response.get("simulated_L2", "")

            # Create dream node (D-09, D-11)
            now = datetime.now()
            dream_id = f"dream_{now.strftime('%Y%m%d_%H%M%S_%f')}"

            # L3 must include '[梦境推演]' prefix (D-11)
            dream_L3 = f"[梦境推演] 基于 {memory.id} 的模拟场景: {simulated_L0}"

            # Importance = base_importance × 0.5 (D-09)
            dream_importance = (memory.importance or 0.5) * 0.5

            # Create new experience node
            dream_exp = Experience(
                id=dream_id,
                L3_raw=dream_L3,
                L0_text=simulated_L0,
                L1_text=simulated_L1,
                L2_text=simulated_L2,
                importance=dream_importance,
                source_type="dream",  # D-09
                confidence=0.3,  # D-09
                created_at=now.isoformat(),
            )

            success = experience_store.create(dream_exp)

            if success:
                created_count += 1
                logger.info(
                    f"Dream simulate: created {dream_id}, "
                    f"importance={dream_importance:.2f}, "
                    f"based_on={memory.id}"
                )

        except Exception as e:
            logger.warning(f"Failed to simulate from {memory.id}: {e}")
            failed_count += 1
            continue

    duration = time.time() - start_time

    return {
        "processed_count": processed_count,
        "created_count": created_count,
        "failed_count": failed_count,
        "duration_seconds": duration,
    }
