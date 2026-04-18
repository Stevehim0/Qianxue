"""测试情感时间线Broken State（Phase 15：修复对emotion_target的依赖）。

验证当前实现的关键问题：
1. 情感时间线依赖emotion_target字段筛选
2. Phase 14.1设置emotion_target=None，导致功能失效
3. 应该从对话内容分析情感互动，不依赖emotion_target

所有测试标记为SKIPPED，因为功能尚未修复。
"""

import pytest
from Memory.consolidator.tasks.emotion_timeline_task import update_emotion_timeline
from Memory.storage.entity_store import entity_store, Entity
from Memory.storage.experience_store import experience_store, Experience
from Memory.storage.database import db_manager
from datetime import datetime


@pytest.fixture(scope="module")
def setup_database():
    """初始化测试数据库。"""
    if not db_manager.initialized:
        db_manager.initialize()
    yield
    # 清理测试数据


@pytest.fixture
def sample_person():
    """创建示例人实体（张三）。"""
    person = Entity(
        id="entity_zhang_san_001",
        name="张三",
        type="person",
        properties={},
        embedding=None,
        emotion_timeline=None,
        emotion_current=None,
        created_at=datetime.now().isoformat(),
    )
    entity_id = entity_store.create(person)
    return entity_store.get_by_id(entity_id)


@pytest.fixture
def sample_experiences_with_emotion():
    """创建示例体验（有情感但emotion_target=None）。

    Phase 14.1之后：所有experience的emotion_target都是None
    情感时间线任务会找不到任何记录
    """
    # Experience 1: 与张三对话，乐意帮助
    exp1 = Experience(
        id="exp_20260409_001",
        L3_raw="张三：你好\nAI：你好呀",
        L0_text="张三向我打招呼，我感到乐意帮助",
        L0_embedding=None,
        L1_summary=None,
        L2_insight=None,
        emotion_category="willing",
        emotion_intensity=0.6,
        emotion_valence=0.7,
        emotion_arousal=0.5,
        emotion_target=None,  # Phase 14.1: 设置为None
        context_focus=None,
        context_mood=None,
        context_time_of_day=None,
        importance=None,
        decay_factor=None,
        consolidated=False,
        distorted=None,
        created_at=datetime.now().isoformat(),
    )
    experience_store.create(exp1)

    # Experience 2: 与张三讨论Python，感到兴奋
    exp2 = Experience(
        id="exp_20260409_002",
        L3_raw="张三：我想学Python\nAI：好的",
        L0_text="张三想学Python，我感到兴奋",
        L0_embedding=None,
        L1_summary=None,
        L2_insight=None,
        emotion_category="excited",
        emotion_intensity=0.8,
        emotion_valence=0.9,
        emotion_arousal=0.7,
        emotion_target=None,  # Phase 14.1: 设置为None
        context_focus=None,
        context_mood=None,
        context_time_of_day=None,
        importance=None,
        decay_factor=None,
        consolidated=False,
        distorted=None,
        created_at=datetime.now().isoformat(),
    )
    experience_store.create(exp2)

    return [exp1.id, exp2.id]


@pytest.mark.skip(reason="ISSUE: 情感时间线依赖emotion_target字段，但Phase 14.1设置为None")
def test_emotion_timeline_should_not_depend_on_emotion_target(
    sample_person, sample_experiences_with_emotion, setup_database
):
    """测试：情感时间线应该从对话内容分析，不依赖emotion_target。

    当前行为（BROKEN）:
    ```python
    emotion_experiences = [
        exp for exp in experiences
        if exp.emotion_category and exp.emotion_target == person.name
    ]
    # 因为emotion_target=None，这个列表永远是空的
    ```

    期望行为（FIXED）:
    - 分析对话内容，识别对话对象（如"张三"）
    - 筛选与该对象相关的体验
    - 构建情感时间线
    """
    # Arrange
    person_id = sample_person.id
    experience_ids = sample_experiences_with_emotion

    # Act
    # result = update_emotion_timeline(
    #     experiences=[experience_store.get(eid) for eid in experience_ids],
    #     llm_client=mock_llm_client,
    #     entity_store=entity_store,
    #     experience_store=experience_store,
    # )

    # Assert (当前会fail)
    # 应该找到2个情感体验
    # emotion_timeline = entity_store.get_by_id(person_id).emotion_timeline
    # assert len(emotion_timeline) == 2
    # assert emotion_timeline[0]["emotion"] == "willing"
    # assert emotion_timeline[1]["emotion"] == "excited"
    pytest.skip("Broken: emotion_target=None导致筛选失败")


@pytest.mark.skip(reason="ISSUE: 需要从对话内容识别对话对象")
def test_emotion_timeline_should_extract_person_from_dialogue(
    sample_person, sample_experiences_with_emotion, setup_database
):
    """测试：情感时间线应该从对话内容识别对话对象。

    示例：
    - L3_raw: "张三：你好\nAI：你好呀"
    - 应该识别：对话对象是"张三"
    - 应该关联：这个体验的情感与"张三"实体相关
    """
    # 这个测试需要实现从对话识别对象的功能
    pytest.skip("Not implemented: 需要NLP识别对话对象")


@pytest.mark.skip(reason="ISSUE: 当前情感时间线功能完全失效")
def test_emotion_timeline_currently_broken(
    sample_person, sample_experiences_with_emotion, setup_database
):
    """测试：验证当前情感时间线功能确实broken。

    这个测试用于验证问题确实存在，作为修复前的baseline。
    """
    # Arrange
    person_id = sample_person.id
    person = entity_store.get_by_id(person_id)

    # Act & Assert
    # 当前emotion_timeline应该是空的
    assert person.emotion_timeline is None or len(person.emotion_timeline) == 0

    # 即使有与张三相关的情感体验，也无法关联
    experiences = experience_store.get_all()
    zhang_san_experiences = [
        exp for exp in experiences
        if exp.L3_raw and "张三" in exp.L3_raw  # 对话内容包含张三
    ]
    assert len(zhang_san_experiences) >= 2

    # 但emotion_target都是None，无法通过emotion_target筛选
    for exp in zhang_san_experiences:
        assert exp.emotion_target is None
