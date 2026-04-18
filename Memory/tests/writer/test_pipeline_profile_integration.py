"""WriterPipeline-ProfileManager集成测试。

测试验证WriterPipeline是否正确集成ProfileManager.check_and_create_profile()。
这是Gap Closure测试的一部分，验证当前broken state。

Gap Coverage:
- Gap 1: WriterPipeline未调用ProfileManager.check_and_create_profile()
- Gap 2: PROFILE-01和PROFILE-02部分实现（代码存在但未集成）
- Gap 3: 阈值逻辑存在但未被外部调用

Reference: .planning/phases/10-召回层/10-VERIFICATION.md
"""

import pytest
from unittest.mock import Mock, MagicMock, call
from datetime import datetime

from Memory.writer.pipeline import WriterPipeline
from Memory.writer.raw_recorder import RawRecorder
from Memory.recall.profile_manager import ProfileManager
from Memory.storage.experience_store import Experience, ExperienceStore
from Memory.storage.entity_store import EntityStore
from Memory.storage.profile_store import ProfileStore
from Memory.llm.factory import LLMFactory


@pytest.mark.skip(reason="Gap 1: 未集成 - 待13-02修复")
def test_writer_pipeline_without_profile_manager():
    """验证WriterPipeline构造函数可以接受profile_manager参数。

    Gap 1验证：WriterPipeline需要在写入新体验后调用ProfileManager.check_and_create_profile()

    测试步骤：
    1. 创建Mock ProfileManager
    2. 验证WriterPipeline构造函数可以接受profile_manager参数
    3. 验证process_event()方法可以正常执行

    Expected: 构造函数接受参数，但process_event()不调用check_and_create_profile()
    """
    # 创建Mock ProfileManager
    mock_profile_manager = Mock(spec=ProfileManager)
    mock_profile_manager.check_and_create_profile.return_value = False

    # 创建WriterPipeline实例，传入profile_manager参数
    pipeline = WriterPipeline(
        profile_manager=mock_profile_manager,
    )

    # 验证profile_manager被正确存储
    assert pipeline.profile_manager == mock_profile_manager

    # 调用process_event()处理一个对话
    exp_id = pipeline.process_event(
        role="user",
        content="今天和张三去爬山",
    )

    # 验证返回了experience_id
    assert exp_id is not None
    assert exp_id.startswith("exp_")

    # Gap 1验证：check_and_create_profile()未被调用
    # 当前状态：WriterPipeline未集成ProfileManager
    mock_profile_manager.check_and_create_profile.assert_not_called()

    print("✓ Gap 1验证通过：WriterPipeline未调用ProfileManager.check_and_create_profile()")


@pytest.mark.skip(reason="Gap 2: 部分实现 - 待13-02修复")
def test_writer_pipeline_with_profile_manager_not_called():
    """验证WriterPipeline虽然接受profile_manager参数，但未实际调用。

    Gap 2验证：PROFILE-01和PROFILE-02部分实现（代码存在但未集成）

    测试步骤：
    1. 创建WriterPipeline实例，传入profile_manager参数
    2. 调用process_event()处理一个包含实体的对话
    3. 验证profile_manager.check_and_create_profile()调用次数为0

    Expected: 虽然传入了profile_manager，但未被调用（当前broken state）

    注意：此测试与test_writer_pipeline_without_profile_manager的区别在于，
    这里明确验证即使传入了profile_manager，也不被调用。
    """
    # 创建Mock ProfileManager
    mock_profile_manager = Mock(spec=ProfileManager)
    mock_profile_manager.check_and_create_profile.return_value = False

    # 创建Mock LLM客户端
    mock_llm = Mock()
    mock_llm.call_with_retry.side_effect = [
        "和张三去爬山",  # L0摘要
        '{"entities": [{"name": "张三", "type": "person", "is_new": true, "relation_to_self": "朋友", "confidence": 0.9}]}',  # 实体识别
        '{"category": "joy", "intensity": 0.8, "valence": 0.7, "arousal": 0.6, "target": "爬山"}',  # 情感分析
    ]

    # 创建WriterPipeline实例
    pipeline = WriterPipeline(
        llm_client=mock_llm,
        profile_manager=mock_profile_manager,
    )

    # 调用process_event()处理包含实体的对话
    exp_id = pipeline.process_event(
        role="user",
        content="今天和张三去爬山，风景很美",
    )

    # 验证返回了experience_id
    assert exp_id is not None

    # Gap 2验证：check_and_create_profile()调用次数为0
    # 当前状态：即使传入profile_manager，WriterPipeline也未调用
    assert mock_profile_manager.check_and_create_profile.call_count == 0

    print("✓ Gap 2验证通过：PROFILE-01和PROFILE-02代码存在但未集成")


