"""实体关系发现任务模块。

本模块实现实体之间的逻辑关系和联想关系发现：
- 基于实体类型、名称、属性进行语义判断
- 使用LLM识别实体间的逻辑关系（因果、包含、依存等）
- 使用LLM识别实体间的联想关系（相关、相似、关联等）
- 创建或更新实体层边（entity_edges）
"""

import logging
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Tuple
from pathlib import Path
from itertools import combinations

from Memory.storage.entity_store import Entity, EntityStore
from Memory.storage.entity_edge_store import EntityEdge, EntityEdgeStore
from Memory.llm.base import BaseLLMClient
from Memory.config.settings import settings

logger = logging.getLogger(__name__)


def discover_entity_relations(
    entities: List[Entity],
    llm_client: BaseLLMClient,
    entity_store: EntityStore,
    entity_edge_store: EntityEdgeStore,
    prompt_template_path: str = None,
    top_k_entities: int = 50,
    sample_pairs_count: int = 100,
    max_workers: int = 4,
) -> Dict[str, Any]:
    """发现实体之间的逻辑关系和联想关系。

    流程：
    1. 按confidence排序，选取top-k实体
    2. 从top-k实体中随机抽取N对实体
    3. 使用ThreadPoolExecutor并行处理实体对
    4. LLM判断每对实体是否有关系（逻辑关系或联想关系）
    5. 创建entity_edges记录确认的关系

    Args:
        entities: 实体节点列表
        llm_client: LLM客户端实例
        entity_store: 实体存储实例
        entity_edge_store: 实体边存储实例
        prompt_template_path: Prompt模板路径（可选）
        top_k_entities: 选取的高频实体数量
        sample_pairs_count: 随机抽取的实体对数量
        max_workers: 并行处理的工作线程数

    Returns:
        任务结果摘要 {
            'evaluated_pairs': 评估的实体对数,
            'created_edges': 创建的边数,
            'logical_relations': 逻辑关系数,
            'associative_relations': 联想关系数,
            'total_candidates': 候选实体对数
        }
    """
    # 加载prompt模板
    if prompt_template_path is None:
        prompt_template_path = (
            Path(__file__).parent.parent.parent
            / "config"
            / "prompts"
            / "consolid_entity_relations.txt"
        )

    try:
        with open(prompt_template_path, "r", encoding="utf-8") as f:
            prompt_template = f.read()
    except FileNotFoundError:
        logging.error(f"Prompt模板未找到: {prompt_template_path}")
        return {
            "evaluated_pairs": 0,
            "created_edges": 0,
            "logical_relations": 0,
            "associative_relations": 0,
            "total_candidates": 0,
        }

    logger = logging.getLogger(__name__)

    # ========== Step 1: 按confidence排序，选取top-k实体 ==========
    entities_with_confidence = [e for e in entities if e.confidence is not None]
    entities_with_confidence.sort(key=lambda e: e.confidence, reverse=True)

    top_entities = entities_with_confidence[:top_k_entities]

    if len(top_entities) < 2:
        logger.info(f"有效实体少于2个，跳过实体关系发现")
        return {
            "evaluated_pairs": 0,
            "created_edges": 0,
            "logical_relations": 0,
            "associative_relations": 0,
            "total_candidates": 0,
        }

    logger.info(
        f"实体关系发现: 从{len(entities)}个实体中选取top-{len(top_entities)}个高频实体"
    )

    # ========== Step 2: 生成所有可能的实体对并随机采样 ==========
    all_pairs = list(combinations(top_entities, 2))

    if len(all_pairs) == 0:
        logger.info("没有实体对可处理")
        return {
            "evaluated_pairs": 0,
            "created_edges": 0,
            "logical_relations": 0,
            "associative_relations": 0,
            "total_candidates": 0,
        }

    # 随机采样
    sampled_pairs = random.sample(all_pairs, min(sample_pairs_count, len(all_pairs)))

    logger.info(
        f"实体关系发现: 从{len(all_pairs)}个候选对中随机抽取{len(sampled_pairs)}对进行评估"
    )

    # ========== Step 3: 并行处理实体对 ==========
    created_edges = []
    evaluated_count = 0
    logical_count = 0
    associative_count = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # 提交所有任务
        futures = {
            executor.submit(
                _evaluate_entity_pair,
                entity_a,
                entity_b,
                llm_client,
                prompt_template,
                entity_edge_store,
            ): (entity_a, entity_b)
            for entity_a, entity_b in sampled_pairs
        }

        # 收集结果
        for future in as_completed(futures):
            entity_a, entity_b = futures[future]
            try:
                result = future.result(timeout=30)  # 每对30秒超时（从60改为30）
                evaluated_count += 1

                if result.get("has_relation", False):
                    edge_info = result.get("edge_info")
                    if edge_info:
                        created_edges.append(edge_info)

                        relation_type = result.get("relation_type", "unknown")
                        if relation_type == "logical":
                            logical_count += 1
                        elif relation_type == "associative":
                            associative_count += 1

                        logger.info(
                            f"发现实体关系: {entity_a.name} <-> {entity_b.name} "
                            f"(类型={relation_type}, 关系={result.get('relation', 'N/A')})"
                        )

            except Exception as e:
                error_type = type(e).__name__
                logger.error(
                    f"评估实体对失败 ({entity_a.name}, {entity_b.name}): {error_type}: {e}"
                )
                # 不要因为单个失败就中断，继续处理下一对

    logger.info(
        f"实体关系发现完成: 评估{evaluated_count}对, "
        f"创建{len(created_edges)}条边 (逻辑={logical_count}, 联想={associative_count})"
    )

    return {
        "evaluated_pairs": evaluated_count,
        "created_edges": len(created_edges),
        "logical_relations": logical_count,
        "associative_relations": associative_count,
        "total_candidates": len(all_pairs),
    }


