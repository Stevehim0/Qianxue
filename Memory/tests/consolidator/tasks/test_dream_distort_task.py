"""梦境扭曲任务测试。"""

import pytest
import json
from unittest.mock import Mock, patch
from Memory.consolidator.tasks.dream_distort_task import dream_distort
from Memory.storage.experience_store import Experience
from datetime import datetime, timedelta


class TestDreamDistortTask:
    """测试记忆扭曲任务。"""

    def test_dream_distort_updates_L0_L1_L2_and_distorted_field(self, db_manager):
        """测试dream_distort更新L0/L1/L2和distorted字段。"""
        # Arrange
        memories = [
            Experience(
                id="exp_000001",
                L3_raw="Original memory that cannot be changed",
                L0_text="Original L0",
                L1_text="Original L1",
                L2_text="Original L2",
                importance=0.8,
                created_at=(datetime.now() - timedelta(days=30)).isoformat(),
            )
        ]

        mock_llm = Mock()
        mock_llm.call_json.return_value = {
            "L0_text": "Distorted L0",
            "L1_text": "Distorted L1",
            "L2_text": "Distorted L2",
        }

        experience_store = Mock()
        experience_store.update_distorted.return_value = True

        # Act
        result = dream_distort(memories, mock_llm, experience_store)

        # Assert: Should call update_distorted
        assert experience_store.update_distorted.called
        call_args = experience_store.update_distorted.call_args
        assert call_args[1]["L0_text"] == "Distorted L0"
        assert call_args[1]["L1_text"] == "Distorted L1"
        assert call_args[1]["L2_text"] == "Distorted L2"
        assert "distorted" in call_args[1]

    def test_dream_distort_never_modifies_L3(self, db_manager):
        """测试dream_distort从不修改L3_raw（由update_distorted强制执行）。"""
        # Arrange
        memories = [
            Experience(
                id="exp_000001",
                L3_raw="Original L3 that must never change",
                L0_text="Original L0",
                importance=0.5,
            )
        ]

        mock_llm = Mock()
        mock_llm.call_json.return_value = {
            "L0_text": "New L0",
            "L1_text": "New L1",
            "L2_text": "New L2",
        }

        experience_store = Mock()
        experience_store.update_distorted.return_value = True

        # Act
        dream_distort(memories, mock_llm, experience_store)

        # Assert: update_distorted should be called (which enforces L3 immutability)
        assert experience_store.update_distorted.called
        # L3 should never be passed to update_distorted
        call_args = experience_store.update_distorted.call_args
        assert "L3_raw" not in call_args[1]

    def test_dream_distort_contains_original_and_distorted_values(self, db_manager):
        """测试distorted JSON包含original_values和distorted_values。"""
        # Arrange
        memories = [
            Experience(
                id="exp_000001",
                L3_raw="Original L3",
                L0_text="Original L0",
                L1_text="Original L1",
                L2_text="Original L2",
                importance=0.7,
                created_at=(datetime.now() - timedelta(days=20)).isoformat(),
            )
        ]

        mock_llm = Mock()
        mock_llm.call_json.return_value = {
            "L0_text": "Distorted L0",
            "L1_text": "Distorted L1",
            "L2_text": "Distorted L2",
        }

        experience_store = Mock()
        experience_store.update_distorted.return_value = True

        # Act
        dream_distort(memories, mock_llm, experience_store)

        # Assert: distorted JSON should contain both original and distorted values
        call_args = experience_store.update_distorted.call_args
        distorted_json = call_args[1]["distorted"]
        distorted_data = json.loads(distorted_json)

        assert "original_values" in distorted_data
        assert "distorted_values" in distorted_data
        assert distorted_data["original_values"]["L0_text"] == "Original L0"
        assert distorted_data["distorted_values"]["L0_text"] == "Distorted L0"

    def test_dream_distort_returns_statistics(self, db_manager):
        """测试dream_distort返回统计信息。"""
        # Arrange
        memories = [Experience(id="exp_000001", L3_raw="Test", L0_text="Original", importance=0.5)]

        mock_llm = Mock()
        mock_llm.call_json.return_value = {
            "L0_text": "New L0",
            "L1_text": "New L1",
            "L2_text": "New L2",
        }

        experience_store = Mock()
        experience_store.update_distorted.return_value = True

        # Act
        result = dream_distort(memories, mock_llm, experience_store)

        # Assert: Should return statistics
        assert "processed_count" in result
        assert "distorted_count" in result
        assert "failed_count" in result
        assert "duration_seconds" in result

    def test_error_handling_works(self, db_manager):
        """测试错误处理（D-13, D-14）。"""
        # Arrange
        memories = [
            Experience(id="exp_000001", L3_raw="Test 1", L0_text="Original 1", importance=0.5),
            Experience(id="exp_000002", L3_raw="Test 2", L0_text="Original 2", importance=0.5),
        ]

        mock_llm = Mock()
        # First call succeeds, second fails
        mock_llm.call_json.side_effect = [
            {"L0_text": "New L0", "L1_text": "New L1", "L2_text": "New L2"},
            Exception("LLM error"),
        ]

        experience_store = Mock()
        experience_store.update_distorted.return_value = True

        # Act
        result = dream_distort(memories, mock_llm, experience_store)

        # Assert: Should process both despite failure
        assert result["processed_count"] == 2
        assert result["failed_count"] > 0
