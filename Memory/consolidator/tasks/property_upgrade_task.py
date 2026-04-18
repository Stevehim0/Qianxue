"""属性升级扫描任务模块。

检查实体属性是否在多次体验中被验证，升级到实体档案。
"""

import logging
import uuid
from typing import List, Dict, Any, Optional
from pathlib import Path
from datetime import datetime

from Memory.storage.experience_store import Experience
from Memory.storage.entity_store import EntityStore, Entity
from Memory.storage.entity_edge_store import EntityEdgeStore, EntityEdge
from Memory.llm.base import BaseLLMClient
from Memory.config.settings import settings
from Memory.llm.utils import parse_json

logger = logging.getLogger(__name__)


def scan_property_upgrade(
    experiences: List[Experience],
    llm_client: BaseLLMClient,
    entity_store: EntityStore,
    prompt_template_path: str = None,
) -> Dict[str, Any]:
    """扫描并升级实体属性。

    流程：
    1. 从体验中提取涉及的实体
    2. 对每个实体，检查其属性是否在多次体验中被验证
    3. LLM评估属性是否应该升级
    4. 更新实体的properties字段

    Args:
        experiences: 体验节点列表
        llm_client: LLM客户端实例
        entity_store: 实体存储实例
        prompt_template_path: Prompt模板路径（可选）

    Returns:
        任务结果摘要 {
            'upgraded_count': 升级的实体数,
            'evaluated_count': 评估的实体数,
            'skipped_count': 跳过的实体数
        }
    """
    # 加载prompt模板
    if prompt_template_path is None:
        prompt_template_path = (
            Path(__file__).parent.parent.parent
            / "config"
            / "prompts"
            / "consolid_property_upgrade.txt"
        )

    try:
        with open(prompt_template_path, "r", encoding="utf-8") as f:
            prompt_template = f.read()
    except FileNotFoundError:
        logging.error(f"Prompt模板未找到: {prompt_template_path}")
        return {"upgraded_count": 0, "evaluated_count": 0, "skipped_count": 0}

    logger = logging.getLogger(__name__)
    threshold = settings.consolidation.property_upgrade_threshold

    # ========== Step 1: 调用EntityStore的get_shared_properties()方法 ==========
    # 使用Task 1创建的方法，避免重复实现扫描逻辑
    shared_properties_list = entity_store.get_shared_properties(threshold=threshold)

    # 转换为字典格式以便后续使用：{property_name:property_value: count}
    shared_properties = {}
    for prop_item in shared_properties_list:
        key = f"{prop_item['property_name']}:{prop_item['property_value']}"
        shared_properties[key] = prop_item["count"]

    logger.info(f"找到{len(shared_properties)}个共享属性(>={threshold}次)")

    # ========== Step 2: 从体验中提取实体ID ==========
    # Phase 7简化处理：我们直接扫描所有实体
    # 完整版本应该从cross_edges中提取相关实体（Phase 9优化）
    all_entities = entity_store.get_all()

    # 过滤：只处理有properties的实体
    entities_with_properties = [e for e in all_entities if e.properties and len(e.properties) > 0]

    logger.info(f"属性升级扫描: {len(entities_with_properties)}个实体有属性")

    # ========== Step 3: 对每个实体评估是否需要升级 ==========
    upgraded_count = 0
    evaluated_count = 0
    skipped_count = 0

    for entity in entities_with_properties:
        try:
            # 检查实体是否有共享属性
            entity_shared_props = []
            for prop_name, prop_value in entity.properties.items():
                if isinstance(prop_value, str):
                    key = f"{prop_name}:{prop_value}"
                    if key in shared_properties:
                        entity_shared_props.append((prop_name, prop_value))

            if not entity_shared_props:
                skipped_count += 1
                continue

            # 对每个共享属性进行LLM评估
            entity_updated = False

            for prop_name, prop_value in entity_shared_props:
                # 构建prompt（简化版本）
                # 注意：完整版本应该包含该实体相关的体验内容
                # Phase 7简化为使用属性出现次数作为上下文
                prompt = prompt_template.format(
                    entity_name=entity.name,
                    current_properties=entity.properties,
                    new_experiences=f"属性{prop_name}在{shared_properties[f'{prop_name}:{prop_value}']}次体验中被验证",
                    property_name=prop_name,
                )

                try:
                    # 使用call_with_retry并指定response_format="json"
                    result_text = llm_client.call_with_retry(prompt=prompt, response_format="json")

                    # 如果返回的是字符串，解析JSON
                    if isinstance(result_text, str):
                        result = parse_json(result_text)
                    else:
                        result = result_text

                    evaluated_count += 1

                    # 检查是否应该升级
                    if result.get("should_upgrade", False):
                        new_value = result.get("new_value")

                        if new_value is not None:
                            # 更新属性
                            new_properties = entity.properties.copy()
                            new_properties[prop_name] = new_value

                            # 写回数据库
                            success = entity_store.update_properties(
                                entity_id=entity.id, properties=new_properties
                            )

                            if success:
                                entity_updated = True
                                logger.info(
                                    f"属性升级: {entity.name}.{prop_name} "
                                    f"={prop_value} -> {new_value}"
                                )

                except Exception as e:
                    logger.warning(f"属性评估失败 ({entity.name}.{prop_name}): {e}")

            if entity_updated:
                upgraded_count += 1

        except Exception as e:
            logger.error(f"属性升级处理失败 ({entity.id}): {e}", exc_info=True)

    return {
        "upgraded_count": upgraded_count,
        "evaluated_count": evaluated_count,
        "skipped_count": skipped_count,
    }


