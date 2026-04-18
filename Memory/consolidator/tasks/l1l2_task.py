"""L1/L2深层提取任务模块。

使用LLM从L3原始记录生成L1关键细节和L2意义提炼。
"""

import logging
from typing import List, Dict, Any
from pathlib import Path

from Memory.storage.experience_store import Experience
from Memory.storage.experience_store import ExperienceStore
from Memory.llm.base import BaseLLMClient
from Memory.config.settings import settings
from Memory.llm.utils import parse_json

logger = logging.getLogger(__name__)


def extract_l1l2(
    experiences: List[Experience],
    llm_client: BaseLLMClient,
    experience_store: ExperienceStore,
    prompt_template_path: str = None,
    stable_text: str = "",
) -> Dict[str, Any]:
    """深层提取L1/L2摘要。

    对每个体验节点：
    - 跳过已有L1/L2的节点
    - 跳过importance < min_importance的节点
    - 使用LLM生成L1（关键细节）和L2（意义提炼）
    - 更新数据库

    Args:
        experiences: 待处理的体验节点列表
        llm_client: LLM客户端实例
        experience_store: 体验存储实例
        prompt_template_path: Prompt模板路径（可选）

    Returns:
        任务结果摘要 {
            'updated_count': 更新的节点数,
            'skipped_count': 跳过的节点数,
            'failed_count': 失败的节点数,
            'total_count': 总节点数
        }
    """
    updated_count = 0
    skipped_count = 0
    failed_count = 0
    total_count = len(experiences)

    # 加载prompt模板
    if prompt_template_path is None:
        prompt_template_path = (
            Path(__file__).parent.parent.parent / "config" / "prompts" / "consolid_l1l2.txt"
        )

    try:
        with open(prompt_template_path, "r", encoding="utf-8") as f:
            prompt_template = f.read()
    except FileNotFoundError:
        logging.error(f"Prompt模板未找到: {prompt_template_path}")
        return {
            "updated_count": 0,
            "skipped_count": total_count,
            "failed_count": 0,
            "total_count": total_count,
            "error": "prompt_template_not_found",
        }

    logger = logging.getLogger(__name__)

    for exp in experiences:
        try:
            # 检查1: 跳过已有L1/L2的节点
            if exp.L1_text and exp.L2_text:
                skipped_count += 1
                logger.debug(f"跳过已有L1/L2的节点: {exp.id}")
                continue

            # 检查2: 跳过重要性不足的节点
            min_importance = getattr(settings.consolidation, "min_importance_for_l1l2", 0.5)
            if exp.importance < min_importance:
                skipped_count += 1
                logger.debug(
                    f"跳过低重要性节点: {exp.id} "
                    f"(importance={exp.importance} < {min_importance})"
                )
                continue

            # 构建prompt
            l0_summary = exp.L0_text or exp.L3_raw[:200] + "..."
            l3_full = exp.L3_raw

            prompt = prompt_template.format(
                l0_summary=l0_summary,
                l3_full=l3_full,
                ai_personality=stable_text or "无",
            )

            # 调用LLM
            result_text = llm_client.call_with_retry(prompt=prompt, response_format="text")

            # 解析JSON结果
            try:
                result = parse_json(result_text)
            except ValueError as e:
                logger.error(f"LLM返回JSON解析失败 (exp={exp.id}): {e}")
                failed_count += 1
                continue

            # 验证返回结果
            if not isinstance(result, dict):
                logger.error(f"LLM返回非字典类型: {type(result)}")
                failed_count += 1
                continue

            if "l1_memory" not in result or "l2_meaning" not in result:
                logger.error(f"LLM返回缺少必需字段: {result}")
                failed_count += 1
                continue

            # 更新数据库
            success = experience_store.update_l1l2(
                experience_id=exp.id, l1_text=result["l1_memory"], l2_text=result["l2_meaning"]
            )

            if success:
                updated_count += 1
                logger.info(
                    f"L1/L2提取成功: {exp.id}, "
                    f"L1={len(result['l1_memory'])}字, "
                    f"L2={len(result['l2_meaning'])}字"
                )
            else:
                failed_count += 1
                logger.warning(f"更新失败: {exp.id}")

        except Exception as e:
            failed_count += 1
            logger.error(f"L1/L2提取失败 (exp={exp.id}): {e}", exc_info=True)
            # 继续处理下一个节点

    return {
        "updated_count": updated_count,
        "skipped_count": skipped_count,
        "failed_count": failed_count,
        "total_count": total_count,
    }
