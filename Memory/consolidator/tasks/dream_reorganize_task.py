"""梦境重组任务模块。

发现记忆间隐藏关联，创建新关系边。
"""

import logging
from typing import List, Dict, Any
from pathlib import Path
from datetime import datetime

from Memory.storage.experience_store import Experience, ExperienceStore
from Memory.storage.experience_edge_store import ExperienceEdgeStore
from Memory.llm.base import BaseLLMClient

logger = logging.getLogger(__name__)


def dream_reorganize(
    memories: List[Experience],
    llm_client: BaseLLMClient,
    experience_store: ExperienceStore,
    edge_store: ExperienceEdgeStore,
) -> Dict[str, Any]:
    """记忆重组任务：发现记忆间隐藏关联，创建新关系边。

    Per D-10: 只创建新关系边，不创建新节点。
    Per D-13: 单个记忆失败记录警告，其他继续。
    Per D-14: 任务内某个记忆处理超时，跳过该记忆。

    Args:
        memories: 待重组的体验节点列表
        llm_client: LLM客户端实例
        experience_store: 体验存储实例（用于读取L0摘要）
        edge_store: 边存储实例（用于创建新边）

    Returns:
        统计信息字典 {
            'processed_count': 处理的节点数,
            'created_edges': 创建的边数,
            'failed_count': 失败的节点数,
            'duration_seconds': 执行时长
        }
    """
    import time

    start_time = time.time()

    processed_count = 0
    created_edges = 0
    failed_count = 0

    # Load dream system prompt (D-21)
    system_prompt_path = (
        Path(__file__).parent.parent.parent / "config" / "prompts" / "dream_system.txt"
    )
    with open(system_prompt_path, "r", encoding="utf-8") as f:
        system_prompt = f.read()

    # Load reorganize task prompt
    task_prompt_path = (
        Path(__file__).parent.parent.parent / "config" / "prompts" / "dream_reorganize.txt"
    )
    with open(task_prompt_path, "r", encoding="utf-8") as f:
        task_template = f.read()

    for i, memory in enumerate(memories):
        try:
            processed_count += 1

            # Find other memories to pair with (pairwise processing)
            for other_memory in memories[i + 1 :]:
                try:
                    # Build prompt
                    prompt = task_template.format(
                        memory_a_L0=memory.L0_text or memory.L3_raw[:200],
                        memory_a_L1=memory.L1_text or "",
                        memory_b_L0=other_memory.L0_text or other_memory.L3_raw[:200],
                        memory_b_L1=other_memory.L1_text or "",
                    )

                    # Call LLM (使用默认30秒超时)
                    response = llm_client.call_json(
                        prompt=prompt,
                        system_prompt=system_prompt,
                    )

                    # Check if LLM found a relationship
                    if response.get("has_relationship", False):
                        # Create edge using ExperienceEdge dataclass
                        from Memory.storage.experience_edge_store import ExperienceEdge

                        edge = ExperienceEdge(
                            from_id=memory.id,
                            to_id=other_memory.id,
                            type=response.get("relationship_type", "dream_reorganized"),
                            weight=response.get("confidence", 0.5),
                            created_at=datetime.now().isoformat(),
                        )

                        edge_id = edge_store.create(edge)

                        if edge_id:
                            created_edges += 1
                            logger.info(
                                f"Dream reorganize: created edge {memory.id} -> {other_memory.id}"
                            )

                except Exception as e:
                    logger.warning(
                        f"Failed to reorganize pair ({memory.id}, {other_memory.id}): {e}"
                    )
                    failed_count += 1
                    continue  # D-14: skip and continue

        except Exception as e:
            logger.error(f"Failed to process memory {memory.id}: {e}")
            failed_count += 1
            continue  # D-13: single memory failure doesn't stop batch

    duration = time.time() - start_time

    return {
        "processed_count": processed_count,
        "created_edges": created_edges,
        "failed_count": failed_count,
        "duration_seconds": duration,
    }