def _evaluate_entity_pair(
    entity_a: Entity,
    entity_b: Entity,
    llm_client: BaseLLMClient,
    prompt_template: str,
    entity_edge_store: EntityEdgeStore,
) -> Dict[str, Any]:
    """评估单个实体对是否存在关系。

    Args:
        entity_a: 实体A
        entity_b: 实体B
        llm_client: LLM客户端实例
        prompt_template: Prompt模板
        entity_edge_store: 实体边存储实例

    Returns:
        评估结果字典 {
            'has_relation': 是否有关系,
            'relation_type': 关系类型（logical/associative/none）,
            'relation': 关系描述,
            'confidence': 置信度,
            'edge_info': EntityEdge对象（如果has_relation=True）
        }
    """
    # 构建实体描述
    entity_a_desc = _build_entity_description(entity_a)
    entity_b_desc = _build_entity_description(entity_b)

    # 构建prompt
    prompt = prompt_template.format(
        entity_a_name=entity_a.name,
        entity_a_type=entity_a.type,
        entity_a_desc=entity_a_desc,
        entity_b_name=entity_b.name,
        entity_b_type=entity_b.type,
        entity_b_desc=entity_b_desc,
    )

    try:
        # 调用LLM
        result = llm_client.call_json(prompt)

        has_relation = result.get("has_relation", False)
        if not has_relation:
            return {"has_relation": False, "relation_type": "none"}

        relation_type = result.get("relation_type", "unknown")  # logical / associative
        relation = result.get("relation", "相关")
        confidence = float(result.get("confidence", 0.5))

        # 只创建高置信度的边
        if confidence < 0.5:
            return {
                "has_relation": False,
                "relation_type": "none",
                "reason": "confidence_too_low",
            }

        # 检查是否已存在相同的边
        existing_edges = entity_edge_store.get_by_from(entity_a.id)
        for existing in existing_edges:
            if existing.to_id == entity_b.id and existing.relation == relation:
                # 边已存在，更新置信度
                if confidence > existing.confidence:
                    entity_edge_store.update_confidence(existing.id, confidence)
                return {
                    "has_relation": True,
                    "relation_type": relation_type,
                    "relation": relation,
                    "confidence": confidence,
                    "edge_info": None,  # 已存在，不创建新边
                }

        # 创建新边
        from datetime import datetime

        edge = EntityEdge(
            from_id=entity_a.id,
            to_id=entity_b.id,
            relation=relation,
            confidence=confidence,
            source="consolidation",
            source_type="inferred",
            created_at=datetime.now().isoformat(),
        )

        edge_id = entity_edge_store.create(edge)

        return {
            "has_relation": True,
            "relation_type": relation_type,
            "relation": relation,
            "confidence": confidence,
            "edge_info": edge,
        }

    except ValueError as json_error:
        # JSON解析失败
        logger.warning(f"JSON解析失败 ({entity_a.name}, {entity_b.name}): {json_error}")
        return {"has_relation": False, "relation_type": "parse_error", "error": str(json_error)}
    except Exception as e:
        error_type = type(e).__name__
        logger.error(f"LLM评估失败 ({entity_a.name}, {entity_b.name}): {error_type}: {e}")
        return {"has_relation": False, "relation_type": "error", "error": f"{error_type}: {e}"}


def _build_entity_description(entity: Entity) -> str:
    """构建实体的描述信息。

    Args:
        entity: 实体对象

    Returns:
        实体描述字符串
    """
    parts = []

    # 类型
    if entity.type:
        parts.append(f"类型：{entity.type}")

    # 属性
    if entity.properties:
        prop_strs = []
        for key, value in entity.properties.items():
            if key.startswith("_"):
                continue  # 跳过内部字段
            if isinstance(value, (str, int, float, bool)):
                prop_strs.append(f"{key}：{value}")
        if prop_strs:
            parts.append("属性：" + "，".join(prop_strs))

    return "；".join(parts) if parts else "无详细信息"
