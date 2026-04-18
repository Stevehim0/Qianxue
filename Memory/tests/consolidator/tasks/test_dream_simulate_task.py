"""梦境模拟推演任务测试。"""

import pytest
from unittest.mock import Mock, patch
from Memory.consolidator.tasks.dream_simulate_task import dream_simulate
from Memory.storage.experience_store import Experience


class TestDreamSimulateTask:
    """测试模拟推演任务。"""

    def test_dream_simulate_creates_new_experience_nodes(self, db_manager):
        """测试dream_simulate创建新的体验节点。"""
        # Arrange
        memories = [
            Experience(
                id="exp_000001",
                L3_raw="Original memory",
                L0_text="I went to the park",
                L1_text="Walked and enjoyed nature",
                importance=0.8,
            )
        ]

        mock_llm = Mock()
        mock_llm.call_json.return_value = {
            "simulated_L0": "I explored a fantasy world",
            "simulated_L1": "Flying through magical landscapes",
            "simulated_L2": "Freedom and wonder",
        }

        experience_store = Mock()
        experience_store.create.return_value = "dream_20260402_120000"

        # Act
        result = dream_simulate(memories, mock_llm, experience_store)

        # Assert: Should create new nodes
        assert result["created_count"] > 0
        assert experience_store.create.called

    def test_dream_simulate_marks_nodes_with_dream_markers(self, db_manager):
        """测试dream_simulate标记节点为source_type=dream, confidence=0.3。"""
        # Arrange
        memories = [
            Experience(
                id="exp_000001",
                L3_raw="Original",
                L0_text="Memory",
                L1_text="Detail",
                importance=0.7,
            )
        ]

        mock_llm = Mock()
        mock_llm.call_json.return_value = {
            "simulated_L0": "Simulated",
            "simulated_L1": "Simulated detail",
            "simulated_L2": "Simulated meaning",
        }

        experience_store = Mock()
        experience_store.create.return_value = "dream_test"

        # Act
        dream_simulate(memories, mock_llm, experience_store)

        # Assert: Should create node with dream markers (D-09)
        call_args = experience_store.create.call_args
        assert call_args[1]["source_type"] == "dream"
        assert call_args[1]["confidence"] == 0.3

    def test_dream_simulate_applies_importance_multiplier(self, db_manager):
        """测试dream_simulate应用importance×0.5乘数（D-09）。"""
        # Arrange
        memories = [
            Experience(
                id="exp_000001",
                L3_raw="Original",
                L0_text="Memory",
                importance=0.8,  # High importance
            )
        ]

        mock_llm = Mock()
        mock_llm.call_json.return_value = {
            "simulated_L0": "Simulated",
            "simulated_L1": "Detail",
            "simulated_L2": "Meaning",
        }

        experience_store = Mock()
        experience_store.create.return_value = "dream_test"

        # Act
        dream_simulate(memories, mock_llm, experience_store)

        # Assert: Should apply 0.5 multiplier to importance
        call_args = experience_store.create.call_args
        expected_importance = 0.8 * 0.5  # D-09
        assert call_args[1]["importance"] == expected_importance

    def test_dream_simulate_adds_dream_prefix_to_L3(self, db_manager):
        """测试dream_simulate在L3字段添加'[梦境推演]'前缀（D-11）。"""
        # Arrange
        memories = [
            Experience(
                id="exp_000001",
                L3_raw="Original memory content",
                L0_text="Original L0",
                importance=0.6,
            )
        ]

        mock_llm = Mock()
        mock_llm.call_json.return_value = {
            "simulated_L0": "Simulated scenario",
            "simulated_L1": "Simulated detail",
            "simulated_L2": "Simulated meaning",
        }

        experience_store = Mock()
        experience_store.create.return_value = "dream_test"

        # Act
        dream_simulate(memories, mock_llm, experience_store)

        # Assert: L3 should contain '[梦境推演]' prefix (D-11)
        call_args = experience_store.create.call_args
        l3_content = call_args[1]["L3_raw"]
        assert "[梦境推演]" in l3_content

    def test_error_handling_works(self, db_manager):
        """测试错误处理（D-13, D-14）。"""
        # Arrange
        memories = [
            Experience(id="exp_000001", L3_raw="Test 1", L0_text="Memory 1", importance=0.5),
            Experience(id="exp_000002", L3_raw="Test 2", L0_text="Memory 2", importance=0.5),
        ]

        mock_llm = Mock()
        # First call succeeds, second fails
        mock_llm.call_json.side_effect = [
            {"simulated_L0": "Sim 1", "simulated_L1": "Detail 1", "simulated_L2": "Meaning 1"},
            Exception("LLM error"),
        ]

        experience_store = Mock()
        experience_store.create.return_value = "dream_test"

        # Act
        result = dream_simulate(memories, mock_llm, experience_store)

        # Assert: Should process both despite failure
        assert result["processed_count"] == 2
        assert result["failed_count"] > 0
