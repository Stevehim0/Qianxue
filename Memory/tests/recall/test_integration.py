"""召回层端到端集成测试。"""

import pytest
from unittest.mock import Mock, MagicMock

from Memory.recall import RecallManager, RecallResult, AdjacencyCache


def test_end_to_end_recall(
    mock_entity_store,
    mock_experience_store,
    mock_edge_store,
    mock_vector_store,
    mock_embedding_service,
    mock_llm_client,
    sample_user_input,
    sample_context,
):
    """端到端召回流程测试（Integration）。

    完整流程：
    1. 触发判断（实体命中"张三"）
    2. 提取关键词["张三"]
    3. 向量检索找到相关记忆
    4. 激活扩散找到间接关联记忆（实际验证AdjacencyCache.spread调用）
    5. 合并排序
    6. 后处理过滤
    7. 返回最终召回结果
    """
    # 1. 创建AdjacencyCache实例
    adjacency_cache = AdjacencyCache(edge_store=mock_edge_store, hop_decay=0.6)

    # 2. 创建RecallManager（注入所有依赖）
    manager = RecallManager(
        experience_store=mock_experience_store,
        entity_store=mock_entity_store,
        edge_store=mock_edge_store,
        vector_store=mock_vector_store,
        embedding_service=mock_embedding_service,
        llm_client=mock_llm_client,
        adjacency_cache=adjacency_cache,  # 注入AdjacencyCache
    )

    # 3. 模拟用户输入："张三最近怎么样"
    query = "张三最近怎么样"

    # 4. Mock返回数据

    # 4.1 TriggerDetector: 实体匹配
    mock_entity_store.get_all.return_value = [Mock(id="ent_001", name="张三", type="person")]

    # 4.2 EmbeddingService: 编码关键词
    mock_embedding_service.encode.return_value = [0.1] * 768  # 768维向量

    # 4.3 VectorStore: 向量检索
    mock_vector_store.query_experience.return_value = {
        "ids": [["exp_001", "exp_002"]],
        "distances": [[0.15, 0.25]],
    }

    # 4.4 ExperienceStore: 获取完整experience
    exp1 = Mock(
        id="exp_001",
        L0_text="和张三去吃饭",
        recall_hint="张三喜欢辣菜",
        importance=0.8,
        emotion_category="joy",
        created_at="2026-03-25T10:00:00",
    )
    exp2 = Mock(
        id="exp_002",
        L0_text="张三今天不开心",
        recall_hint=None,
        importance=0.6,
        emotion_category="sadness",
        created_at="2026-03-26T14:00:00",
    )

    # 设置mock返回值
    def mock_get(exp_id: str):
        if exp_id == "exp_001":
            return exp1
        elif exp_id == "exp_002":
            return exp2
        return None

    mock_experience_store.get.side_effect = mock_get

    # 4.5 AdjacencyCache: Mock激活扩散返回候选集B
    # 使用MagicMock验证spread()被调用
    adjacency_cache.spread = MagicMock(return_value={})

    # 4.6 LLMClient: 后处理过滤（暂时不实现，后续plan添加）
    # mock_llm_client.call_json.return_value = {
    #     'should_mention': True,
    #     'reason': '与用户查询相关',
    #     'how_to_mention': '在回复开头自然提及'
    # }

    # 5. 执行召回
    results = manager.recall(query, sample_context)

    # 6. 验证结果
    assert len(results) > 0, "应该返回召回结果"

    # 验证调用了正确的组件
    mock_embedding_service.encode.assert_called()  # 编码关键词
    mock_vector_store.query_experience.assert_called()  # 向量检索
    mock_experience_store.get.assert_called()  # 获取完整experience

    # 验证AdjacencyCache.spread()被调用（关键验证）
    adjacency_cache.spread.assert_called_once()
    spread_call_args = adjacency_cache.spread.call_args
    assert spread_call_args is not None, "AdjacencyCache.spread()应该被调用"

    # 验证spread()参数
    start_nodes = (
        spread_call_args[0][0]
        if spread_call_args[0]
        else spread_call_args[1].get("start_nodes", [])
    )
    assert len(start_nodes) > 0, "spread()应该接收起始节点列表"
    assert "exp_001" in start_nodes or "exp_002" in start_nodes, "起始节点应包含向量检索结果"

    # 验证召回结果格式
    result = results[0]
    assert isinstance(result, RecallResult)
    assert result.experience_id in ["exp_001", "exp_002"]
    assert result.L0_text is not None
    assert result.activation_score > 0

    # 验证recall_hint优先使用
    if result.experience_id == "exp_001":
        assert result.recall_hint == "张三喜欢辣菜"
    else:
        assert result.recall_hint == result.L0_text


