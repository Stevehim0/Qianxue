"""召回层测试配置。

提供共享fixtures和测试工具。
"""

import pytest
from unittest.mock import Mock, MagicMock
from datetime import datetime, timedelta
from typing import Dict, Any

import numpy as np


@pytest.fixture
def mock_entity_store():
    """模拟EntityStore。

    提供get_all()和get_by_name()方法。
    """
    store = Mock()

    # 测试实体列表
    test_entities = [
        Mock(id="entity_001", name="张三", type="person"),
        Mock(id="entity_002", name="李四", type="person"),
        Mock(id="entity_003", name="王五", type="person"),
        Mock(id="entity_004", name="那家店", type="place"),
    ]

    # get_all()返回所有实体
    store.get_all.return_value = test_entities

    # get_by_name()精确匹配
    def mock_get_by_name(name: str):
        for entity in test_entities:
            if entity.name == name:
                return entity
        return None

    store.get_by_name.side_effect = mock_get_by_name

    return store


@pytest.fixture
def mock_experience_store():
    """模拟ExperienceStore。

    提供get()和get_entity_stats()方法。
    """
    store = Mock()

    # 测试Experience对象
    test_experience = Mock(
        id="exp_20260331_120000",
        L0_text="和张三讨论了一下午架构，虽然吵了几句但最后达成共识，很满足",
        L1_text="讨论架构，达成共识",
        L2_text="和张三讨论系统架构设计，在数据库选型上有分歧，经过深入交流后达成一致",
        L3_raw="今天下午和张三开了个会，讨论新系统的架构设计。我们一开始在数据库选型上有分歧，他主张PostgreSQL，我觉得MySQL就够了。吵了几句后，我们详细对比了两者优劣，最后决定用PostgreSQL。虽然过程有点激烈，但最后达成共识的感觉很好。",
        importance=0.7,
        emotion_category="satisfaction",
        emotion_intensity=0.8,
        recall_hint="和张三讨论架构，达成共识",
        created_at="2026-03-31T12:00:00Z",
    )

    # get()返回测试Experience
    def mock_get(exp_id: str):
        if exp_id == "exp_20260331_120000":
            return test_experience
        return None

    store.get.side_effect = mock_get

    # get_entity_stats()返回统计信息
    def mock_get_entity_stats(entity_name: str):
        # 模拟张三出现5次，跨4天
        if entity_name == "张三":
            return {"count": 5, "unique_days": 4}
        # 模拟李四出现2次，跨2天
        elif entity_name == "李四":
            return {"count": 2, "unique_days": 2}
        return {"count": 0, "unique_days": 0}

    store.get_entity_stats.side_effect = mock_get_entity_stats

    return store


@pytest.fixture
def mock_edge_store():
    """模拟ExperienceEdgeStore。

    提供get_all()方法返回测试边列表。
    """
    store = Mock()

    # 测试边列表
    test_edges = [
        Mock(
            id=1,
            from_id="exp_20260331_120000",
            to_id="exp_20260331_140000",
            type="temporal",
            weight=1.0,
            decayed_weight=0.9,
        ),
        Mock(
            id=2,
            from_id="exp_20260331_120000",
            to_id="exp_20260331_160000",
            type="thematic",
            weight=0.8,
            decayed_weight=0.7,
        ),
        Mock(
            id=3,
            from_id="exp_20260331_140000",
            to_id="exp_20260331_180000",
            type="causal",
            weight=0.9,
            decayed_weight=0.6,
        ),
        Mock(
            id=4,
            from_id="exp_20260331_120000",
            to_id="exp_20260401_100000",
            type="associative",
            weight=0.7,
            decayed_weight=0.5,
        ),
    ]

    store.get_all.return_value = test_edges

    return store


@pytest.fixture
def mock_vector_store():
    """模拟VectorStore（ChromaDB）。

    提供query_experience()方法返回候选结果。
    """
    store = Mock()

    # 模拟向量检索结果
    test_candidates = [
        {
            "id": "exp_20260331_120000",
            "score": 0.85,
            "metadata": {
                "L0_text": "和张三讨论了一下午架构，虽然吵了几句但最后达成共识，很满足",
                "importance": 0.7,
                "emotion_category": "satisfaction",
            },
        },
        {
            "id": "exp_20260331_140000",
            "score": 0.78,
            "metadata": {
                "L0_text": "和张三一起吃午饭，聊了聊家常",
                "importance": 0.5,
                "emotion_category": "joy",
            },
        },
        {
            "id": "exp_20260330_100000",
            "score": 0.72,
            "metadata": {
                "L0_text": "上次和李四去的那家餐厅很不错",
                "importance": 0.6,
                "emotion_category": "joy",
            },
        },
    ]

    store.query_experience.return_value = test_candidates

    return store


@pytest.fixture
def mock_llm_client():
    """模拟LLM客户端。

    提供call_json()方法返回测试JSON响应。
    """
    client = Mock()

    # 默认返回should_mention=True
    default_response = {
        "should_mention": True,
        "reason": "这段记忆与用户问题直接相关",
        "how_to_mention": "在回复开头自然提及",
    }
    client.call_json.return_value = default_response

    # call_with_retry()直接返回结果
    client.call_with_retry.return_value = "模拟LLM响应"

    return client


@pytest.fixture
def mock_profile_store():
    """模拟ProfileStore。

    提供get_by_name(), create(), update()方法。
    """
    store = Mock()

    # 默认返回None（档案不存在）
    store.get_by_name.return_value = None

    # create()返回档案ID
    store.create.return_value = "profile_zhangsan"

    # update()返回True
    store.update.return_value = True

    return store


@pytest.fixture
def sample_user_input():
    """示例用户输入。

    覆盖触发和不触发场景。
    """
    return [
        "张三最近怎么样",  # 实体命中 - 触发
        "上次我们去的那家店",  # 时间指代 - 触发
        "今天我出门了",  # 状态变化 - 触发
        "你好",  # 不触发
        "好的",  # 不触发
    ]


@pytest.fixture
def sample_context():
    """示例对话上下文。

    包含recent_history, ai_state, current_time。
    """
    now = datetime.now()

    return {
        "recent_history": [
            {"role": "user", "content": "你好"},
            {"role": "ai", "content": "你好！有什么我可以帮助你的吗？"},
            {"role": "user", "content": "我想了解一下系统架构"},
        ],
        "ai_state": {"mood": "neutral", "energy": 0.7, "focus": "system_design"},
        "current_time": now.isoformat(),
    }


@pytest.fixture
def sample_keywords():
    """示例提取的关键词。

    对应不同触发信号。
    """
    return {
        "entity_hit": "张三",
        "time_reference": {"time_range": "最近", "topic": "怎么样"},
        "state_change": "出门了",
    }


@pytest.fixture
def mock_embedding_service():
    """模拟EmbeddingService。

    提供encode()方法返回测试向量。
    """
    service = Mock()

    # 返回768维测试向量（bge-base-zh维度）
    test_vector = np.random.rand(768).astype(np.float32)
    service.encode.return_value = test_vector

    return service
