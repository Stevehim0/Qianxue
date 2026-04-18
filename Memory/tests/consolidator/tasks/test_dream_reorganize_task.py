"""梦境重组任务测试。"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from Memory.consolidator.tasks.dream_reorganize_task import dream_reorganize
from Memory.storage.experience_store import Experience
from Memory.storage.experience_edge_store import ExperienceEdgeStore
from datetime import datetime


class TestDreamReorganizeTask:
    """测试记忆重组任务。"""

    def test_dream_reorganize_creates_new_edges(self, db_manager):
        """测试dream_reorganize创建新的关系边。"""
        # Arrange: Create test memories
        memories = [
            Experience(
                id="exp_000001",
                L3_raw="Test memory 1",
                L0_text="Memory about coding",
                L1_text="I wrote Python code",
                importance=0.8,
            ),
            Experience(
                id="exp_000002",
                L3_raw="Test memory 2",
                L0_text="Memory about learning",
                L1_text="I learned about algorithms",
                importance=0.7,
            ),
        ]

        mock_llm = Mock()
        mock_llm.call_json.return_value = {
            "has_relationship": True,
            "relationship_type": "analogy",
            "confidence": 0.8,
            "explanation": "Both involve problem-solving",
        }

        experience_store = Mock()
        edge_store = Mock(spec=ExperienceEdgeStore)
        edge_store.create.return_value = True

        # Act
        result = dream_reorganize(memories, mock_llm, experience_store, edge_store)

        # Assert: Should create edges
        assert result["created_edges"] > 0, "Should have created at least one edge"
        assert edge_store.create.called, "edge_store.create should be called"

    def test_dream_reorganize_returns_statistics(self, db_manager):
        """测试dream_reorganize返回统计信息。"""
        # Arrange
        memories = [
            Experience(
                id="exp_000001",
                L3_raw="Test",
                L0_text="Memory 1",
                L1_text="Detail 1",
                importance=0.5,
            )
        ]

        mock_llm = Mock()
        mock_llm.call_json.return_value = {"has_relationship": False}

        experience_store = Mock()
        edge_store = Mock()

        # Act
        result = dream_reorganize(memories, mock_llm, experience_store, edge_store)

        # Assert: Should return statistics
        assert "processed_count" in result
        assert "created_edges" in result
        assert "failed_count" in result
        assert "duration_seconds" in result

    def test_dream_reorganize_uses_dream_system_prompt(self, db_manager):
        """测试dream_reorganize使用dream_system.txt作为system prompt。"""
        # Arrange
        memories = [
            Experience(
                id="exp_000001", L3_raw="Test", L0_text="Memory", L1_text="Detail", importance=0.5
            )
        ]

        mock_llm = Mock()
        mock_llm.call_json.return_value = {"has_relationship": False}

        experience_store = Mock()
        edge_store = Mock()

        # Act
        with patch("builtins.open", create=True) as mock_open:
            mock_open.return_value.__enter__.return_value.read.return_value = "dream system prompt"
            dream_reorganize(memories, mock_llm, experience_store, edge_store)

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
                importance=0.5,
            ),
            Experience(
                id="exp_000002",
                L3_raw="Test 2",
                L0_text="Memory 2",
                L1_text="Detail 2",
                importance=0.5,
            ),
        ]

        mock_llm = Mock()
        # First call succeeds, second fails
        mock_llm.call_json.side_effect = [{"has_relationship": False}, Exception("LLM error")]

        experience_store = Mock()
        edge_store = Mock()

        # Act
        result = dream_reorganize(memories, mock_llm, experience_store, edge_store)

        # Assert: Should process both memories despite failure
        assert result["processed_count"] == 2
        assert result["failed_count"] > 0

    def test_returns_dict_with_duration_seconds(self, db_manager):
        """测试返回的字典包含duration_seconds字段。"""
        # Arrange
        memories = [
            Experience(
                id="exp_000001", L3_raw="Test", L0_text="Memory", L1_text="Detail", importance=0.5
            )
        ]

        mock_llm = Mock()
        mock_llm.call_json.return_value = {"has_relationship": False}

        experience_store = Mock()
        edge_store = Mock()

        # Act
        result = dream_reorganize(memories, mock_llm, experience_store, edge_store)

        # Assert: Should include duration
        assert "duration_seconds" in result
        assert result["duration_seconds"] >= 0
