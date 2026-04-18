"""信息验证任务模块。

验证低置信度的信息边，使用LLM评估边的可靠性。
"""

import logging
from typing import List, Dict, Any
from pathlib import Path
from datetime import datetime

from Memory.storage.experience_store import Experience, ExperienceStore
from Memory.storage.entity_edge_store import EntityEdgeStore, EntityEdge
from Memory.storage.entity_store import EntityStore, entity_store
from Memory.storage.experience_store import experience_store
from Memory.llm.base import BaseLLMClient

logger = logging.getLogger(__name__)


def verify_information(
    experiences: List[Experience],
    llm_client: BaseLLMClient,
    entity_edge_store: EntityEdgeStore,
    entity_store: EntityStore,
    experience_store: ExperienceStore,
    prompt_template_path: str = None,
    max_edges: int = 20,
) -> Dict[str, Any]:
    """验证低置信度的信息边。

    查询confidence<0.5且verify_count=0的边，
    使用LLM评估边的可靠性，更新confidence和verify_count。

    Args:
        experiences: 体验节点列表（用于上下文）
        llm_client: LLM客户端实例
        entity_edge_store: 实体边存储实例
        entity_store: 实体存储实例
        experience_store: 体验存储实例
        prompt_template_path: Prompt模板路径（可选）
        max_edges: 最多处理的边数

    Returns:
        任务结果摘要 {
            'verified_count': 验证的边数,
            'confirmed_count': 确认可靠的边数,
            'rejected_count': 拒绝的边数,
            'total_candidates': 候选边数
        }
    """
    # 加载prompt模板
    if prompt_template_path is None:
        prompt_template_path = (
            Path(__file__).parent.parent.parent / "config" / "prompts" / "consolid_info_verify.txt"
        )

    try:
        with open(prompt_template_path, "r", encoding="utf-8") as f:
            prompt_template = f.read()
    except FileNotFoundError:
        logging.error(f"Prompt模板未找到: {prompt_template_path}")
        return {
            "verified_count": 0,
            "confirmed_count": 0,
            "rejected_count": 0,
            "total_candidates": 0,
        }

    logger = logging.getLogger(__name__)

    # ========== Step 1: 查询低置信度边 ==========
    all_edges = entity_edge_store.get_low_confidence(threshold=0.5, verify_count=0, limit=max_edges)

    total_candidates = len(all_edges)

    if not all_edges:
        logger.info("信息验证任务: 没有低置信度边需要验证")
        return {
            "verified_count": 0,
            "confirmed_count": 0,
            "rejected_count": 0,
            "total_candidates": 0,
        }

    logger.info(f"信息验证任务: 找到{total_candidates}条低置信度边")

    # ========== Step 2: LLM评估每条边 ==========
    verified_count = 0
    confirmed_count = 0
    rejected_count = 0

    for edge in all_edges:
        try:
            # 获取源实体和目标实体
            from_entity = entity_store.get(edge.from_id)
            to_entity = entity_store.get(edge.to_id)

            if not from_entity or not to_entity:
                logger.debug(f"跳过缺失实体的边: {edge.id}")
                continue

            # 构建prompt
            edge_info = f"{from_entity.name} -> {to_entity.name}: {edge.relation}"
            source_info = edge.source if hasattr(edge, "source") and edge.source else "未知来源"

            prompt = prompt_template.format(edge_info=edge_info, source_experiences=source_info)

            # 调用LLM
            result = llm_client.call_json(prompt)
            verified_count += 1

            # 更新边的置信度
            is_reliable = result.get("is_reliable", False)
            new_confidence = result.get("confidence", edge.confidence)

            # 限制confidence在[0, 1]范围
            new_confidence = max(0.0, min(1.0, new_confidence))

            # 创建更新的边对象
            updated_edge = EntityEdge(
                id=edge.id,
                from_id=edge.from_id,
                to_id=edge.to_id,
                relation=edge.relation,
                confidence=new_confidence,
                source=edge.source,
                source_type=edge.source_type,
                verify_count=edge.verify_count + 1,
                verified_at=datetime.now().isoformat(),
            )

            entity_edge_store.update(updated_edge)

            if is_reliable:
                confirmed_count += 1
                logger.info(
                    f"边验证通过: {from_entity.name} -> {to_entity.name} "
                    f"(confidence: {edge.confidence:.2f} -> {new_confidence:.2f})"
                )
            else:
                rejected_count += 1
                logger.info(
                    f"边验证拒绝: {from_entity.name} -> {to_entity.name} "
                    f"(confidence: {edge.confidence:.2f} -> {new_confidence:.2f})"
                )

        except Exception as e:
            logger.error(f"信息验证失败 (edge={edge.id}): {e}", exc_info=True)
            # 继续处理下一条边

    return {
        "verified_count": verified_count,
        "confirmed_count": confirmed_count,
        "rejected_count": rejected_count,
        "total_candidates": total_candidates,
    }