def test_no_trigger_case(mock_entity_store, mock_experience_store, sample_context):
    """测试不触发召回的场景（RECALL-02）。"""
    from Memory.recall import RecallManager

    manager = RecallManager(
        experience_store=mock_experience_store,
        entity_store=mock_entity_store,
        edge_store=Mock(),
        vector_store=Mock(),
        embedding_service=Mock(),
    )

    # 用户说"你好"（不触发）
    query = "你好"

    # Mock实体匹配返回空（无实体）
    mock_entity_store.get_all.return_value = []

    # 执行召回
    results = manager.recall(query, sample_context)

    # 验证：不触发，返回空列表
    assert len(results) == 0


def test_empty_vector_search_case(
    mock_entity_store,
    mock_experience_store,
    mock_vector_store,
    mock_embedding_service,
    sample_context,
):
    """测试向量检索无结果的情况。"""
    from Memory.recall import RecallManager, AdjacencyCache

    adjacency_cache = Mock()  # Mock AdjacencyCache
    adjacency_cache.spread.return_value = {}

    manager = RecallManager(
        experience_store=mock_experience_store,
        entity_store=mock_entity_store,
        edge_store=Mock(),
        vector_store=mock_vector_store,
        embedding_service=mock_embedding_service,
        adjacency_cache=adjacency_cache,
    )

    query = "张三最近怎么样"

    # Mock实体匹配
    mock_entity_store.get_all.return_value = [Mock(id="ent_001", name="张三", type="person")]

    # Mock向量检索返回空结果
    mock_vector_store.query_experience.return_value = {"ids": [[]], "distances": [[]]}

    # 执行召回
    results = manager.recall(query, sample_context)

    # 验证：无结果，返回空列表
    assert len(results) == 0


def test_llm_failure_case(
    mock_entity_store,
    mock_experience_store,
    mock_vector_store,
    mock_embedding_service,
    mock_llm_client,
    sample_context,
):
    """测试LLM调用失败的情况（降级策略）。"""
    from Memory.recall import RecallManager, AdjacencyCache

    adjacency_cache = Mock()
    adjacency_cache.spread.return_value = {}

    manager = RecallManager(
        experience_store=mock_experience_store,
        entity_store=mock_entity_store,
        edge_store=Mock(),
        vector_store=mock_vector_store,
        embedding_service=mock_embedding_service,
        llm_client=mock_llm_client,
        adjacency_cache=adjacency_cache,
    )

    query = "张三最近怎么样"

    # Mock所有组件
    mock_entity_store.get_all.return_value = [Mock(id="ent_001", name="张三", type="person")]
    mock_embedding_service.encode.return_value = [0.1] * 768
    mock_vector_store.query_experience.return_value = {"ids": [["exp_001"]], "distances": [[0.15]]}
    exp = Mock(
        id="exp_001",
        L0_text="和张三去吃饭",
        recall_hint="张三喜欢辣菜",
        importance=0.8,
        emotion_category="joy",
        created_at="2026-03-25T10:00:00",
    )
    mock_experience_store.get.return_value = exp

    # Mock LLM调用失败
    mock_llm_client.call_json.side_effect = Exception("LLM API error")

    # 执行召回
    results = manager.recall(query, sample_context)

    # 验证：LLM失败，保守策略返回空列表
    assert len(results) == 0


def test_expand_memory_levels(mock_experience_store):
    """测试深度展开接口 - 不同层级（RECALL-12）。"""
    from Memory.recall import RecallManager

    manager = RecallManager(
        experience_store=mock_experience_store,
        entity_store=Mock(),
        edge_store=Mock(),
        vector_store=Mock(),
        embedding_service=Mock(),
    )

    # Mock完整Experience
    exp = Mock(
        id="exp_001", L0_text="L0摘要", L1_text="L1要点", L2_text="L2细节", L3_raw="L3完整原文"
    )
    mock_experience_store.get.return_value = exp

    # 测试不同层级
    result_0 = manager.expand_memory("exp_001", level=0)
    assert "L0" in result_0
    assert "L1" not in result_0

    result_1 = manager.expand_memory("exp_001", level=1)
    assert "L0" in result_1
    assert "L1" in result_1
    assert "L2" not in result_1

    result_2 = manager.expand_memory("exp_001", level=2)
    assert "L0" in result_2
    assert "L1" in result_2
    assert "L2" in result_2
    assert "L3" not in result_2

    result_3 = manager.expand_memory("exp_001", level=3)
    assert "L0" in result_3
    assert "L1" in result_3
    assert "L2" in result_3
    assert "L3" in result_3
