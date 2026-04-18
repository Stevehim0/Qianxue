"""梦境情感加工任务测试。"""

import pytest
import json
from unittest.mock import Mock, patch
from Memory.consolidator.tasks.dream_emotion_task import dream_emotion
from Memory.storage.experience_store import Experience


class TestDreamEmotionTask:
    """测试情感加工任务。"""

    def test_dream_emotion_updates_emotion_snapshot(self, db_manager):
        """测试dream_emotion更新emotion_snapshot字段。"""
        # Arrange
        memories = [
            Experience(
                id="exp_000001",
                L3_raw="Test memory",
                L0_text="I felt happy",
                L1_text="Great experience",
                emotion_category="neutral",
                emotion_intensity=0.5,
            )
        ]

        mock_llm = Mock()
        mock_llm.call_json.return_value = {
            "emotion_category": "joy",
            "emotion_intensity": 0.9,
            "valence": 0.8,
            "arousal": 0.7,
            "target": None,
        }

        experience_store = Mock()
        experience_store.update.return_value = True

        # Act
        result = dream_emotion(memories, mock_llm, experience_store)

        # Assert: Should update emotion
        assert result["updated_count"] > 0
        assert experience_store.update.called

        # Verify the update call included emotion data
        call_args = experience_store.update.call_args
        assert "emotion_snapshot" in call_args[1]

    def test_dream_emotion_returns_statistics(self, db_manager):
        """测试dream_emotion返回统计信息。"""
        # Arrange
        memories = [
            Experience(
                id="exp_000001",
                L3_raw="Test",
                L0_text="Memory",
                L1_text="Detail",
                emotion_category="neutral",
                emotion_intensity=0.5,
            )
        ]

        mock_llm = Mock()
        mock_llm.call_json.return_value = {
            "emotion_category": "joy",
            "emotion_intensity": 0.8,
            "valence": 0.7,
            "arousal": 0.6,
            "target": None,
        }

        experience_store = Mock()
        experience_store.update.return_value = True

        # Act
        result = dream_emotion(memories, mock_llm, experience_store)

        # Assert: Should return statistics
        assert "processed_count" in result
        assert "updated_count" in result
        assert "failed_count" in result
        assert "duration_seconds" in result

    def test_dream_emotion_uses_dream_system_prompt(self, db_manager):
        """测试dream_emotion使用dream_system.txt作为system prompt。"""
        # Arrange
        memories = [
            Experience(
                id="exp_000001",
                L3_raw="Test",
                L0_text="Memory",
                L1_text="Detail",
                emotion_category="neutral",
                emotion_intensity=0.5,
            )
        ]

        mock_llm = Mock()
        mock_llm.call_json.return_value = {
            "emotion_category": "joy",
            "emotion_intensity": 0.8,
            "valence": 0.7,
            "arousal": 0.6,
            "target": None,
        }

        experience_store = Mock()

        # Act
        with patch("builtins.open", create=True) as mock_open:
            mock_open.return_value.__enter__.return_value.read.return_value = "dream system prompt"
            dream_emotion(memories, mock_llm, experience_store)

            # Assert: LLM should be called with system prompt
            assert mock_llm.call_json.called
            call_kwargs = mock_llm.call_json.call_args[1]
            assert "system_prompt" in call_kwargs

    def test_single_memory_failure_doesnt_stop_batch(self, db_manager):
        """测试单个记忆失败不阻止批量处理。"""
        # Arrange
        memories = [
            Experience(
                id="exp_000001",
                L3_raw="Test 1",
                L0_text="Memory 1",
                L1_text="Detail 1",
                emotion_category="neutral",
                emotion_intensity=0.5,
            ),
            Experience(
                id="exp_000002",
                L3_raw="Test 2",
                L0_text="Memory 2",
                L1_text="Detail 2",
                emotion_category="neutral",
                emotion_intensity=0.5,
            ),
        ]

        mock_llm = Mock()
        # First call succeeds, second fails
        mock_llm.call_json.side_effect = [
            {
                "emotion_category": "joy",
                "emotion_intensity": 0.8,
                "valence": 0.7,
                "arousal": 0.6,
                "target": None,
            },
            Exception("LLM error"),
        ]

        experience_store = Mock()
        experience_store.update.return_value = True

        # Act
        result = dream_emotion(memories, mock_llm, experience_store)

        # Assert: Should process both memories despite failure
        assert result["processed_count"] == 2
        assert result["failed_count"] > 0

    def test_returns_dict_with_duration_seconds(self, db_manager):
        """测试返回的字典包含duration_seconds字段。"""
        # Arrange
        memories = [
            Experience(
                id="exp_000001",
                L3_raw="Test",
                L0_text="Memory",
                L1_text="Detail",
                emotion_category="neutral",
                emotion_intensity=0.5,
            )
        ]

        mock_llm = Mock()
        mock_llm.call_json.return_value = {
            "emotion_category": "joy",
            "emotion_intensity": 0.8,
            "valence": 0.7,
            "arousal": 0.6,
            "target": None,
        }

        experience_store = Mock()
        experience_store.update.return_value = True

        # Act
        result = dream_emotion(memories, mock_llm, experience_store)

        # Assert: Should include duration
        assert "duration_seconds" in result
        assert result["duration_seconds"] >= 0