@pytest.mark.skip(reason="Gap 3: 未调用 - 待13-02修复")
def test_profile_manager_threshold_check_exists():
    """验证ProfileManager.check_and_create_profile()方法存在且逻辑正确。

    Gap 3验证：阈值逻辑存在但未被外部调用

    测试步骤：
    1. 验证ProfileManager.check_and_create_profile()方法存在
    2. 验证THRESHOLD_COUNT=3和THRESHOLD_DAYS=3常量存在
    3. 验证方法逻辑：检查count>=3且unique_days>=3
    4. 验证当阈值满足时，方法会创建档案

    Expected: ProfileManager方法完整实现，但未被WriterPipeline调用

    此测试验证ProfileManager本身的实现是正确的，
    问题在于WriterPipeline没有调用它（集成缺失）。
    """
    # 创建Mock stores
    mock_profile_store = Mock(spec=ProfileStore)
    mock_profile_store.get_by_name.return_value = None  # 档案不存在
    mock_profile_store.create.return_value = "profile_zhangsan"

    mock_experience_store = Mock(spec=ExperienceStore)
    # 模拟张三出现5次，跨4天（满足阈值：>=3次且>=3天）
    mock_experience_store.get_entity_stats.return_value = {
        "count": 5,
        "unique_days": 4,
    }
    # 模拟get()返回Experience对象
    mock_experience_store.get.return_value = Experience(
        id="exp_20260331_120000",
        L0_text="和张三去爬山",
        role="user",
        raw_content="今天和张三去爬山",
        created_at="2026-03-31T12:00:00Z",
    )

    mock_entity_store = Mock(spec=EntityStore)
    mock_entity_store.get_by_name.return_value = Mock(
        id="entity_001",
        name="张三",
        type="person",
        properties={"relation_to_self": "朋友"},
    )

    # 创建ProfileManager实例
    profile_manager = ProfileManager(
        profile_store=mock_profile_store,
        experience_store=mock_experience_store,
        entity_store=mock_entity_store,
    )

    # 验证阈值常量存在
    assert hasattr(profile_manager, "THRESHOLD_COUNT")
    assert hasattr(profile_manager, "THRESHOLD_DAYS")
    assert profile_manager.THRESHOLD_COUNT == 3
    assert profile_manager.THRESHOLD_DAYS == 3

    # 验证check_and_create_profile()方法存在
    assert hasattr(profile_manager, "check_and_create_profile")

    # 创建测试Experience对象
    test_experience = Experience(
        id="exp_20260331_120000",
        L0_text="和张三去爬山",
        role="user",
        raw_content="今天和张三去爬山",
        created_at="2026-03-31T12:00:00Z",
        emotion_category="joy",
        context_time_of_day="下午",
    )

    # 调用check_and_create_profile()
    result = profile_manager.check_and_create_profile("张三", test_experience)

    # 验证阈值检查逻辑正确
    # 1. get_entity_stats()被调用
    mock_experience_store.get_entity_stats.assert_called_once_with("张三")

    # 2. 满足阈值（count=5>=3, unique_days=4>=3），应该创建档案
    assert result is True

    # 3. profile_store.create()被调用
    mock_profile_store.create.assert_called_once()

    # Gap 3验证：方法逻辑存在且正确，但未被WriterPipeline调用
    print("✓ Gap 3验证通过：阈值逻辑存在且正确，但未被外部调用")


class TestProfileManagerThresholdLogic:
    """ProfileManager阈值逻辑的详细测试。

    验证check_and_create_profile()在不同场景下的行为。
    """

    @pytest.mark.skip(reason="Gap 3: 未调用 - 待13-02修复")
    def test_threshold_met_creates_profile(self, mock_profile_store, mock_experience_store, mock_entity_store):
        """验证满足阈值时创建档案。

        场景：实体出现5次，跨4天（满足count>=3且unique_days>=3）
        Expected: 创建档案
        """
        # 模拟张三出现5次，跨4天
        mock_experience_store.get_entity_stats.return_value = {
            "count": 5,
            "unique_days": 4,
        }
        mock_profile_store.get_by_name.return_value = None

        profile_manager = ProfileManager(
            profile_store=mock_profile_store,
            experience_store=mock_experience_store,
            entity_store=mock_entity_store,
        )

        test_experience = Experience(
            id="exp_20260331_120000",
            L0_text="和张三聊天",
            role="user",
            raw_content="和张三聊天",
            created_at="2026-03-31T12:00:00Z",
        )

        result = profile_manager.check_and_create_profile("张三", test_experience)

        assert result is True
        mock_profile_store.create.assert_called_once()

    @pytest.mark.skip(reason="Gap 3: 未调用 - 待13-02修复")
    def test_threshold_not_met_no_profile(self, mock_profile_store, mock_experience_store, mock_entity_store):
        """验证不满足阈值时不创建档案。

        场景：实体出现2次，跨2天（不满足count>=3且unique_days>=3）
        Expected: 不创建档案
        """
        # 模拟李四出现2次，跨2天
        mock_experience_store.get_entity_stats.return_value = {
            "count": 2,
            "unique_days": 2,
        }
        mock_profile_store.get_by_name.return_value = None

        profile_manager = ProfileManager(
            profile_store=mock_profile_store,
            experience_store=mock_experience_store,
            entity_store=mock_entity_store,
        )

        test_experience = Experience(
            id="exp_20260331_120000",
            L0_text="和李四聊天",
            role="user",
            raw_content="和李四聊天",
            created_at="2026-03-31T12:00:00Z",
        )

        result = profile_manager.check_and_create_profile("李四", test_experience)

        assert result is False
        mock_profile_store.create.assert_not_called()

    @pytest.mark.skip(reason="Gap 3: 未调用 - 待13-02修复")
    def test_profile_already_exists(self, mock_profile_store, mock_experience_store, mock_entity_store):
        """验证档案已存在时不重复创建。

        场景：档案已存在于ProfileStore
        Expected: 不创建新档案，返回False
        """
        # 模拟档案已存在
        mock_profile_store.get_by_name.return_value = Mock(
            id="profile_zhangsan",
            basic={"name": "张三"},
        )

        profile_manager = ProfileManager(
            profile_store=mock_profile_store,
            experience_store=mock_experience_store,
            entity_store=mock_entity_store,
        )

        test_experience = Experience(
            id="exp_20260331_120000",
            L0_text="和张三聊天",
            role="user",
            raw_content="和张三聊天",
            created_at="2026-03-31T12:00:00Z",
        )

        result = profile_manager.check_and_create_profile("张三", test_experience)

        assert result is False
        mock_profile_store.create.assert_not_called()
