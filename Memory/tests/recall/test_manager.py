"""召回管理器测试。"""

import pytest
from unittest.mock import Mock

from Memory.recall.manager import RecallManager


@pytest.mark.skip(reason="Wave 0 stub")
def test_vector_search(mock_vector_store, mock_experience_store):
    """测试向量检索（RECALL-04）。

    - 在ChromaDB的experience_L0集合中查询
    - 返回相似度排序的候选结果
    - 候选结果包含id, score, metadata
    """
    manager = RecallManager(
        experience_store=mock_experience_store,
        entity_store=Mock(),
        edge_store=Mock(),
        vector_store=mock_vector_store,
        llm_client=Mock(),
        profile_manager=Mock(),
        adjacency_cache=Mock(),
    )

    # 执行向量检索
    candidates = manager._vector_search(keywords="张三")

    # 验证结果
    assert len(candidates) > 0
    assert "id" in candidates[0]
    assert "score" in candidates[0]


@pytest.mark.skip(reason="Wave 0 stub")
def test_merge_rank():
    """测试候选集合并排序（RECALL-09）。

    - 合并向量检索和激活扩散的候选集
    - 按激活分数排序
    - 去重（同一记忆只保留最高分）
    """
    # 候选集合并逻辑在RecallManager中实现
    pass


@pytest.mark.skip(reason="Wave 0 stub")
def test_recall_hint(mock_experience_store):
    """测试recall_hint取回（RECALL-10）。

    - 优先使用experience.recall_hint
    - recall_hint为空时使用L0_text
    - 正确从数据库取回完整Experience对象
    """
    manager = RecallManager(
        experience_store=mock_experience_store,
        entity_store=Mock(),
        edge_store=Mock(),
        vector_store=Mock(),
        llm_client=Mock(),
        profile_manager=Mock(),
        adjacency_cache=Mock(),
    )

    # 测试recall_hint取回
    candidate = Mock(id="exp_20260331_120000")
    manager._fetch_recall_hint(candidate)

    # 验证recall_hint被正确设置
    assert candidate.recall_hint is not None


@pytest.mark.skip(reason="Wave 0 stub")
def test_expand_memory(mock_experience_store):
    """测试深度展开接口（RECALL-12）。

    - level=1返回L0+L1
    - level=2返回L0+L1+L2
    - level=3返回L0+L1+L2+L3
    - AI主动调用，按需展开
    """
    manager = RecallManager(
        experience_store=mock_experience_store,
        entity_store=Mock(),
        edge_store=Mock(),
        vector_store=Mock(),
        llm_client=Mock(),
        profile_manager=Mock(),
        adjacency_cache=Mock(),
    )

    # 展开到L1
    result = manager.expand_memory("exp_20260331_120000", level=1)
    assert "L0" in result
    assert "L1" in result
    assert "L2" not in result
    assert "L3" not in result

    # 展开到L3
    result = manager.expand_memory("exp_20260331_120000", level=3)
    assert "L0" in result
    assert "L1" in result
    assert "L2" in result
    assert "L3" in result
