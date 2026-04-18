"""衰减计算任务测试模块。

测试边和节点的衰减计算逻辑。
"""

import pytest
from datetime import datetime, timedelta
from Memory.consolidator.tasks.decay_calculation_task import (
    calculate_edge_decay,
    calculate_node_decay,
    check_and_update_dormancy,
    calculate_decay,
)
from Memory.storage.experience_edge_store import ExperienceEdge, ExperienceEdgeStore
from Memory.storage.experience_store import Experience, ExperienceStore
from Memory.storage.database import db_manager


@pytest.fixture
def test_db():
    """创建测试数据库."""
    db_manager.initialize(":memory:")
    yield db_manager
    db_manager.close()


@pytest.fixture
def edge_store(test_db):
    """创建ExperienceEdgeStore实例."""
    return ExperienceEdgeStore(test_db)


@pytest.fixture
def exp_store(test_db):
    """创建ExperienceStore实例."""
    return ExperienceStore(test_db)


def test_calculate_edge_decay_basic(edge_store):
    """测试1: 计算1天前的temporal边衰减."""
    # 创建1天前的边
    yesterday = (datetime.now() - timedelta(days=1)).isoformat()
    edge = ExperienceEdge(
        from_id="exp_001",
        to_id="exp_002",
        type="temporal",
        weight=1.0,
        decayed_weight=1.0,
        access_count=0,
        created_at=yesterday,
    )

    # 计算衰减
    lambda_map = {"temporal": 0.02, "thematic": 0.015, "causal": 0.01, "associative": 0.025}
    decayed = calculate_edge_decay(edge, lambda_map, alpha=0.05)

    # 验证：衰减后权重应小于原始权重
    # 公式：1.0 * e^(-0.02 * 1) = 1.0 * 0.9802 ≈ 0.98
    assert decayed < 1.0
    assert decayed > 0.95  # 1天衰减不应太多
    assert decayed == pytest.approx(0.9802, rel=0.01)


def test_calculate_edge_decay_with_reinforcement(edge_store):
    """测试2: 计算有access_count的边衰减（强化因子生效）."""
    # 创建1天前的边，access_count=10
    yesterday = (datetime.now() - timedelta(days=1)).isoformat()
    edge = ExperienceEdge(
        from_id="exp_001",
        to_id="exp_002",
        type="temporal",
        weight=1.0,
        decayed_weight=1.0,
        access_count=10,
        created_at=yesterday,
    )

    # 计算衰减
    lambda_map = {"temporal": 0.02}
    decayed = calculate_edge_decay(edge, lambda_map, alpha=0.05)

    # 验证：强化因子应使衰减后的权重更高
    # 公式：1.0 * e^(-0.02 * 1) * (1 + 0.05 * 10) = 0.9802 * 1.5 ≈ 1.47
    # 但边界检查会限制不超过原始权重1.0
    assert decayed == pytest.approx(1.0, abs=0.01)


def test_calculate_edge_decay_with_emotion(edge_store):
    """测试3: 计算情感驱动的边衰减（情感因子生效）."""
    # 创建有情感驱动的边
    yesterday = (datetime.now() - timedelta(days=1)).isoformat()
    edge = ExperienceEdge(
        from_id="exp_001",
        to_id="exp_002",
        type="temporal",
        weight=1.0,
        decayed_weight=1.0,
        emotion_driver="strong_positive",
        access_count=0,
        created_at=yesterday,
    )

    # 计算衰减
    lambda_map = {"temporal": 0.02}
    decayed = calculate_edge_decay(edge, lambda_map, alpha=0.05)

    # 验证：边通常不考虑情感因子（情感因子只用于节点）
    # 所以结果应该和基本衰减相同
    assert decayed < 1.0
    assert decayed > 0.95


