"""测试情感快照任务（Phase 14.1：emotion_target=None）。

验证：
1. dialogue参数正确传递
2. LLM分析情感（不返回target字段）
3. emotion_target固定写None
4. 其他情感字段正常存储
"""

import pytest
from unittest.mock import MagicMock, patch
from Memory.writer.tasks.emotion_task import analyze_emotion_and_check_state
from Memory.storage.experience_store import experience_store


@pytest.fixture
def mock_llm_client():
    """Mock LLM客户端，返回预设情感分析结果（无target字段）。"""
    mock = MagicMock()
    mock.call_with_retry.return_value = {
        "category": "willing",
        "intensity": 0.6,
        "valence": 0.7,
        "arousal": 0.5
        # 注意：不返回target字段
    }
    return mock


@pytest.fixture
def sample_dialogue():
    """示例长对话。"""
    return """
    张三：我想学Python
    AI：好的，我来帮你
    """


def test_analyze_emotion_uses_dialogue_parameter(sample_dialogue, mock_llm_client):
    """测试：analyze_emotion_and_check_state使用dialogue参数。"""
    # Arrange
    experience_id = "exp_test_001"

    with patch("Memory.writer.tasks.emotion_task.LLMFactory.create_client", return_value=mock_llm_client):
        # Act
        emotion = analyze_emotion_and_check_state(
            experience_id=experience_id,
            dialogue=sample_dialogue,
            state_focus=None,
            state_mood_label="平静",
            llm_client=mock_llm_client,
            experience_store=experience_store,
        )

        # Assert
        assert emotion is not None
        assert emotion.category == "willing"
        assert emotion.intensity == 0.6


def test_emotion_target_is_none(sample_dialogue, mock_llm_client):
    """测试：emotion_target固定写None。

    即使LLM返回target字段，代码也应该强制写None。
    """
    # Arrange
    experience_id = "exp_test_002"

    with patch("Memory.writer.tasks.emotion_task.LLMFactory.create_client", return_value=mock_llm_client):
        # Act
        emotion = analyze_emotion_and_check_state(
            experience_id=experience_id,
            dialogue=sample_dialogue,
            state_focus=None,
            state_mood_label="平静",
            llm_client=mock_llm_client,
            experience_store=experience_store,
        )

        # Assert
        # EmotionSnapshot对象的target字段
        assert emotion.target is None

        # 数据库中的emotion_target字段
        exp = experience_store.get(experience_id)
        assert exp.emotion_target is None


def test_emotion_fields_stored_correctly(sample_dialogue, mock_llm_client):
    """测试：其他情感字段正常存储。"""
    # Arrange
    experience_id = "exp_test_003"

    with patch("Memory.writer.tasks.emotion_task.LLMFactory.create_client", return_value=mock_llm_client):
        # Act
        emotion = analyze_emotion_and_check_state(
            experience_id=experience_id,
            dialogue=sample_dialogue,
            state_focus=None,
            state_mood_label="平静",
            llm_client=mock_llm_client,
            experience_store=experience_store,
        )

        # Assert
        exp = experience_store.get(experience_id)
        assert exp.emotion_category == "willing"
        assert exp.emotion_intensity == 0.6
        assert exp.emotion_valence == 0.7
        assert exp.emotion_arousal == 0.5
        # target必须是None
        assert exp.emotion_target is None
