"""个人档案管理器测试。"""

import pytest
from unittest.mock import Mock

from Memory.recall.profile_manager import ProfileManager


@pytest.mark.skip(reason="Wave 0 stub")
def test_profile_loading(mock_profile_store, mock_experience_store, mock_entity_store):
    """测试个人档案加载（RECALL-13）。

    - 根据实体名加载档案
    - 档案不存在时返回None
    - 档案包含basic和interaction_style
    """
    manager = ProfileManager(mock_profile_store, mock_experience_store, mock_entity_store)

    # 加载存在的档案
    profile = manager.load_profile("张三")
    # mock返回None，实际实现会返回Profile对象

    # 加载不存在的档案
    profile = manager.load_profile("不存在的人")
    assert profile is None


@pytest.mark.skip(reason="Wave 0 stub")
def test_progressive_creation(mock_profile_store, mock_experience_store, mock_entity_store):
    """测试渐进创建。

    - 实体出现>=3次且>=3天时创建
    - 根据上下文设置初始相处方式
    - 只创建一次，避免重复
    """
    manager = ProfileManager(mock_profile_store, mock_experience_store, mock_entity_store)

    # 张三：5次，4天 - 应该创建
    should_create = manager.check_and_create_profile("张三", Mock())
    assert should_create is True

    # 李四：2次，2天 - 不应该创建
    should_create = manager.check_and_create_profile("李四", Mock())
    assert should_create is False


def test_threshold_not_met(mock_profile_store, mock_experience_store, mock_entity_store):
    """测试阈值未达到时不创建。

    - 出现次数<3时不创建
    - 跨天数<3时不创建
    - 两个条件都满足才创建
    """
    manager = ProfileManager(mock_profile_store, mock_experience_store, mock_entity_store)

    # 出现1次 - 不应该创建
    mock_experience_store.get_entity_stats.return_value = {"count": 1, "unique_days": 1}
    should_create = manager.check_and_create_profile("新人", Mock())
    assert should_create is False

    # 出现3次但只有1天 - 不应该创建
    mock_experience_store.get_entity_stats.return_value = {"count": 3, "unique_days": 1}
    should_create = manager.check_and_create_profile("频繁出现", Mock())
    assert should_create is False


def test_initial_style_derivation(mock_profile_store, mock_experience_store, mock_entity_store):
    """测试初始相处方式推导（D-15）。

    - 根据emotion_category推导初始参数
    - 根据time_of_day推导初始参数
    - 6个维度都在合理范围内（0-1）
    """
    manager = ProfileManager(mock_profile_store, mock_experience_store, mock_entity_store)

    # Mock统计信息达到阈值
    mock_experience_store.get_entity_stats.return_value = {"count": 5, "unique_days": 4}
    mock_profile_store.get_by_name.return_value = None

    # Mock实体
    mock_entity = Mock()
    mock_entity.id = "entity_001"
    mock_entity.name = "张三"
    mock_entity.type = "person"
    mock_entity.properties = {}
    mock_entity_store.get_by_name.return_value = mock_entity

    # Mock体验数据
    experience = Mock()
    experience.emotion_category = "joy"  # 开心情感
    experience.context_time_of_day = "afternoon"  # 下午时段
    experience.created_at = "2026-04-15T12:00:00"

    # 调用检查和创建
    manager.check_and_create_profile("张三", experience)

    # 验证create被调用
    assert mock_profile_store.create.called

    # 获取创建的profile参数
    call_args = mock_profile_store.create.call_args
    if call_args[0]:
        profile = call_args[0][0]
        # 验证 interaction_style 是字典且在合理范围内
        style = profile.interaction_style
        assert isinstance(style, dict), f"interaction_style should be dict, got {type(style)}"
        assert 0 <= style["warmth"] <= 1
        assert 0 <= style["formality"] <= 1
        assert 0 <= style["humor"] <= 1
        assert 0 <= style["proactivity"] <= 1
        assert 0 <= style["directness"] <= 1
        assert 0 <= style["boundaries"] <= 1