def test_calculate_edge_decay_boundary(edge_store):
    """测试4: 边界检查（衰减权重不超过原始权重，不小于0）."""
    # 创建7天前的边
    week_ago = (datetime.now() - timedelta(days=7)).isoformat()
    edge = ExperienceEdge(
        from_id="exp_001",
        to_id="exp_002",
        type="temporal",
        weight=1.0,
        decayed_weight=1.0,
        access_count=0,
        created_at=week_ago,
    )

    # 计算衰减
    lambda_map = {"temporal": 0.02}
    decayed = calculate_edge_decay(edge, lambda_map, alpha=0.05)

    # 验证：权重应在[0, 1]范围内
    assert 0.0 <= decayed <= 1.0
    # 7天后：e^(-0.02 * 7) = e^(-0.14) ≈ 0.869
    assert decayed == pytest.approx(0.869, rel=0.01)


def test_calculate_edge_decay_different_types(edge_store):
    """测试5: 不同边类型使用不同λ值."""
    # 创建1天前的边
    yesterday = (datetime.now() - timedelta(days=1)).isoformat()

    # 测试temporal边（λ=0.02）
    edge_temporal = ExperienceEdge(
        from_id="exp_001", to_id="exp_002", type="temporal", weight=1.0, created_at=yesterday
    )
    decayed_temporal = calculate_edge_decay(
        edge_temporal,
        {"temporal": 0.02, "thematic": 0.015, "causal": 0.01, "associative": 0.025},
        alpha=0.05,
    )

    # 测试causal边（λ=0.01，衰减最慢）
    edge_causal = ExperienceEdge(
        from_id="exp_001", to_id="exp_002", type="causal", weight=1.0, created_at=yesterday
    )
    decayed_causal = calculate_edge_decay(
        edge_causal,
        {"temporal": 0.02, "thematic": 0.015, "causal": 0.01, "associative": 0.025},
        alpha=0.05,
    )

    # 验证：causal边（λ=0.01）的衰减后权重应高于temporal边（λ=0.02）
    assert decayed_causal > decayed_temporal


def test_calculate_node_decay_layered(exp_store):
    """测试1: 计算L0/L1/L2/L3分层衰减（使用不同λ值）."""
    # 创建1天前的节点
    yesterday = (datetime.now() - timedelta(days=1)).isoformat()
    exp = Experience(
        id="exp_test_001", L3_raw="Test experience", emotion_intensity=0.5, created_at=yesterday
    )

    # 计算分层衰减
    L0, L1, L2, L3 = calculate_node_decay(
        exp, lambda_L0=0.01, lambda_L1=0.02, lambda_L2=0.03, lambda_L3=0.05, beta=0.5
    )

    # 验证：L0衰减最慢，L3衰减最快
    assert L0 > L1 > L2 > L3
    # 验证：所有值在[0, 1]范围内
    assert all(0.0 <= v <= 1.0 for v in [L0, L1, L2, L3])

    # L0: e^(-0.01 * 1) * (1 + 0.5 * 0.5) = 0.99 * 1.25 ≈ 1.24 → 限制为1.0
    # L1: e^(-0.02 * 1) * 1.25 = 0.98 * 1.25 ≈ 1.225 → 限制为1.0
    # L2: e^(-0.03 * 1) * 1.25 = 0.97 * 1.25 ≈ 1.21 → 限制为1.0
    # L3: e^(-0.05 * 1) * 1.25 = 0.95 * 1.25 ≈ 1.19 → 限制为1.0
    # 由于情感因子 > 1，所有值都被限制为1.0
    assert L0 == pytest.approx(1.0, abs=0.01)
    assert L1 == pytest.approx(1.0, abs=0.01)
    assert L2 == pytest.approx(1.0, abs=0.01)
    assert L3 == pytest.approx(1.0, abs=0.01)


def test_calculate_node_decay_with_emotion(exp_store):
    """测试2: 计算高情感强度节点的衰减（情感因子生效）."""
    # 创建1天前的高情感强度节点
    yesterday = (datetime.now() - timedelta(days=1)).isoformat()
    exp = Experience(
        id="exp_test_001",
        L3_raw="Emotional experience",
        emotion_intensity=0.8,
        created_at=yesterday,
    )

    # 计算分层衰减
    L0, L1, L2, L3 = calculate_node_decay(
        exp, lambda_L0=0.01, lambda_L1=0.02, lambda_L2=0.03, lambda_L3=0.05, beta=0.5
    )

    # 验证：高情感强度（0.8）使衰减更慢
    # 情感因子：1 + 0.5 * 0.8 = 1.4
    # 所有值应该接近1.0（因为情感因子 > 1，边界检查限制为1.0）
    assert all(v == pytest.approx(1.0, abs=0.01) for v in [L0, L1, L2, L3])


