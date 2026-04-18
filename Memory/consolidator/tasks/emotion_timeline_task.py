"""情感时间线更新任务模块。

更新高频实体的情感时间线，总结情感变化趋势。
"""

import logging
from typing import List, Dict, Any
from pathlib import Path
from datetime import datetime, timedelta

from Memory.storage.experience_store import Experience, ExperienceStore, experience_store
from Memory.storage.entity_store import EntityStore, entity_store
from Memory.storage.cross_edge_store import CrossEdgeStore
from Memory.llm.base import BaseLLMClient

logger = logging.getLogger(__name__)


def update_emotion_timeline(
    experiences: List[Experience],
    llm_client: BaseLLMClient,
    entity_store: EntityStore,
    experience_store: ExperienceStore,
    prompt_template_path: str = None,
) -> Dict[str, Any]:
    """更新高频实体的情感时间线。

    查询最近30天有>=3次体验的person，
    使用LLM总结情感变化趋势，更新emotion_timeline字段。

    Args:
        experiences: 体验节点列表
        llm_client: LLM客户端实例
        entity_store: 实体存储实例
        experience_store: 体验存储实例
        prompt_template_path: Prompt模板路径（可选）

    Returns:
        任务结果摘要 {
            'updated_count': 更新的实体数,
            'evaluated_count': 评估的实体数
        }
    """
    # 加载prompt模板
    if prompt_template_path is None:
        prompt_template_path = (
            Path(__file__).parent.parent.parent
            / "config"
            / "prompts"
            / "consolid_emotion_timeline.txt"
        )

    try:
        with open(prompt_template_path, "r", encoding="utf-8") as f:
            prompt_template = f.read()
    except FileNotFoundError:
        logging.error(f"Prompt模板未找到: {prompt_template_path}")
        return {"updated_count": 0, "evaluated_count": 0}

    logger = logging.getLogger(__name__)

    # ========== Step 1: 获取高频person实体 ==========
    frequent_persons = entity_store.get_frequent_entities(
        entity_type="person", days=30, min_count=3
    )

    if not frequent_persons:
        logger.info("情感时间线更新: 没有高频person实体")
        return {"updated_count": 0, "evaluated_count": 0}

    logger.info(f"情感时间线更新: {len(frequent_persons)}个高频person实体")

    # 获取cross_edge_store（使用entity_store的db）
    xes = CrossEdgeStore(entity_store.db)

    # ========== Step 2: 对每个person总结情感趋势 ==========
    updated_count = 0
    evaluated_count = 0

    for person in frequent_persons:
        try:
            # 获取该person相关的最近体验（通过cross_edges）
            cross_edges = xes.get_by_from(person.id, days=30)

            if not cross_edges:
                logger.debug(f"跳过无最近体验的person: {person.name}")
                continue

            # 获取体验详情
            related_experiences = []
            for ce in cross_edges:
                exp = experience_store.get(ce.to_id)
                if exp:
                    related_experiences.append(exp)

            # 筛选有情感记录的体验
            emotion_experiences = [
                exp
                for exp in related_experiences
                if exp.emotion_category and exp.emotion_target == person.name
            ]

            if not emotion_experiences:
                logger.debug(f"跳过无情感记录的person: {person.name}")
                continue

            # 构建情感记录摘要
            emotion_records = []
            for exp in sorted(emotion_experiences, key=lambda e: e.created_at)[:10]:
                if exp.emotion_category:
                    intensity_str = (
                        f"{exp.emotion_intensity:.1f}" if exp.emotion_intensity else "N/A"
                    )
                    emotion_records.append(
                        f"{exp.created_at[:10]}: {exp.emotion_category} (强度{intensity_str})"
                    )

            if not emotion_records:
                continue

            # 构建prompt
            prompt = prompt_template.format(
                person_name=person.name, emotion_records="\n".join(emotion_records)
            )

            # 调用LLM
            result = llm_client.call_json(prompt)
            evaluated_count += 1

            # 构建emotion_timeline数据
            emotion_timeline = {
                "overall_trend": result.get("overall_trend", "stable"),
                "key_events": result.get("key_events", []),
                "relationship_status": result.get("relationship_status", "neutral"),
                "updated_at": datetime.now().isoformat(),
                "record_count": len(emotion_records),
            }

            # 更新实体的emotion_timeline字段（存储在properties）
            new_properties = person.properties.copy() if person.properties else {}
            new_properties["_emotion_timeline"] = emotion_timeline

            success = entity_store.update_properties(entity_id=person.id, properties=new_properties)

            if success:
                updated_count += 1
                logger.info(
                    f"情感时间线更新: {person.name} "
                    f"(趋势={emotion_timeline['overall_trend']}, 记录数={len(emotion_records)})"
                )

        except Exception as e:
            logger.error(f"情感时间线更新失败 ({person.id}): {e}", exc_info=True)

    return {"updated_count": updated_count, "evaluated_count": evaluated_count}
