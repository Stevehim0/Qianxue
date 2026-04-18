"""邻接表缓存测试。"""

import pytest
from unittest.mock import Mock

from Memory.recall.adjacency_cache import AdjacencyCache


@pytest.mark.skip(reason="Wave 0 stub")
def test_spread(mock_edge_store):
    """测试激活扩散（RECALL-05）。

    - 从起始节点开始扩散
    - 正确计算激活分数
    - 考虑边的decayed_weight
    """
    cache = AdjacencyCache(mock_edge_store, hop_decay=0.6)

    # 单跳扩散
    activated = cache.spread(start_nodes=["exp_001"], max_hops=1)
    assert "exp_002" in activated
    assert activated["exp_002"] > 0

    # 多跳扩散
    activated = cache.spread(start_nodes=["exp_001"], max_hops=2)
    assert len(activated) > 1


@pytest.mark.skip(reason="Wave 0 stub")
def test_lifecycle(mock_edge_store):
    """测试三阶段生命周期（RECALL-06）。

    - 启动加载：从数据库全量加载所有边
    - 实时同步：写入新边时立即更新
    - 巩固重载：巩固结束后全量重载
    """
    cache = AdjacencyCache(mock_edge_store)

    # 启动加载
    assert len(cache.adjacency) > 0  # 应该加载了边

    # 实时同步
    cache.add_edge("exp_005", "exp_006", "temporal", 0.9)
    assert "exp_005" in cache.adjacency

    # 巩固重载
    cache.reload()
    assert len(cache.adjacency) > 0  # 重载后仍有数据


@pytest.mark.skip(reason="Wave 0 stub")
def test_max_hops(mock_edge_store):
    """测试扩散跳数限制（RECALL-07）。

    - max_hops=1时只扩散1跳
    - max_hops=2时扩散2跳
    - 激活分数随跳数衰减
    """
    cache = AdjacencyCache(mock_edge_store, hop_decay=0.6)

    # max_hops=1
    activated_1 = cache.spread(start_nodes=["exp_001"], max_hops=1)

    # max_hops=2
    activated_2 = cache.spread(start_nodes=["exp_001"], max_hops=2)

    # 2跳应该激活更多节点
    assert len(activated_2) >= len(activated_1)


@pytest.mark.skip(reason="Wave 0 stub")
def test_activation_score(mock_edge_store):
    """测试激活分数计算（RECALL-08）。

    - 公式：score = base_score × decayed_weight × (hop_decay ^ hop)
    - hop_decay参数影响衰减速度
    - decayed_weight影响边的权重
    """
    cache = AdjacencyCache(mock_edge_store, hop_decay=0.6)

    activated = cache.spread(start_nodes=["exp_001"], max_hops=1)

    # 检查激活分数在合理范围内
    for node_id, score in activated.items():
        assert 0 <= score <= 1.0


def test_recall_manager_integration(mock_edge_store):
    """测试RecallManager集成（Plan 10-03/10-04）。

    验证RecallManager正确调用AdjacencyCache.spread()。
    """
    from Memory.recall import RecallManager, AdjacencyCache
    from unittest.mock import Mock

    # 创建AdjacencyCache
    cache = AdjacencyCache(mock_edge_store, hop_decay=0.6)

    # 创建RecallManager
    manager = RecallManager(
        experience_store=Mock(),
        entity_store=Mock(),
        edge_store=mock_edge_store,
        vector_store=Mock(),
        embedding_service=Mock(),
        adjacency_cache=cache,
    )

    # 验证adjacency_cache属性已设置
    assert manager.adjacency_cache == cache

    # 验证spread()方法可调用
    start_nodes = ["exp_001"]
    activated = cache.spread(start_nodes, max_hops=1)
    assert isinstance(activated, dict)
