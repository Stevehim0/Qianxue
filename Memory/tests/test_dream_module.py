"""
梦境模块端到端集成测试

Tests the complete dream module flow:
1. Sampling (40% important + 60% random)
2. Four parallel dream tasks
3. Pipeline integration
4. CLI execution
5. Audit logging

Wave 0: Test stubs created in Plan 01.
Wave 4: Tests implemented in Plan 04.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from typing import List
from pathlib import Path
import json

from Memory.consolidator.pipeline import ConsolidationPipeline
from Memory.consolidator.tasks import dream_reorganize, dream_emotion, dream_distort, dream_simulate
from Memory.consolidator.sampling import select_memories_for_dream
from Memory.storage.experience_store import ExperienceStore, Experience
from Memory.storage.experience_edge_store import ExperienceEdgeStore
from Memory.llm.base import BaseLLMClient


# Test 1: Layered sampling strategy
def test_layered_sampling_40_60_split(dream_memories_sample, experience_store):
    """验证分层采样：40%重要 + 60%随机"""
    # Setup: Insert test memories into database
    for memory in dream_memories_sample:
        experience_store.create(
            experience_id=memory.id,
            L3_raw=memory.L3_raw,
            L0_text=memory.L0_text,
            L1_text=memory.L1_text,
            L2_text=memory.L2_text,
            importance=memory.importance,
            emotion_intensity=memory.emotion_intensity,
            created_at=memory.created_at,
        )

    # Execute: Select 10 memories (4 important + 6 random)
    selected = select_memories_for_dream(experience_store, total_count=10)

    # Verify: Total count
    assert len(selected) == 10, "Should select exactly 10 memories"

    # Verify: 4 most important (40%)
    important_selected = [m for m in selected if m.importance >= 0.7]
    assert (
        len(important_selected) == 4
    ), f"Should have 4 important memories, got {len(important_selected)}"

    # Verify: No overlap between important and random
    selected_ids = [m.id for m in selected]
    assert len(selected_ids) == len(set(selected_ids)), "No duplicate IDs allowed"


# Test 2: Dream reorganize task
@patch("Memory.consolidator.tasks.dream_reorganize_task.BaseLLMClient")
def test_dream_reorganize_creates_edges(mock_llm_client, dream_memories_sample):
    """验证记忆重组任务创建关系边（不创建节点）"""
    # Setup: Mock LLM response
    mock_llm_instance = Mock()
    mock_llm_instance.call_json.return_value = {
        "has_relationship": True,
        "relationship_type": "thematic",
        "confidence": 0.7,
        "explanation": "Test relationship",
    }
    mock_llm_client.return_value = mock_llm_instance

    # Setup: Mock stores
    mock_exp_store = Mock()
    mock_edge_store = Mock()
    mock_edge_store.create.return_value = True

    # Execute: Run dream reorganize
    result = dream_reorganize(
        memories=dream_memories_sample[:5],
        llm_client=mock_llm_instance,
        experience_store=mock_exp_store,
        edge_store=mock_edge_store,
    )

    # Verify: Edges created
    assert result["created_edges"] > 0, "Should create at least one edge"
    assert mock_edge_store.create.call_count > 0, "edge_store.create() should be called"

    # Verify: No new nodes created (D-10)
    assert mock_exp_store.create.call_count == 0, "Should NOT create new nodes"

    # Verify: Return format
    assert "processed_count" in result
    assert "created_edges" in result
    assert "failed_count" in result
    assert "duration_seconds" in result


# Test 3: Dream emotion task
@patch("Memory.consolidator.tasks.dream_emotion_task.BaseLLMClient")
def test_dream_emotion_updates_emotion_snapshot(mock_llm_client, dream_memories_sample):
    """验证情感加工任务更新情感快照"""
    # Setup: Mock LLM response
    mock_llm_instance = Mock()
    mock_llm_instance.call_json.return_value = {
        "emotion_category": "calm",
        "emotion_intensity": 0.4,
        "valence": 0.2,
        "arousal": 0.3,
        "target": None,
    }
    mock_llm_client.return_value = mock_llm_instance

    # Setup: Mock store
    mock_exp_store = Mock()
    mock_exp_store.update.return_value = True

    # Execute: Run dream emotion
    result = dream_emotion(
        memories=dream_memories_sample[:5],
        llm_client=mock_llm_instance,
        experience_store=mock_exp_store,
    )

    # Verify: Emotion snapshots updated
    assert result["updated_count"] == 5, "Should update all 5 memories"
    assert mock_exp_store.update.call_count == 5, "update() called 5 times"

    # Verify: Return format
    assert "processed_count" in result
    assert "updated_count" in result
    assert "failed_count" in result


# Test 4: Dream distort task
@patch("Memory.consolidator.tasks.dream_distort_task.BaseLLMClient")
def test_dream_distort_never_modifies_L3(mock_llm_client, dream_memories_sample):
    """验证记忆扭曲任务永不修改L3（铁律）"""
    # Setup: Mock LLM response
    mock_llm_instance = Mock()
    mock_llm_instance.call_json.return_value = {
        "L0_text": "Distorted L0",
        "L1_text": "Distorted L1",
        "L2_text": "Distorted L2",
    }
    mock_llm_client.return_value = mock_llm_instance

    # Setup: Mock store
    mock_exp_store = Mock()
    mock_exp_store.update_distorted.return_value = True

    # Execute: Run dream distort
    result = dream_distort(
        memories=dream_memories_sample[:5],
        llm_client=mock_llm_instance,
        experience_store=mock_exp_store,
    )

    # Verify: update_distorted called (not update)
    assert mock_exp_store.update_distorted.call_count == 5, "Should call update_distorted()"
    assert mock_exp_store.update.call_count == 0, "Should NOT call update() for L3 modification"

    # Verify: Distorted JSON includes original and distorted values
    for call in mock_exp_store.update_distorted.call_args_list:
        kwargs = call[1]  # Get keyword arguments
        assert "distorted" in kwargs, "Should include distorted JSON"
        distorted_data = json.loads(kwargs["distorted"])
        assert "original_values" in distorted_data
        assert "distorted_values" in distorted_data
        # L3 not in either (D-15)
        assert "L3_raw" not in distorted_data["original_values"]
        assert "L3_raw" not in distorted_data["distorted_values"]


# Test 5: Dream simulate task
@patch("Memory.consolidator.tasks.dream_simulate_task.BaseLLMClient")
def test_dream_simulate_creates_dream_nodes(mock_llm_client, dream_memories_sample):
    """验证模拟推演任务创建梦境节点"""
    # Setup: Mock LLM response
    mock_llm_instance = Mock()
    mock_llm_instance.call_json.return_value = {
        "simulated_L0": "Simulated scenario",
        "simulated_L1": "Simulated details",
        "simulated_L2": "Simulated meaning",
    }
    mock_llm_client.return_value = mock_llm_instance

    # Setup: Mock store
    mock_exp_store = Mock()
    mock_exp_store.create.return_value = True

    # Execute: Run dream simulate
    result = dream_simulate(
        memories=dream_memories_sample[:5],
        llm_client=mock_llm_instance,
        experience_store=mock_exp_store,
    )

    # Verify: Dream nodes created
    assert result["created_count"] == 5, "Should create 5 dream nodes"
    assert mock_exp_store.create.call_count == 5, "create() called 5 times"

    # Verify: Dream node markers (D-09)
    for call in mock_exp_store.create.call_args_list:
        kwargs = call[1]
        assert kwargs["source_type"] == "dream", "Should mark source_type='dream'"
        assert kwargs["confidence"] == 0.3, "Should set confidence=0.3"
        assert kwargs["importance"] < 1.0, "Should reduce importance"
        assert "[梦境推演]" in kwargs["L3_raw"], "Should add prefix to L3"


# Test 6: Pipeline integration - dream module only in full mode
@patch("Memory.consolidator.pipeline.ThreadPoolExecutor")
def test_dream_module_only_in_full_consolidation(mock_executor):
    """验证梦境模块仅在全量巩固时执行（D-01, D-17）"""
    # Setup: Mock pipeline components
    mock_pipeline = Mock(spec=ConsolidationPipeline)
    mock_pipeline._run_phase1_tasks.return_value = {"phase1": "done"}
    mock_pipeline._run_decay_calculation.return_value = {"phase2": "done"}

    # Execute: Incremental mode (should skip dream module)
    with (
        patch.object(ConsolidationPipeline, "_run_phase1_tasks", mock_pipeline._run_phase1_tasks),
        patch.object(
            ConsolidationPipeline, "_run_decay_calculation", mock_pipeline._run_decay_calculation
        ),
    ):
        pipeline = ConsolidationPipeline()
        results = pipeline.run_consolidation(mode="incremental")

    # Verify: Dream module skipped
    assert "phase3" in results
    assert results["phase3"]["status"] == "skipped"
    assert results["phase3"]["reason"] == "incremental mode"


# Test 7: Pipeline integration - four tasks parallel execution
@patch("Memory.consolidator.pipeline.ThreadPoolExecutor")
@patch("Memory.consolidator.sampling.select_memories_for_dream")
def test_dream_four_tasks_parallel_execution(mock_sampling, mock_executor):
    """验证四个梦境任务并行执行（D-06）"""
    # Setup: Mock sampling to return test memories
    mock_sampling.return_value = [Mock(id=f"test_{i}") for i in range(5)]

    # Setup: Mock ThreadPoolExecutor
    mock_future = Mock()
    mock_future.result.return_value = {"processed_count": 5, "duration_seconds": 10.0}
    mock_executor.return_value.__enter__.return_value.submit.return_value = mock_future

    # Execute: Run dream module
    pipeline = ConsolidationPipeline()
    results = pipeline._run_dream_module()

    # Verify: All four tasks submitted
    assert (
        mock_executor.return_value.__enter__.return_value.submit.call_count == 4
    ), "Should submit 4 tasks to executor"

    # Verify: Results include all four tasks
    assert "reorganize" in results
    assert "emotion" in results
    assert "distort" in results
    assert "simulate" in results


# Test 8: Dream module timeout handling
@patch("Memory.consolidator.pipeline.ThreadPoolExecutor")
@patch("Memory.consolidator.sampling.select_memories_for_dream")
def test_dream_timeout_handling(mock_sampling, mock_executor):
    """验证任务超时处理（D-08, D-14）"""
    # Setup: Mock sampling
    mock_sampling.return_value = [Mock(id=f"test_{i}") for i in range(5)]

    # Setup: Mock timeout (future.result() raises TimeoutError)
    mock_future = Mock()
    from concurrent.futures import TimeoutError

    mock_future.result.side_effect = TimeoutError("Task timed out")
    mock_executor.return_value.__enter__.return_value.submit.return_value = mock_future

    # Execute: Run dream module
    pipeline = ConsolidationPipeline()
    results = pipeline._run_dream_module()

    # Verify: Timeout handled gracefully
    for task_name in ["reorganize", "emotion", "distort", "simulate"]:
        assert task_name in results
        assert results[task_name]["status"] == "timeout"
        assert results[task_name]["processed_count"] == 0


# Test 9: Error handling - single task failure doesn't stop others
@patch("Memory.consolidator.pipeline.ThreadPoolExecutor")
@patch("Memory.consolidator.sampling.select_memories_for_dream")
def test_single_task_failure_doesnt_stop_others(mock_sampling, mock_executor):
    """验证单个任务失败不影响其他任务（D-13）"""
    # Setup: Mock sampling
    mock_sampling.return_value = [Mock(id=f"test_{i}") for i in range(5)]

    # Setup: Mock mixed results (2 succeed, 2 fail)
    def create_mock_result(success):
        mock_f = Mock()
        if success:
            mock_f.result.return_value = {"processed_count": 5}
        else:
            mock_f.result.side_effect = Exception("Task failed")
        return mock_f

    mock_executor.return_value.__enter__.return_value.submit.side_effect = [
        create_mock_result(True),  # reorganize succeeds
        create_mock_result(False),  # emotion fails
        create_mock_result(True),  # distort succeeds
        create_mock_result(False),  # simulate fails
    ]

    # Execute: Run dream module
    pipeline = ConsolidationPipeline()
    results = pipeline._run_dream_module()

    # Verify: 2 succeed, 2 fail
    assert results["reorganize"]["processed_count"] == 5
    assert results["emotion"]["status"] == "failed"
    assert results["distort"]["processed_count"] == 5
    assert results["simulate"]["status"] == "failed"


# Test 10: Audit logging verification
@patch("Memory.consolidator.pipeline.ThreadPoolExecutor")
@patch("Memory.consolidator.sampling.select_memories_for_dream")
@patch("Memory.consolidator.tasks.dream_reorganize_task.logger")
def test_audit_logging(mock_logger, mock_sampling, mock_executor):
    """验证审计日志记录（D-20）"""
    # Setup: Mock successful execution
    mock_sampling.return_value = [Mock(id=f"test_{i}") for i in range(5)]
    mock_future = Mock()
    mock_future.result.return_value = {
        "processed_count": 5,
        "created_edges": 3,
        "duration_seconds": 10.0,
    }
    mock_executor.return_value.__enter__.return_value.submit.return_value = mock_future

    # Execute: Run dream module
    pipeline = ConsolidationPipeline()
    results = pipeline._run_dream_module()

    # Verify: Logging called
    assert mock_logger.info.call_count > 0, "Should log info messages"

    # Verify: Key log messages present
    log_messages = [call[0][0] for call in mock_logger.info.call_args_list]
    assert any("Dream" in msg for msg in log_messages)


# Test 11: Full consolidation flow with dream module
@patch("Memory.consolidator.pipeline.ThreadPoolExecutor")
@patch("Memory.consolidator.sampling.select_memories_for_dream")
def test_full_consolidation_with_dream_module(mock_sampling, mock_executor, tmp_path):
    """验证完整巩固流程包含梦境模块"""
    # Setup: Mock all components
    mock_sampling.return_value = [Mock(id=f"test_{i}") for i in range(5)]
    mock_future = Mock()
    mock_future.result.return_value = {"processed_count": 5, "duration_seconds": 10.0}
    mock_executor.return_value.__enter__.return_value.submit.return_value = mock_future

    # Execute: Full consolidation
    pipeline = ConsolidationPipeline()
    results = pipeline.run_consolidation(mode="full")

    # Verify: All three phases present
    assert "phase1" in results
    assert "phase2" in results
    assert "phase3" in results

    # Verify: Phase 3 (dream module) executed
    assert results["phase3"]["status"] != "skipped"
    assert "reorganize" in results["phase3"]
    assert "emotion" in results["phase3"]
    assert "distort" in results["phase3"]
    assert "simulate" in results["phase3"]


# Test 12: Dream requirements verification
def test_dream_requirements_coverage():
    """验证所有DREAM-01到DREAM-04需求已覆盖"""
    # DREAM-01: 专门的system prompt
    dream_system_path = Path(__file__).parent.parent / "config" / "prompts" / "dream_system.txt"
    assert dream_system_path.exists(), f"dream_system.txt should exist at {dream_system_path}"
    content = dream_system_path.read_text(encoding="utf-8")
    assert "梦境" in content or "dream" in content.lower(), "Should use dream persona"

    # DREAM-02: 四项任务并行
    from Memory.consolidator.pipeline import ConsolidationPipeline

    assert hasattr(
        ConsolidationPipeline, "_run_dream_module"
    ), "Pipeline should have _run_dream_module method"

    # DREAM-03: 记忆扭曲按重要度×时间远近组合
    dream_distort_prompt = Path(__file__).parent.parent / "config" / "prompts" / "dream_distort.txt"
    assert (
        dream_distort_prompt.exists()
    ), f"dream_distort.txt should exist at {dream_distort_prompt}"
    content = dream_distort_prompt.read_text(encoding="utf-8")
    assert (
        "重要性" in content or "importance" in content.lower()
    ), "Should mention importance in distortion rules"
    assert (
        "时间" in content or "time" in content.lower()
    ), "Should mention time distance in distortion rules"

    # DREAM-04: 梦境推演节点标记
    dream_simulate_prompt = (
        Path(__file__).parent.parent / "config" / "prompts" / "dream_simulate.txt"
    )
    assert dream_simulate_prompt.exists(), "dream_simulate.txt should exist"
    content = dream_simulate_prompt.read_text(encoding="utf-8")
    assert "推演" in content or "simulate" in content.lower(), "Should mention simulation"
