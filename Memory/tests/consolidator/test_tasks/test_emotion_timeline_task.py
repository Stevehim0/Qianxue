"""测试情感时间线更新任务。"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock
from Memory.storage.entity_store import EntityStore, Entity
from Memory.storage.cross_edge_store import CrossEdgeStore, CrossEdge
from Memory.storage.experience_store import ExperienceStore, Experience
from Memory.storage.database import db_manager
from Memory.consolidator.tasks.emotion_timeline_task import update_emotion_timeline


@pytest.fixture
def clean_db():
    """清理数据库的fixture。"""
    # 确保数据库已初始化
    if not db_manager.is_initialized:
        db_manager.initialize()

    # 清理测试数据（使用多个模式）
    with db_manager.transaction() as cursor:
        cursor.execute("DELETE FROM entities WHERE name LIKE 'test_freq_%'")
        cursor.execute("DELETE FROM cross_edges WHERE from_id LIKE 'test_freq_%'")
        cursor.execute("DELETE FROM entities WHERE name LIKE 'EmotionPerson%'")
        cursor.execute("DELETE FROM cross_edges WHERE from_id LIKE 'emotion_%'")
        cursor.execute("DELETE FROM experiences WHERE id LIKE 'emotion_%'")
        cursor.execute("DELETE FROM entities WHERE name LIKE '频繁%'")
        cursor.execute("DELETE FROM entities WHERE name LIKE '低频%'")
        cursor.execute("DELETE FROM entities WHERE name LIKE '地点%'")

    yield

    # 测试后清理
    with db_manager.transaction() as cursor:
        cursor.execute("DELETE FROM entities WHERE name LIKE 'test_freq_%'")
        cursor.execute("DELETE FROM cross_edges WHERE from_id LIKE 'test_freq_%'")
        cursor.execute("DELETE FROM entities WHERE name LIKE 'EmotionPerson%'")
        cursor.execute("DELETE FROM cross_edges WHERE from_id LIKE 'emotion_%'")
        cursor.execute("DELETE FROM experiences WHERE id LIKE 'emotion_%'")
        cursor.execute("DELETE FROM entities WHERE name LIKE '频繁%'")
        cursor.execute("DELETE FROM entities WHERE name LIKE '低频%'")
        cursor.execute("DELETE FROM entities WHERE name LIKE '地点%'")


def test_get_frequent_entities(clean_db):
    """测试get_frequent_entities方法。

    Test 1: 通过cross_edges统计实体出现次数
    Test 2: 只返回出现次数>=min_count的实体
    Test 3: 按出现次数降序排序
    Test 4: 支持指定entity_type和days参数
    """
    entity_store = EntityStore(db_manager)
    cross_edge_store = CrossEdgeStore(db_manager)

    # 创建测试实体
    import time

    timestamp = int(time.time() * 1000)

    person1 = Entity(
        id=f"test_freq_person1_{timestamp}", name=f"频繁人物1_{timestamp}", type="person"
    )
    person2 = Entity(
        id=f"test_freq_person2_{timestamp}", name=f"频繁人物2_{timestamp}", type="person"
    )
    person3 = Entity(
        id=f"test_freq_person3_{timestamp}", name=f"低频人物_{timestamp}", type="person"
    )
    place1 = Entity(id=f"test_freq_place1_{timestamp}", name=f"地点1_{timestamp}", type="place")

    entity_store.create(person1)
    entity_store.create(person2)
    entity_store.create(person3)
    entity_store.create(place1)

    # 创建cross_edges（模拟体验关联）
    # person1: 5次关联（高频）
    for i in range(5):
        edge = CrossEdge(
            from_id=f"test_freq_person1_{timestamp}",
            to_id=f"exp_{i}_{timestamp}",
            context=f"测试体验{i}",
        )
        cross_edge_store.create(edge)

    # person2: 3次关联（刚好达到阈值）
    for i in range(3):
        edge = CrossEdge(
            from_id=f"test_freq_person2_{timestamp}",
            to_id=f"exp_{i+5}_{timestamp}",
            context=f"测试体验{i+5}",
        )
        cross_edge_store.create(edge)

    # person3: 1次关联（低于阈值）
    edge = CrossEdge(
        from_id=f"test_freq_person3_{timestamp}", to_id=f"exp_8_{timestamp}", context="测试体验8"
    )
    cross_edge_store.create(edge)

    # place1: 4次关联（但不是person类型）
    for i in range(4):
        edge = CrossEdge(
            from_id=f"test_freq_place1_{timestamp}",
            to_id=f"exp_{i+9}_{timestamp}",
            context=f"测试体验{i+9}",
        )
        cross_edge_store.create(edge)

    # Test 1 & 3: 查询高频person实体，按出现次数降序
    frequent_persons = entity_store.get_frequent_entities(
        entity_type="person", days=30, min_count=3
    )

    # 应该返回2个person（person1和person2）
    assert len(frequent_persons) == 2
    assert frequent_persons[0].id == f"test_freq_person1_{timestamp}"
    assert frequent_persons[1].id == f"test_freq_person2_{timestamp}"
    # 验证按出现次数降序排序
    assert getattr(frequent_persons[0], "_appearance_count") == 5
    assert getattr(frequent_persons[1], "_appearance_count") == 3

    # Test 2: 测试min_count过滤
    # min_count=4应该只返回person1
    frequent_persons_high = entity_store.get_frequent_entities(
        entity_type="person", days=30, min_count=4
    )
    assert len(frequent_persons_high) == 1
    assert frequent_persons_high[0].id == f"test_freq_person1_{timestamp}"

    # Test 4: 测试entity_type过滤
    # 查询place类型
    frequent_places = entity_store.get_frequent_entities(entity_type="place", days=30, min_count=3)
    assert len(frequent_places) == 1
    assert frequent_places[0].id == f"test_freq_place1_{timestamp}"
    assert getattr(frequent_places[0], "_appearance_count") == 4


@pytest.fixture
def mock_llm_client_emotion():
    """Mock LLM客户端 for emotion timeline。"""
    client = Mock()
    client.call_json = Mock(
        return_value={
            "overall_trend": "warming",
            "key_events": ["初次见面", "深入交谈"],
            "relationship_status": "友好",
        }
    )
    return client


def test_emotion_update(clean_db, mock_llm_client_emotion):
    """测试update_emotion_timeline函数。

    Test 1: 调用get_frequent_entities()获取高频person
    Test 2: 通过cross_edges获取相关体验
    Test 3: LLM总结情感变化趋势
    Test 4: 更新实体的emotion_timeline字段
    Test 5: 返回更新的实体数量
    """
    entity_store = EntityStore(db_manager)
    cross_edge_store = CrossEdgeStore(db_manager)
    exp_store = ExperienceStore(db_manager)

    # 创建测试实体（使用更长的timestamp确保唯一性）
    import time

    timestamp = int(time.time() * 1000000)  # 更长的时间戳

    person = Entity(
        id=f"emotion_p_{timestamp}", name=f"EmotionPerson{timestamp}", type="person", properties={}
    )
    entity_store.create(person)

    # 创建测试体验
    exp1 = Experience(
        id=f"emotion_e1_{timestamp}",
        L0_text="和测试人物愉快交谈",
        L1_text="交谈",
        L2_text="愉快",
        L3_raw="完整原文",
        emotion_category="joy",
        emotion_intensity=0.8,
        emotion_target=f"EmotionPerson{timestamp}",
        created_at=datetime.now().isoformat(),
    )
    exp2 = Experience(
        id=f"emotion_e2_{timestamp}",
        L0_text="和测试人物深入讨论",
        L1_text="讨论",
        L2_text="深入",
        L3_raw="完整原文2",
        emotion_category="interest",
        emotion_intensity=0.7,
        emotion_target=f"EmotionPerson{timestamp}",
        created_at=(datetime.now() - timedelta(days=1)).isoformat(),
    )
    exp_store.create(exp1)
    exp_store.create(exp2)

    # 创建cross_edges
    edge1 = CrossEdge(
        from_id=f"emotion_p_{timestamp}", to_id=f"emotion_e1_{timestamp}", context="交谈体验"
    )
    edge2 = CrossEdge(
        from_id=f"emotion_p_{timestamp}", to_id=f"emotion_e2_{timestamp}", context="讨论体验"
    )
    cross_edge_store.create(edge1)
    cross_edge_store.create(edge2)

    # 创建更多cross_edges以达到min_count=3的阈值
    exp3 = Experience(
        id=f"emotion_e3_{timestamp}",
        L0_text="和测试人物再次相遇",
        L1_text="相遇",
        L2_text="再次",
        L3_raw="完整原文3",
        emotion_category="joy",
        emotion_intensity=0.6,
        emotion_target=f"EmotionPerson{timestamp}",
        created_at=(datetime.now() - timedelta(days=2)).isoformat(),
    )
    exp_store.create(exp3)
    edge3 = CrossEdge(
        from_id=f"emotion_p_{timestamp}", to_id=f"emotion_e3_{timestamp}", context="相遇体验"
    )
    cross_edge_store.create(edge3)

    # 调用update_emotion_timeline
    result = update_emotion_timeline(
        experiences=[],
        llm_client=mock_llm_client_emotion,
        entity_store=entity_store,
        experience_store=exp_store,
    )

    # 验证结果
    assert result["evaluated_count"] == 1
    assert result["updated_count"] == 1

    # 验证LLM被调用
    assert mock_llm_client_emotion.call_json.called

    # 验证实体的properties被更新
    updated_person = entity_store.get(f"emotion_p_{timestamp}")
    assert updated_person.properties is not None
    assert "_emotion_timeline" in updated_person.properties
    assert updated_person.properties["_emotion_timeline"]["overall_trend"] == "warming"
    assert updated_person.properties["_emotion_timeline"]["record_count"] == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