def test_calculate_node_decay_boundary(exp_store):
    """测试3: 边界检查（每层衰减权重在0-1范围）."""
    # 创建30天前的节点
    month_ago = (datetime.now() - timedelta(days=30)).isoformat()
    exp = Experience(
        id="exp_test_001", L3_raw="Old experience", emotion_intensity=0.5, created_at=month_ago
    )

    # 计算分层衰减
    L0, L1, L2, L3 = calculate_node_decay(
        exp, lambda_L0=0.01, lambda_L1=0.02, lambda_L2=0.03, lambda_L3=0.05, beta=0.5
    )

    # 验证：所有值在[0, 1]范围内
    assert all(0.0 <= v <= 1.0 for v in [L0, L1, L2, L3])

    # 验证：L0衰减最慢，L3衰减最快
    assert L0 > L1 > L2 > L3

    # 30天后：
    # L0: e^(-0.01 * 30) * 1.25 = 0.74 * 1.25 = 0.925
    # L1: e^(-0.02 * 30) * 1.25 = 0.55 * 1.25 = 0.687
    # L2: e^(-0.03 * 30) * 1.25 = 0.40 * 1.25 = 0.50
    # L3: e^(-0.05 * 30) * 1.25 = 0.22 * 1.25 = 0.275
    assert L0 == pytest.approx(0.925, rel=0.05)
    assert L1 == pytest.approx(0.687, rel=0.05)
    assert L2 == pytest.approx(0.50, rel=0.05)
    assert L3 == pytest.approx(0.275, rel=0.05)


def test_calculate_node_decay_rates(exp_store):
    """测试4: 分层衰减速率正确（L0最慢，L3最快）."""
    # 创建10天前的节点
    ten_days_ago = (datetime.now() - timedelta(days=10)).isoformat()
    exp = Experience(
        id="exp_test_001",
        L3_raw="Test experience",
        emotion_intensity=0.0,  # 无情感保护
        created_at=ten_days_ago,
    )

    # 计算分层衰减
    L0, L1, L2, L3 = calculate_node_decay(
        exp, lambda_L0=0.01, lambda_L1=0.02, lambda_L2=0.03, lambda_L3=0.05, beta=0.5
    )

    # 验证：L0最慢，L3最快
    assert L0 > L1 > L2 > L3

    # 无情感保护时：
    # L0: e^(-0.01 * 10) = 0.904
    # L1: e^(-0.02 * 10) = 0.818
    # L2: e^(-0.03 * 10) = 0.740
    # L3: e^(-0.05 * 10) = 0.606
    assert L0 == pytest.approx(0.904, rel=0.01)
    assert L1 == pytest.approx(0.818, rel=0.01)
    assert L2 == pytest.approx(0.740, rel=0.01)
    assert L3 == pytest.approx(0.606, rel=0.01)


def test_dormancy_mechanism_mark_dormant(edge_store):
    """测试1: decayed_weight低于阈值的边标记为休眠."""
    # 注意：这个测试需要schema v3支持dormant字段
    # 在08-01计划中应该已经添加了dormant字段
    # 这里暂时跳过，等待schema升级
    pytest.skip("Requires schema v3 with dormant field")


def test_dormancy_mechanism_awaken(edge_store):
    """测试2: decayed_weight高于阈值的休眠边被唤醒."""
    pytest.skip("Requires schema v3 with dormant field")


def test_dormancy_mechanism_keep_active(edge_store):
    """测试3: decayed_weight高的活跃边保持活跃."""
    pytest.skip("Requires schema v3 with dormant field")


def test_dormancy_mechanism_keep_dormant(edge_store):
    """测试4: decayed_weight低的休眠边保持休眠."""
    pytest.skip("Requires schema v3 with dormant field")


def test_calculate_decay_integration(exp_store, edge_store):
    """测试5: 集成测试（端到端）."""
    pytest.skip("Requires schema v3 with decay fields")
