"""测试信息验证任务。"""

import pytest
from datetime import datetime
from unittest.mock import Mock, MagicMock
from Memory.storage.entity_edge_store import EntityEdgeStore, EntityEdge
from Memory.storage.entity_store import EntityStore, Entity
from Memory.storage.experience_store import ExperienceStore, Experience
from Memory.storage.database import db_manager
from Memory.consolidator.tasks.verify_task import verify_information


@pytest.fixture
def clean_db():
    """清理数据库的fixture。"""
    # 确保数据库已初始化
    if not db_manager.is_initialized:
        db_manager.initialize()

    # 清理测试数据
    with db_manager.transaction() as cursor:
        cursor.execute("DELETE FROM entity_edges WHERE relation LIKE 'test_%'")

    yield

    # 测试后清理
    with db_manager.transaction() as cursor:
        cursor.execute("DELETE FROM entity_edges WHERE relation LIKE 'test_%'")


def test_get_low_confidence(clean_db):
    """测试get_low_confidence方法查询低置信度边。

    Test 1: 返回confidence<threshold且verify_count=0的边
    Test 2: 支持按limit限制返回数量
    Test 3: 按confidence升序排序（最不确定的优先）
    Test 4: 返回List[EntityEdge]
    """
    store = EntityEdgeStore(db_manager)

    # 创建测试边
    edges = [
        EntityEdge(
            from_id="entity1",
            to_id="entity2",
            relation="test_low_conf_1",
            confidence=0.3,
            verify_count=0,
            source_type="direct",
        ),
        EntityEdge(
            from_id="entity1",
            to_id="entity3",
            relation="test_low_conf_2",
            confidence=0.4,
            verify_count=0,
            source_type="direct",
        ),
        EntityEdge(
            from_id="entity2",
            to_id="entity3",
            relation="test_high_conf",
            confidence=0.7,
            verify_count=0,
            source_type="direct",
        ),
        EntityEdge(
            from_id="entity1",
            to_id="entity4",
            relation="test_verified",
            confidence=0.2,
            verify_count=1,
            source_type="direct",
        ),
    ]

    for edge in edges:
        store.create(edge)

    # Test 1 & 3: 查询confidence < 0.5且verify_count=0的边
    results = store.get_low_confidence(threshold=0.5, verify_count=0)
    assert len(results) == 2
    assert results[0].relation == "test_low_conf_1"
    assert results[1].relation == "test_low_conf_2"
    # 验证按confidence升序排序
    assert results[0].confidence < results[1].confidence

    # Test 2: 测试limit参数
    results_limited = store.get_low_confidence(threshold=0.5, verify_count=0, limit=1)
    assert len(results_limited) == 1
    assert results_limited[0].relation == "test_low_conf_1"

    # Test 4: 验证返回类型
    assert all(isinstance(edge, EntityEdge) for edge in results)

    # 测试verify_count过滤
    results_verified = store.get_low_confidence(threshold=0.3, verify_count=1)
    assert len(results_verified) == 1
    assert results_verified[0].relation == "test_verified"


@pytest.fixture
def mock_llm_client():
    """Mock LLM客户端。"""
    client = Mock()
    client.call_json = Mock(
        return_value={"is_reliable": True, "confidence": 0.8, "reason": "信息来源可信"}
    )
    return client


def test_info_verify(clean_db, mock_llm_client):
    """测试verify_information函数。

    Test 1: 调用get_low_confidence()获取待验证边
    Test 2: LLM评估边的可靠性
    Test 3: 更新边的confidence和verify_count
    Test 4: 返回验证的边数量统计
    """
    edge_store = EntityEdgeStore(db_manager)
    entity_store = EntityStore(db_manager)
    exp_store = ExperienceStore(db_manager)

    # 创建测试实体（使用时间戳确保唯一性）
    import time

    timestamp = int(time.time() * 1000)

    entity1 = Entity(
        id=f"test_verify_entity1_{timestamp}", name=f"测试实体1_{timestamp}", type="person"
    )
    entity2 = Entity(
        id=f"test_verify_entity2_{timestamp}", name=f"测试实体2_{timestamp}", type="person"
    )
    entity_store.create(entity1)
    entity_store.create(entity2)

    # 创建低置信度测试边
    test_edge = EntityEdge(
        from_id=f"test_verify_entity1_{timestamp}",
        to_id=f"test_verify_entity2_{timestamp}",
        relation=f"test_verify_relation_{timestamp}",
        confidence=0.3,
        verify_count=0,
        source_type="direct",
        source="测试来源",
    )
    edge_id = edge_store.create(test_edge)
    assert edge_id > 0, "Edge should be created successfully"

    # 创建测试体验列表
    experiences = []

    # 调用verify_information
    result = verify_information(
        experiences=experiences,
        llm_client=mock_llm_client,
        entity_edge_store=edge_store,
        entity_store=entity_store,
        experience_store=exp_store,
        max_edges=20,
    )

    # 验证结果
    assert result["total_candidates"] == 1
    assert result["verified_count"] == 1
    assert result["confirmed_count"] == 1
    assert result["rejected_count"] == 0

    # 验证LLM被调用
    assert mock_llm_client.call_json.called

    # 验证边被更新
    updated_edge = edge_store.get(edge_id)
    assert updated_edge is not None, "Edge should exist after verification"
    assert updated_edge.verify_count == 1
    assert updated_edge.confidence == 0.8
    assert updated_edge.verified_at is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
