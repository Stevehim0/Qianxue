"""衰减计算任务模块。

实现记忆的时间衰减计算，应用统一的衰减公式到所有边和节点。
计算衰减后权重，实现休眠和唤醒机制。
"""

import logging
import math
from datetime import datetime
from typing import Dict, Any

from Memory.storage.experience_edge_store import ExperienceEdgeStore, ExperienceEdge
from Memory.storage.experience_store import ExperienceStore, Experience

logger = logging.getLogger(__name__)


def calculate_edge_decay(edge: ExperienceEdge, lambda_map: Dict[str, float], alpha: float) -> float:
    """计算单条边的衰减权重。

    衰减公式：decayed_weight = original × e^(-λ × t) × (1 + α × access_count)

    Args:
        edge: 体验边对象
        lambda_map: 边类型到λ值的映射（如{'temporal': 0.02, 'thematic': 0.015}）
        alpha: 强化系数

    Returns:
        衰减后权重（0-1范围）
    """
    # 1. 计算时间差（天）
    created_at = datetime.fromisoformat(edge.created_at)
    now = datetime.now()
    t = (now - created_at).total_seconds() / 86400.0  # 转换为天

    # 2. 获取该边类型的λ值
    lambda_val = lambda_map.get(edge.type, 0.02)  # 默认使用temporal的λ值

    # 3. 时间衰减因子
    time_factor = math.exp(-lambda_val * t)

    # 4. 强化因子（访问次数）
    reinforcement_factor = 1 + alpha * edge.access_count

    # 5. 综合衰减公式（边通常无情感驱动）
    decayed_weight = edge.weight * time_factor * reinforcement_factor

    # 6. 边界检查
    decayed_weight = max(0.0, min(edge.weight, decayed_weight))

    logger.debug(
        f"Edge {edge.id}: type={edge.type}, t={t:.2f}d, "
        f"lambda={lambda_val}, decayed={decayed_weight:.3f}"
    )

    return decayed_weight


def calculate_node_decay(
    exp: Experience,
    lambda_L0: float,
    lambda_L1: float,
    lambda_L2: float,
    lambda_L3: float,
    beta: float,
) -> tuple:
    """计算节点的分层衰减权重。

    衰减公式：decayed = e^(-λ × t) × (1 + β × emotion_intensity)

    Args:
        exp: 体验节点对象
        lambda_L0/L1/L2/L3: 四层的衰减速率
        beta: 情感保护系数

    Returns:
        (L0_decayed, L1_decayed, L2_decayed, L3_decayed) 元组
    """
    # 1. 计算时间差（天）
    created_at = datetime.fromisoformat(exp.created_at)
    now = datetime.now()
    t = (now - created_at).total_seconds() / 86400.0

    # 2. 情感强度
    emotion = exp.emotion_intensity or 0.5

    # 3. 情感因子
    emotion_factor = 1 + beta * emotion

    # 4. 分层衰减（使用不同λ值）
    L0_decayed = math.exp(-lambda_L0 * t) * emotion_factor
    L1_decayed = math.exp(-lambda_L1 * t) * emotion_factor
    L2_decayed = math.exp(-lambda_L2 * t) * emotion_factor
    L3_decayed = math.exp(-lambda_L3 * t) * emotion_factor

    # 5. 边界检查
    L0_decayed = max(0.0, min(1.0, L0_decayed))
    L1_decayed = max(0.0, min(1.0, L1_decayed))
    L2_decayed = max(0.0, min(1.0, L2_decayed))
    L3_decayed = max(0.0, min(1.0, L3_decayed))

    logger.debug(
        f"Node {exp.id}: t={t:.2f}d, emotion={emotion:.2f}, "
        f"L0={L0_decayed:.3f}, L1={L1_decayed:.3f}, "
        f"L2={L2_decayed:.3f}, L3={L3_decayed:.3f}"
    )

    return (L0_decayed, L1_decayed, L2_decayed, L3_decayed)


