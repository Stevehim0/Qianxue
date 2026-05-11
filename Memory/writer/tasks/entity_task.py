"""实体识别和边创建任务。

使用LLM从对话中识别实体（人/地点/概念/事件/技能等）并提取属性，
创建实体节点，创建跨层边（体验→实体）。
"""

import json
import logging
import uuid
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any

from Memory.llm.base import BaseLLMClient
from Memory.config.settings import settings
from Memory.embedding.model import EmbeddingService
from Memory.storage.entity_store import EntityStore, Entity
from Memory.storage.cross_edge_store import CrossEdgeStore, CrossEdge

logger = logging.getLogger(__name__)


def recognize_entities_and_create_edges(
    experience_id: str,
    dialogue: str,
    llm_client: BaseLLMClient,
    embedding_service: EmbeddingService,
    entity_store: EntityStore,
    cross_edge_store: CrossEdgeStore,
) -> List[str]:
    """识别实体并创建跨层边。

    Args:
        experience_id: 体验节点ID
        dialogue: 长对话（多轮对话，标注说话者）
        llm_client: LLM客户端实例
        embedding_service: Embedding服务实例
        entity_store: 实体存储实例
        cross_edge_store: 跨层边存储实例

    Returns:
        实体ID列表

    Raises:
        Exception: LLM调用失败时抛出异常（不降级）

    Examples:
        >>> from Memory.llm.factory import LLMFactory
        >>> from Memory.embedding.model import embedding_service
        >>> from Memory.storage.entity_store import entity_store
        >>> from Memory.storage.cross_edge_store import cross_edge_store
        >>>
        >>> llm_client = LLMFactory.create_client()
        >>> dialogue = "张三：我想学Python\\nAI：好的..."
        >>> entity_ids = recognize_entities_and_create_edges(
        ...     experience_id="exp_20260331_120000",
        ...     dialogue=dialogue,
        ...     llm_client=llm_client,
        ...     embedding_service=embedding_service,
        ...     entity_store=entity_store,
        ...     cross_edge_store=cross_edge_store
        ... )
        >>> print(entity_ids)
        ['123', '456']
    """
    # ========== Step 1: 构建Prompt ==========
    prompt_template = _load_prompt_template()
    prompt = prompt_template.format(dialogue=dialogue)

    logger.debug(f"Recognizing entities for {experience_id}")

    # ========== Step 2: 调用LLM识别实体 ==========
    try:
        logger.debug(f"Calling LLM for entity recognition, dialogue length: {len(dialogue)}")
        result_json = llm_client.call_with_retry(
            prompt=prompt,
            response_format="json",
            temperature=0.3,  # 低温度保证提取稳定
            max_tokens=2000,  # 长对话可能产生大量实体，500 tokens不够会导致JSON被截断
        )

        logger.debug(f"LLM returned result type: {type(result_json)}")
        logger.debug(f"LLM returned result preview: {str(result_json)[:200] if not isinstance(result_json, str) else result_json[:200]}")

        # 解析JSON (处理多种可能的返回格式)
        if isinstance(result_json, dict):
            # 完整的JSON对象 {"entities": [...]}
            entity_list = result_json.get("entities", [])
            logger.debug(f"Extracted entities from dict response: {len(entity_list)} entities")
        elif isinstance(result_json, list):
            # 直接返回entities数组
            entity_list = result_json
            logger.debug(f"Using direct list response: {len(entity_list)} entities")
        elif isinstance(result_json, str):
            # JSON字符串，需要解析
            logger.warning(f"Received string response instead of parsed JSON, length: {len(result_json)}")
            logger.debug(f"String response preview: {result_json[:300]}")
            try:
                result = json.loads(result_json)
                if isinstance(result, dict):
                    entity_list = result.get("entities", [])
                elif isinstance(result, list):
                    entity_list = result
                else:
                    entity_list = []
                logger.debug(f"Parsed string response successfully: {len(entity_list)} entities")
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse string response as JSON: {e}")
                logger.error(f"String response: {result_json[:500]}")
                entity_list = []
        else:
            logger.error(f"Unexpected result type: {type(result_json)}")
            logger.error(f"Result content: {str(result_json)[:200]}")
            entity_list = []

        logger.debug(f"LLM recognized {len(entity_list)} entities")

    except Exception as e:
        logger.error(f"LLM call failed for entity recognition: {e}")
        # 不降级，直接抛出异常（全部失败策略）
        raise

    # ========== Step 3: 创建实体 + 跨层边 ==========
    entity_ids = []

    for entity_data in entity_list:
        entity_name = entity_data.get("name")
        entity_type = entity_data.get("type")
        entity_attributes = entity_data.get("attributes", {})
        entity_confidence = entity_data.get("confidence", 1.0)

        if not entity_name or not entity_type:
            logger.warning(f"Invalid entity data: {entity_data}")
            continue

        # 跳过 AI 自身的实体
        if entity_name == settings.writer.bot_name:
            logger.debug(f"Skipping bot self-entity: {entity_name}")
            continue
            logger.warning(f"Invalid entity data: {entity_data}")
            continue

        # 验证entity_type是否为有效枚举值
        valid_types = ["person", "place", "concept", "event", "skill", "other"]
        if entity_type not in valid_types:
            logger.warning(f"Invalid entity type '{entity_type}', using 'other'")
            entity_type = "other"

        # 检查实体是否已存在（同名即同人规则）
        existing_entity = entity_store.get_by_name(entity_name)
        entity_id = None

        if existing_entity:
            # 实体已存在，更新属性
            entity_id = existing_entity.id

            # 合并属性：保留现有属性，更新新属性
            merged_properties = existing_entity.properties or {}
            merged_properties.update(entity_attributes)
            # 移除临时兼容代码：不再将confidence存入properties

            try:
                entity_store.update(
                    entity_id=entity_id,
                    properties=merged_properties
                )
                logger.debug(f"Updated existing entity: {entity_name} ({entity_id})")
            except Exception as e:
                logger.error(f"Failed to update entity {entity_name}: {e}")
                continue
        else:
            # 创建新实体 - 直接使用source和confidence字段（表字段，非properties）
            new_entity = Entity(
                id=_generate_entity_id(),
                name=entity_name,  # 实体名称（如"张三"）
                type=entity_type,  # 固定类型枚举值
                properties=entity_attributes,  # 只包含业务属性
                source="entity_recognition",  # 元数据：表字段
                confidence=entity_confidence,  # 元数据：表字段
                embedding=embedding_service.encode(entity_name),
                emotion_timeline=None,
                emotion_current=None,
                created_at=datetime.now().isoformat(),
            )

            try:
                entity_id = entity_store.create(new_entity)
                logger.debug(f"Created new entity: {entity_name} ({entity_id})")
            except Exception as e:
                logger.error(f"Failed to create entity {entity_name}: {e}")
                # 独立事务：单个实体创建失败不影响其他实体
                continue

        entity_ids.append(entity_id)

        # 创建跨层边（体验→实体）
        try:
            cross_edge = CrossEdge(
                from_id=experience_id,
                to_id=entity_id,
                context="contains_entity",
                weight=1.0,
                created_at=datetime.now().isoformat(),
            )
            cross_edge_store.create(cross_edge)
            logger.debug(f"Created cross edge: {experience_id} -> {entity_id}")
        except Exception as e:
            logger.warning(f"Failed to create cross edge: {e}")
            # 独立事务：单个边创建失败不影响其他边

    logger.info(
        f"Entity recognition completed: "
        f"{len(entity_ids)} entities processed"
    )

    return entity_ids


def _load_prompt_template() -> str:
    """加载实体识别Prompt模板。

    Returns:
        Prompt模板字符串

    Raises:
        FileNotFoundError: 模板文件不存在
    """
    prompt_path = Path(__file__).parent.parent.parent / "config" / "prompts" / "write_entity_recognize.txt"

    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt template not found: {prompt_path}")

    with open(prompt_path, "r", encoding="utf-8") as f:
        template = f.read()

    return template


def _generate_entity_id() -> str:
    """生成实体ID（UUID格式）。

    Returns:
        实体ID

    Note:
        使用uuid.uuid4()生成唯一标识符
    """
    return str(uuid.uuid4())