def upgrade_shared_attributes(
    entity_store: EntityStore,
    edge_store: EntityEdgeStore,
    embedding_service,
    threshold: int = 3,
) -> Dict[str, Any]:
    """将高频共享的属性值升级为独立实体。

    这是D-05决策的核心实现："是属性，才能升级"。

    流程：
    1. 检测共享属性 - 调用entity_store.get_shared_properties(threshold)
    2. 升级属性值为实体 - 将高频共享的属性值创建为独立实体
    3. 创建关系边 - 建立原实体和新实体的关系边

    Args:
        entity_store: Entity存储实例
        edge_store: EntityEdge存储实例
        embedding_service: Embedding服务实例
        threshold: 最小共享次数（默认3）

    Returns:
        任务结果摘要 {
            'promoted_count': 升级的实体数,
            'edges_created_count': 创建的边数,
            'skipped_count': 跳过的属性值数,
            'failed_count': 失败的属性升级数
        }
    """
    logger.info(f"开始扫描共享属性，threshold={threshold}")

    # ========== Step 1: 检测共享属性 ==========
    shared_properties = entity_store.get_shared_properties(threshold=threshold)
    logger.info(f"找到{len(shared_properties)}个共享属性")

    promoted_count = 0
    edges_created_count = 0
    skipped_count = 0
    failed_count = 0

    # ========== Step 2: 升级属性值为实体 ==========
    for prop in shared_properties:
        prop_name = prop["property_name"]  # 如"位置"
        prop_value = prop["property_value"]  # 如"云南"
        entity_ids = prop["entities"]  # 原实体ID列表
        count = prop["count"]  # 共享次数

        try:
            # 过滤：空值检查
            if not prop_value or (isinstance(prop_value, str) and prop_value.strip() == ""):
                logger.warning(f"跳过空值属性: {prop_name}:{prop_value}")
                skipped_count += 1
                continue

            # 检查实体是否已存在（同名实体复用）
            existing_entity = entity_store.get_by_name(prop_value)
            if existing_entity:
                # 实体已存在，复用已有实体
                new_entity_id = existing_entity.id
                logger.debug(f"实体'{prop_value}'已存在，复用已有实体")
            else:
                # 创建新实体（属性值升级为实体）
                entity_type = _infer_entity_type_from_attribute(prop_name)
                new_entity = Entity(
                    id=str(uuid.uuid4()),
                    name=prop_value,  # 属性值作为实体名
                    type=entity_type,
                    properties={
                        "描述": f"由{count}个实体共享的{prop_name}属性",
                        "升级来源": "属性升级任务",
                    },
                    embedding=embedding_service.encode(prop_value),
                    source="consolidation",
                    confidence=0.8,
                    created_at=datetime.now().isoformat(),
                )

                new_entity_id = entity_store.create(new_entity)
                promoted_count += 1
                logger.info(f"升级属性'{prop_name}:{prop_value}'为实体{new_entity_id}")

            # ========== Step 3: 创建关系边 ==========
            for source_entity_id in entity_ids:
                edge = EntityEdge(
                    from_id=source_entity_id,
                    to_id=new_entity_id,
                    relation=prop_name,  # 使用属性名作为关系类型
                    confidence=0.8,
                    source="attribute_upgrade",
                    source_type="consolidation",
                    created_at=datetime.now().isoformat(),
                )

                edge_store.create(edge)
                edges_created_count += 1

            logger.debug(
                f"创建了{len(entity_ids)}条关系边: "
                f"{[eid[:8]+'...' for eid in entity_ids]} -> {prop_value}"
            )

        except Exception as e:
            logger.error(
                f"升级共享属性失败 {prop_name}:{prop_value}: {e}", exc_info=True
            )
            failed_count += 1
            continue

    logger.info(
        f"升级完成: promoted={promoted_count}, "
        f"edges={edges_created_count}, skipped={skipped_count}, failed={failed_count}"
    )

    return {
        "promoted_count": promoted_count,
        "edges_created_count": edges_created_count,
        "skipped_count": skipped_count,
        "failed_count": failed_count,
    }


def _infer_entity_type_from_attribute(attribute_name: str) -> str:
    """从属性名推断实体类型。

    映射规则：
    - "位置"/"位于" → "location"
    - "职业"/"工作于" → "organization"
    - "关系" → "person"
    - 其他 → "unknown"

    Args:
        attribute_name: 属性名

    Returns:
        实体类型字符串
    """
    mapping = {
        "位置": "location",
        "位于": "location",
        "职业": "organization",
        "工作于": "organization",
        "关系": "person",
    }
    return mapping.get(attribute_name, "unknown")