def check_and_update_dormancy(
    edge: ExperienceEdge, edge_store: ExperienceEdgeStore, dormant_threshold: float
) -> tuple:
    """检查并更新边的休眠状态。

    Args:
        edge: 体验边对象
        edge_store: 边存储实例（用于更新dormant字段）
        dormant_threshold: 休眠阈值

    Returns:
        (dormant_set, awakened) 元组
        - dormant_set: 是否设置为休眠（True/False）
        - awakened: 是否被唤醒（True/False）
    """
    # 1. 检查是否应该休眠
    should_dormant = edge.decayed_weight < dormant_threshold

    # 2. 检查是否应该唤醒（当前休眠但权重恢复）
    should_awaken = edge.dormant == 1 and edge.decayed_weight >= dormant_threshold

    dormant_set = False
    awakened = False

    # 3. 执行状态更新
    if should_dormant and edge.dormant == 0:
        edge_store.set_dormant(edge.id, True)
        dormant_set = True
        logger.debug(f"Edge {edge.id} marked dormant (weight={edge.decayed_weight:.3f})")

    elif should_awaken:
        edge_store.set_dormant(edge.id, False)
        awakened = True
        logger.debug(f"Edge {edge.id} awakened (weight={edge.decayed_weight:.3f})")

    return (dormant_set, awakened)


def calculate_decay(
    experience_store: ExperienceStore,
    experience_edge_store: ExperienceEdgeStore,
    lambda_map: Dict[str, float],
    lambda_L0: float,
    lambda_L1: float,
    lambda_L2: float,
    lambda_L3: float,
    alpha: float,
    beta: float,
    dormancy_threshold: float,
) -> Dict[str, Any]:
    """计算所有边和节点的衰减权重。

    这是Phase 2的核心任务，在Phase 1的六个并行任务完成后执行。

    Args:
        experience_store: 体验存储实例
        experience_edge_store: 体验边存储实例
        lambda_map: 边类型到λ值的映射
        lambda_L0/L1/L2/L3: 四层的衰减速率
        alpha: 强化系数
        beta: 情感保护系数
        dormancy_threshold: 休眠阈值

    Returns:
        任务结果摘要 {
            'edge_count': 处理的边数,
            'node_count': 处理的节点数,
            'dormant_count': 标记休眠的边数,
            'awakened_count': 唤醒的边数
        }
    """
    logger.info("Starting decay calculation task")

    # 1. 获取所有边
    edges = experience_edge_store.get_all()
    logger.info(f"Processing {len(edges)} edges")

    dormant_count = 0
    awakened_count = 0

    # 2. 计算边的衰减
    for edge in edges:
        # 计算衰减权重
        decayed_weight = calculate_edge_decay(edge=edge, lambda_map=lambda_map, alpha=alpha)

        # 更新decayed_weight字段
        experience_edge_store.update_decayed_weight(edge.id, decayed_weight)

        # 临时更新edge对象的decayed_weight（用于休眠检查）
        edge.decayed_weight = decayed_weight

        # 检查并更新休眠状态
        dormant_set, awakened = check_and_update_dormancy(
            edge=edge, edge_store=experience_edge_store, dormant_threshold=dormancy_threshold
        )

        if dormant_set:
            dormant_count += 1
        if awakened:
            awakened_count += 1

    # 3. 获取所有节点
    experiences = experience_store.get_all()
    logger.info(f"Processing {len(experiences)} nodes")

    # 4. 计算节点的分层衰减
    for exp in experiences:
        L0_decayed, L1_decayed, L2_decayed, L3_decayed = calculate_node_decay(
            exp=exp,
            lambda_L0=lambda_L0,
            lambda_L1=lambda_L1,
            lambda_L2=lambda_L2,
            lambda_L3=lambda_L3,
            beta=beta,
        )

        # 更新节点的衰减字段
        exp.L0_decayed = L0_decayed
        exp.L1_decayed = L1_decayed
        exp.L2_decayed = L2_decayed
        exp.L3_decayed = L3_decayed

        experience_store.update_decayed_fields(exp)

    # 5. 返回任务结果
    result = {
        "edge_count": len(edges),
        "node_count": len(experiences),
        "dormant_count": dormant_count,
        "awakened_count": awakened_count,
    }

    logger.info(
        f"Decay calculation completed: "
        f"edges={result['edge_count']}, "
        f"nodes={result['node_count']}, "
        f"dormant={result['dormant_count']}, "
        f"awakened={result['awakened_count']}"
    )

    return result
