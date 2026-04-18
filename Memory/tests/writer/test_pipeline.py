"""WriterPipeline集成测试。"""

import pytest
from unittest.mock import Mock, patch
from Memory.writer.pipeline import WriterPipeline


class TestWriterPipelineIntegration:
    """WriterPipeline集成测试。"""

    def test_process_event_full_flow(
        self,
        sample_raw_text,
        mock_llm_client,
        mock_embedding_service,
        mock_vector_store,
        temp_db_dir,
    ):
        """测试完整流程：原始记录 → 并行任务 → 边创建 → 状态更新。"""
        # 准备
        raw_recorder = Mock()
        raw_recorder.record_event.return_value = "exp_20260331_120000"

        experience_store = Mock()
        experience_store.get.return_value = Mock()
        experience_store.update.return_value = True

        entity_store = Mock()
        entity_store.get_by_name.return_value = None
        entity_store.create.return_value = "entity-123"

        cross_edge_store = Mock()
        cross_edge_store.create.return_value = 1

        experience_edge_store = Mock()
        experience_edge_store.create.return_value = 1

        state_manager = Mock()
        state_manager.get_mood.return_value = Mock(label="平静", valence=0.0, arousal=0.3)
        state_manager.get_focus.return_value = None

        # 创建pipeline
        pipeline = WriterPipeline(
            raw_recorder=raw_recorder,
            llm_client=mock_llm_client,
            embedding_service=mock_embedding_service,
            vector_store=mock_vector_store,
            experience_store=experience_store,
            entity_store=entity_store,
            cross_edge_store=cross_edge_store,
            experience_edge_store=experience_edge_store,
            state_manager=state_manager,
        )

        # 执行
        exp_id = pipeline.process_event(role="user", content=sample_raw_text)

        # 验证
        assert exp_id == "exp_20260331_120000"
        assert raw_recorder.record_event.called
        assert mock_llm_client.call_with_retry.call_count == 3  # L0/实体/情感
        assert experience_store.update.call_count == 2  # L0 + 情感
        assert entity_store.create.called
        assert cross_edge_store.create.called
        assert experience_edge_store.create.called

    def test_parallel_execution(
        self,
        sample_raw_text,
        mock_llm_client,
        mock_embedding_service,
        mock_vector_store,
        temp_db_dir,
    ):
        """测试三项任务并行执行。"""
        # 准备
        raw_recorder = Mock()
        raw_recorder.record_event.return_value = "exp_20260331_120000"

        experience_store = Mock()
        experience_store.get.return_value = Mock()
        experience_store.update.return_value = True

        entity_store = Mock()
        entity_store.get_by_name.return_value = None
        entity_store.create.return_value = "entity-123"

        cross_edge_store = Mock()
        experience_edge_store = Mock()

        state_manager = Mock()
        state_manager.get_mood.return_value = Mock(label="平静", valence=0.0, arousal=0.3)
        state_manager.get_focus.return_value = None

        pipeline = WriterPipeline(
            raw_recorder=raw_recorder,
            llm_client=mock_llm_client,
            embedding_service=mock_embedding_service,
            vector_store=mock_vector_store,
            experience_store=experience_store,
            entity_store=entity_store,
            cross_edge_store=cross_edge_store,
            experience_edge_store=experience_edge_store,
            state_manager=state_manager,
        )

        # 执行
        pipeline.process_event(role="user", content=sample_raw_text)

        # 验证：三个LLM调用都发生
        assert mock_llm_client.call_with_retry.call_count == 3

    def test_all_fail_strategy(
        self,
        sample_raw_text,
        mock_llm_client,
        mock_embedding_service,
        mock_vector_store,
        temp_db_dir,
    ):
        """测试全部失败策略：任何任务失败，整体失败。"""
        # 准备：LLM调用失败
        mock_llm_client.call_with_retry.side_effect = Exception("LLM error")

        raw_recorder = Mock()
        raw_recorder.record_event.return_value = "exp_20260331_120000"

        experience_store = Mock()
        entity_store = Mock()
        cross_edge_store = Mock()
        experience_edge_store = Mock()
        state_manager = Mock()

        pipeline = WriterPipeline(
            raw_recorder=raw_recorder,
            llm_client=mock_llm_client,
            embedding_service=mock_embedding_service,
            vector_store=mock_vector_store,
            experience_store=experience_store,
            entity_store=entity_store,
            cross_edge_store=cross_edge_store,
            experience_edge_store=experience_edge_store,
            state_manager=state_manager,
        )

        # 执行和验证
        with pytest.raises(Exception, match="LLM error"):
            pipeline.process_event(role="user", content=sample_raw_text)
