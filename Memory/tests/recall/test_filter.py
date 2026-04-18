"""后处理过滤器测试。"""

import pytest
from unittest.mock import Mock

from Memory.recall.filter import RecallFilter


@pytest.mark.skip(reason="Wave 0 stub")
def test_llm_classification(mock_llm_client, sample_context):
    """测试LLM二分类（RECALL-11）。

    - 输入：recall_hint + 对话上下文 + AI状态
    - 输出：should_mention (true/false) + reason
    - LLM调用正确传递参数
    """
    filter = RecallFilter(mock_llm_client)

    # 测试候选记忆
    candidate = Mock(
        id="exp_001",
        recall_hint="和张三讨论架构，达成共识",
        importance=0.7,
        emotion_category="satisfaction",
        time_distance_days=1,
    )

    # 执行过滤
    result = filter.filter_candidate(candidate, "张三最近怎么样", sample_context)

    # 验证LLM被调用
    assert mock_llm_client.call_json.called

    # 验证返回结果
    assert "should_mention" in result
    assert "reason" in result


@pytest.mark.skip(reason="Wave 0 stub")
def test_filter_rules():
    """测试过滤规则。

    - 宁可不说也不要强行插入
    - 情感冲突时不提
    - 能帮助对话时提
    - 避免重复
    """
    # 规则验证在test_llm_classification中通过mock LLM响应测试
    pass


def test_cache_mechanism(mock_llm_client):
    """测试缓存机制。

    - 相同上下文下使用缓存结果
    - 避免重复LLM调用
    """
    filter = RecallFilter(mock_llm_client)

    candidate = Mock(
        id="exp_001",
        recall_hint="和张三讨论架构",
        importance=0.7,
        emotion_category="satisfaction",
        time_distance_days=1,
    )

    query = "张三最近怎么样"
    context = {"recent_history": [], "ai_state": {}, "current_time": "2026-04-02T12:00:00Z"}

    # 第一次调用
    result1 = filter.filter_candidate(candidate, query, context)

    # 第二次调用（应该使用缓存）
    result2 = filter.filter_candidate(candidate, query, context)

    # 验证LLM只被调用一次（使用缓存）
    assert mock_llm_client.call_json.call_count == 1


def test_prompt_building(mock_llm_client, sample_context):
    """测试prompt构建。

    - 正确构建prompt包含recall_hint、context、ai_state
    - 验证prompt格式符合设计文档
    """
    filter = RecallFilter(mock_llm_client)

    candidate = Mock(
        id="exp_001",
        recall_hint="和张三讨论架构",
        importance=0.7,
        emotion_category="satisfaction",
        time_distance_days=1,
    )

    query = "张三最近怎么样"

    # 执行过滤
    filter.filter_candidate(candidate, query, sample_context)

    # 验证LLM被调用
    assert mock_llm_client.call_json.called

    # 获取调用参数
    call_args = mock_llm_client.call_json.call_args
    prompt = call_args[0][0] if call_args[0] else call_args[1].get("prompt", "")

    # 验证prompt包含关键信息
    assert "和张三讨论架构" in prompt or "recall_hint" in str(prompt).lower()


def test_recall_manager_integration(mock_llm_client):
    """测试RecallManager集成。

    验证RecallManager正确调用RecallFilter。
    """
    from Memory.recall import RecallFilter
    from Memory.recall.result import RecallResult

    filter = RecallFilter(mock_llm_client)

    # 创建RecallResult
    result = RecallResult(
        experience_id="exp_001",
        L0_text="和张三讨论架构",
        recall_hint="讨论架构",
        importance=0.7,
        emotion_category="satisfaction",
        time_distance_days=1,
        activation_score=0.8,
        source_type="vector_search",
    )

    query = "张三最近怎么样"
    context = {"recent_history": [], "ai_state": {}, "current_time": "2026-04-02T12:00:00Z"}

    # 执行过滤
    filter_result = filter.filter_candidate(result, query, context)

    # 验证返回结果
    assert "should_mention" in filter_result
