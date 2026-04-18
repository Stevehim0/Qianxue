"""隐性边发现任务模块。

本模块实现体验节点之间的隐性关联发现功能：
- 使用embedding相似度预筛选候选体验对
- 调用LLM评估每对是否存在隐性关联
- 创建或更新体验层边（UPSERT语义）
"""

import logging
from typing import List, Dict, Any
from pathlib import Path

import numpy as np

from Memory.storage.experience_store import Experience
from Memory.storage.experience_edge_store import ExperienceEdge, ExperienceEdgeStore
from Memory.llm.base import BaseLLMClient
from Memory.config.settings import settings

logger = logging.getLogger(__name__)


def discover_implicit_edges(
    experiences: List[Experience],
    llm_client: BaseLLMClient,
    experience_store,
    experience_edge_store: ExperienceEdgeStore,
    embedding_service=None,
    top_k: int = 50,
    prompt_template_path: str = None,
) -> Dict[str, Any]:
    """发现体验节点之间的隐性关联边。

    流程：
    1. 对每个体验，用embedding检索最相似的其他体验（top_k）
    2. 筛选相似度>=threshold的体验对
    3. LLM评估每对是否存在隐性关联
    4. 创建/更新边（UPSERT语义）

    Args:
        experiences: 待处理的体验节点列表
        llm_client: LLM客户端实例
        experience_store: 体验存储实例
        experience_edge_store: 体验边存储实例
        embedding_service: Embedding服务实例（可选，用于生成向量）
        top_k: 每个体验检索的最相似体验数
        prompt_template_path: Prompt模板路径（可选）

    Returns:
        任务结果摘要 {
            'created': 新建边数,
            'updated': 更新边数,
            'evaluated': 评估的对数,
            'total_candidates': 候选对数
        }

    注意：
        矩阵相似度计算为O(n²)复杂度，建议batch_size<=100
    """
    # 加载prompt模板
    if prompt_template_path is None:
        prompt_template_path = (
            Path(__file__).parent.parent.parent
            / "config"
            / "prompts"
            / "consolid_implicit_edges.txt"
        )

    try:
        with open(prompt_template_path, "r", encoding="utf-8") as f:
            prompt_template = f.read()
    except FileNotFoundError:
        logging.error(f"Prompt模板未找到: {prompt_template_path}")
        return {"created": 0, "updated": 0, "evaluated": 0, "total_candidates": 0}

    # ========== Step 1: 收集有embedding的体验 ==========
    valid_experiences = [exp for exp in experiences if exp.L0_embedding is not None]
    if len(valid_experiences) < 2:
        logger.info("有效体验少于2个，跳过隐性边发现")
        return {"created": 0, "updated": 0, "evaluated": 0, "total_candidates": 0}

    # 性能警告：O(n²)复杂度
    if len(valid_experiences) > 100:
        logger.warning(
            f"隐性边发现: 体验数量({len(valid_experiences)}) > 100，" f"相似度矩阵计算可能较慢"
        )

    # ========== Step 2: 计算所有对的相似度（矩阵运算） ==========
    # 收集所有embedding
    embeddings = np.array([exp.L0_embedding for exp in valid_experiences])

    # 计算相似度矩阵（点积，假设embedding已归一化）
    similarity_matrix = np.dot(embeddings, embeddings.T)

    # 获取上三角矩阵的索引（避免重复和自比较）
    threshold = settings.consolidation.similarity_threshold
    candidates = []

    for i in range(len(valid_experiences)):
        for j in range(i + 1, len(valid_experiences)):
            similarity = similarity_matrix[i, j]

            if similarity >= threshold:
                candidates.append((valid_experiences[i], valid_experiences[j], similarity))

    # 按相似度降序排序，取top_k
    candidates.sort(key=lambda x: x[2], reverse=True)
    top_candidates = candidates[:top_k]

    logger.info(
        f"隐性边候选: 找到{len(candidates)}对相似>={threshold}, "
        f"选取top{len(top_candidates)}对评估"
    )

    # ========== Step 3: LLM评估每对是否存在隐性关联 ==========
    edges_to_create = []
    evaluated_count = 0

    for exp_a, exp_b, similarity in top_candidates:
        try:
            # 构建prompt
            prompt = prompt_template.format(
                entity_a=f"体验{exp_a.id[:15]}...",
                entity_b=f"体验{exp_b.id[:15]}...",
                shared_context=f"""
                体验A摘要：{exp_a.L0_text or exp_a.L3_raw[:100]}
                体验B摘要：{exp_b.L0_text or exp_b.L3_raw[:100]}
                相似度：{similarity:.3f}
                """,
            )

            # 调用LLM
            result = llm_client.call_json(prompt)

            evaluated_count += 1

            # 检查是否有关系
            if result.get("has_relation", False):
                relation_type = result.get("relation_type", "related")
                confidence = result.get("confidence", 0.5)

                # 只创建高置信度的边
                if confidence >= 0.5:
                    # 只创建单向边（A→B），反向由查重时检查
                    edge = ExperienceEdge(
                        from_id=exp_a.id,
                        to_id=exp_b.id,
                        type=relation_type,
                        weight=confidence,
                        decayed_weight=confidence,
                        emotion_driver=f"implicit: {result.get('reason', '')[:50]}",
                    )

                    edges_to_create.append(edge)
                    logger.info(
                        f"发现隐性边: {exp_a.id[:10]} <-> {exp_b.id[:10]} "
                        f"(type={relation_type}, conf={confidence:.2f})"
                    )

        except Exception as e:
            logger.error(f"LLM评估失败 ({exp_a.id[:10]}, {exp_b.id[:10]}): {e}")
            # 继续评估下一对

    # ========== Step 4: 批量创建/更新边 ==========
    if edges_to_create:
        result = experience_edge_store.upsert_batch(edges_to_create)
        logger.info(f"隐性边创建完成: {result['created']}新建, " f"{result['updated']}更新")
    else:
        result = {"created": 0, "updated": 0}

    return {
        "created": result["created"],
        "updated": result["updated"],
        "evaluated": evaluated_count,
        "total_candidates": len(candidates),
    }
