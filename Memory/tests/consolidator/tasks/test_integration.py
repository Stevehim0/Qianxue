"""任务模块和Pipeline集成测试。"""

import pytest
from unittest.mock import Mock, patch

from Memory.consolidator.tasks import extract_l1l2, calculate_importance
from Memory.consolidator.pipeline import ConsolidationPipeline


class TestTaskModuleExports:
    """测试tasks模块导出。"""

    def test_tasks_module_exports(self):
        """测试1：tasks模块导出extract_l1l2和calculate_importance。"""
        # 验证模块可以导入
        from Memory.consolidator.tasks import extract_l1l2, calculate_importance

        # 验证是可调用的函数
        assert callable(extract_l1l2)
        assert callable(calculate_importance)

    def test_tasks_module_all(self):
        """测试2：__all__列表包含正确的函数名。"""
        import Memory.consolidator.tasks as tasks_module

        assert "extract_l1l2" in tasks_module.__all__
        assert "calculate_importance" in tasks_module.__all__


class TestPipelineIntegration:
    """测试ConsolidationPipeline集成。"""

    @pytest.fixture
    def mock_pipeline(self):
        """创建Mock的ConsolidationPipeline。"""
        with patch("Memory.consolidator.pipeline.LLMFactory.create_client") as mock_llm:
            mock_llm.return_value = Mock()

            pipeline = ConsolidationPipeline(
                llm_client=mock_llm.return_value,
                experience_store=Mock(),
                experience_edge_store=Mock(),
                entity_store=Mock(),
            )

            # Mock experience store methods
            pipeline.experience_store.get_consolidation_candidates = Mock(return_value=[])
            pipeline.experience_store.update_consolidated_batch = Mock(return_value=0)

            yield pipeline

    def test_pipeline_has_extract_l1l2_task(self, mock_pipeline):
        """测试3：ConsolidationPipeline有_extract_l1l2_task方法。"""
        assert hasattr(mock_pipeline, "_extract_l1l2_task")
        assert callable(mock_pipeline._extract_l1l2_task)

    def test_pipeline_has_calculate_importance_task(self, mock_pipeline):
        """测试4：ConsolidationPipeline有_calculate_importance_task方法。"""
        assert hasattr(mock_pipeline, "_calculate_importance_task")
        assert callable(mock_pipeline._calculate_importance_task)

    def test_extract_l1l2_task_calls_extract_l1l2(self, mock_pipeline):
        """测试5：_extract_l1l2_task调用extract_l1l2函数。"""
        from Memory.storage.experience_store import Experience

        experiences = [Experience(id="exp_001", L3_raw="测试内容", L0_text="测试", importance=0.7)]

        # Mock the extract_l1l2 function
        with patch("Memory.consolidator.pipeline.extract_l1l2") as mock_extract:
            mock_extract.return_value = {
                "updated_count": 1,
                "skipped_count": 0,
                "failed_count": 0,
                "total_count": 1,
            }

            result = mock_pipeline._extract_l1l2_task(experiences)

            # 验证extract_l1l2被调用
            mock_extract.assert_called_once()
            assert result["updated_count"] == 1

    def test_calculate_importance_task_calls_calculate_importance(self, mock_pipeline):
        """测试6：_calculate_importance_task调用calculate_importance函数。"""
        from Memory.storage.experience_store import Experience

        experiences = [
            Experience(id="exp_001", L3_raw="测试内容", L0_text="测试", emotion_intensity=0.5)
        ]

        # Mock the calculate_importance function
        with patch("Memory.consolidator.pipeline.calculate_importance") as mock_calc:
            mock_calc.return_value = {"updated_count": 1, "total_count": 1, "avg_importance": 0.5}

            result = mock_pipeline._calculate_importance_task(experiences)

            # 验证calculate_importance被调用
            mock_calc.assert_called_once()
            assert result["updated_count"] == 1
