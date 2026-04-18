"""L0摘要生成任务测试。"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import numpy as np

from Memory.writer.tasks.l0_summary_task import generate_l0_summary
from Memory.storage.experience_store import Experience


class TestL0SummaryGeneration:
    """L0摘要生成功能测试。"""

    def test_generate_l0_summary_success(
        self,
        sample_experience_id,
        sample_raw_text,
        mock_llm_client,
        mock_embedding_service,
        mock_vector_store,
        temp_db_dir,
    ):
        """测试成功生成L0摘要。"""
        # 准备测试数据
        experience_store = Mock()
        experience_store.get.return_value = Experience(
            id=sample_experience_id, L3_raw=sample_raw_text, created_at="2026-03-31T12:00:00"
        )
        experience_store.update.return_value = True

        # 执行
        result = generate_l0_summary(
            experience_id=sample_experience_id,
            raw_text=sample_raw_text,
            llm_client=mock_llm_client,
            embedding_service=mock_embedding_service,
            vector_store=mock_vector_store,
            experience_store=experience_store,
        )

        # 验证
        assert result == "和朋友爬山看到美景，心情舒畅"
        assert mock_llm_client.call_with_retry.called
        assert mock_embedding_service.encode.called
        assert experience_store.update.called
        assert mock_vector_store.add_experience.called

    def test_generate_l0_summary_llm_failure(
        self,
        sample_experience_id,
        sample_raw_text,
        mock_llm_client,
        mock_embedding_service,
        mock_vector_store,
        temp_db_dir,
    ):
        """测试LLM调用失败抛出异常。"""
        # 准备：LLM调用失败
        mock_llm_client.call_with_retry.side_effect = Exception("LLM API error")

        experience_store = Mock()
        experience_store.get.return_value = Experience(
            id=sample_experience_id, L3_raw=sample_raw_text
        )

        # 执行和验证
        with pytest.raises(Exception, match="LLM API error"):
            generate_l0_summary(
                experience_id=sample_experience_id,
                raw_text=sample_raw_text,
                llm_client=mock_llm_client,
                embedding_service=mock_embedding_service,
                vector_store=mock_vector_store,
                experience_store=experience_store,
            )

    def test_generate_l0_summary_embedding_storage(
        self,
        sample_experience_id,
        sample_raw_text,
        mock_llm_client,
        mock_embedding_service,
        mock_vector_store,
        temp_db_dir,
    ):
        """测试embedding向量正确存储。"""
        # 准备
        experience_store = Mock()
        experience_store.get.return_value = Experience(
            id=sample_experience_id, L3_raw=sample_raw_text
        )
        experience_store.update.return_value = True

        # 执行
        generate_l0_summary(
            experience_id=sample_experience_id,
            raw_text=sample_raw_text,
            llm_client=mock_llm_client,
            embedding_service=mock_embedding_service,
            vector_store=mock_vector_store,
            experience_store=experience_store,
        )

        # 验证：embedding存入数据库
        updated_exp = experience_store.update.call_args[0][0]
        assert updated_exp.L0_text == "和朋友爬山看到美景，心情舒畅"
        assert updated_exp.L0_embedding is not None
        assert isinstance(updated_exp.L0_embedding, np.ndarray)

        # 验证：embedding存入ChromaDB
        assert mock_vector_store.add_experience.called
        call_args = mock_vector_store.add_experience.call_args
        assert call_args[1]["exp_id"] == sample_experience_id
        assert isinstance(call_args[1]["embedding"], list)
