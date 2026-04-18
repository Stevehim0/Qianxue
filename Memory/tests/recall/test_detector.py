"""触发检测器测试。"""

import pytest
from unittest.mock import Mock

from Memory.recall.detector import TriggerDetector


@pytest.mark.skip(reason="Wave 0 stub")
def test_trigger_signals(mock_entity_store):
    """测试三种触发信号（RECALL-01）。

    - 实体命中：用户提到已知实体名
    - 时间指代：用户使用"上次"、"之前"等时间指代词
    - 状态变化：用户描述自己的状态变化
    """
    detector = TriggerDetector(mock_entity_store)

    # 实体命中
    assert detector.should_trigger("张三最近怎么样") is True

    # 时间指代
    assert detector.should_trigger("上次我们去的那家店") is True

    # 状态变化
    assert detector.should_trigger("今天我出门了") is True


@pytest.mark.skip(reason="Wave 0 stub")
def test_negative_signals():
    """测试不触发信号（RECALL-02）。

    - 简单问候：你好、嗨等
    - 简单确认：好的、是的等
    - 不包含触发信号的普通对话
    """
    detector = TriggerDetector(Mock())

    # 简单问候
    assert detector.should_trigger("你好") is False

    # 简单确认
    assert detector.should_trigger("好的") is False

    # 普通对话
    assert detector.should_trigger("我想了解一下系统架构") is False


@pytest.mark.skip(reason="Wave 0 stub")
def test_keyword_extraction(mock_entity_store, sample_user_input, sample_context):
    """测试关键词提取规则（RECALL-03）。

    - 实体命中 → 提取实体名
    - 时间指代 → 提取时间范围 + 主题
    - 状态变化 → 提取动作部分
    """
    detector = TriggerDetector(mock_entity_store)

    # 实体命中提取
    keywords = detector.extract_keywords("张三最近怎么样", sample_context)
    assert keywords == {"type": "entity", "entity": "张三"}

    # 时间指代提取
    keywords = detector.extract_keywords("上次我们去的那家店", sample_context)
    assert keywords["type"] == "time_reference"
    assert "time_range" in keywords
    assert "topic" in keywords

    # 状态变化提取
    keywords = detector.extract_keywords("今天我出门了", sample_context)
    assert keywords == {"type": "state_change", "action": "出门了"}
