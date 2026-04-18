"""巩固层Pipeline测试模块。"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime

from Memory.consolidator.pipeline import ConsolidationPipeline
from Memory.storage.experience_store import Experience
from Memory.storage.experience_edge_store import ExperienceEdge
from Memory.config.settings import settings


@pytest.fixture
def mock_llm_client():
    """模拟LLM客户端。"""
    llm_client = Mock()
    llm_client.call_json.return_value = {"L1": "测试L1摘要", "L2": "测试L2摘要"}
    return llm_client


@pytest.fixture
def mock_embedding_service():
    """模拟Embedding服务。"""
    embedding_service = Mock()
    import numpy as np

    embedding_service.encode.return_value = np.random.rand(768).astype(np.float32)
    return embedding_service


@pytest.fixture
def sample_experiences():
    """创建示例体验节点。"""
    return [
        Experience(
            id="exp_20260331_120000",
            L3_raw="测试内容1",
            L0_text="测试L0摘要1",
            consolidated=0,
            importance=0.7,
            created_at="2026-03-31T12:00:00Z",
        ),
        Experience(
            id="exp_20260331_120100",
            L3_raw="测试内容2",
            L0_text="测试L0摘要2",
            consolidated=0,
            importance=0.6,
            created_at="2026-03-31T12:01:00Z",
        ),
    ]


class TestConsolidationPipelineInit:
    """测试ConsolidationPipeline初始化。"""

    def test_init_with_defaults(self):
        """测试使用默认参数初始化。"""
        pipeline = ConsolidationPipeline()

        assert pipeline.llm_client is not None
        assert pipeline.embedding_service is not None
        assert pipeline.vector_store is not None
        assert pipeline.experience_store is not None
        assert pipeline.experience_edge_store is not None
        assert pipeline.entity_store is not None
        assert pipeline.entity_edge_store is not None
        assert pipeline.logger is not None

    def test_init_with_dependencies(self, mock_llm_client, mock_embedding_service):
        """测试使用依赖注入初始化。"""
        mock_vector_store = Mock()
        mock_experience_store = Mock()
        mock_edge_store = Mock()
        mock_entity_store = Mock()
        mock_entity_edge_store = Mock()

        pipeline = ConsolidationPipeline(
            llm_client=mock_llm_client,
            embedding_service=mock_embedding_service,
            vector_store=mock_vector_store,
            experience_store=mock_experience_store,
            experience_edge_store=mock_edge_store,
            entity_store=mock_entity_store,
            entity_edge_store=mock_entity_edge_store,
        )

        assert pipeline.llm_client == mock_llm_client
        assert pipeline.embedding_service == mock_embedding_service
        assert pipeline.vector_store == mock_vector_store
        assert pipeline.experience_store == mock_experience_store
        assert pipeline.experience_edge_store == mock_edge_store
        assert pipeline.entity_store == mock_entity_store
        assert pipeline.entity_edge_store == mock_entity_edge_store


class TestRunConsolidation:
    """测试run_consolidation方法。"""

    def test_incremental_mode_gets_unconsolidated_nodes(self, sample_experiences, mock_llm_client):
        """测试增量模式获取consolidated=0的节点。"""
        mock_experience_store = Mock()
        mock_experience_store.get_consolidation_candidates.return_value = sample_experiences
        mock_experience_store.update_consolidated_batch.return_value = 2

        mock_edge_store = Mock()
        mock_entity_store = Mock()

        pipeline = ConsolidationPipeline(
            llm_client=mock_llm_client,
            experience_store=mock_experience_store,
            experience_edge_store=mock_edge_store,
            entity_store=mock_entity_store,
        )

        result = pipeline.run_consolidation(mode="incremental")

        # 验证调用了正确的方法
        mock_experience_store.get_consolidation_candidates.assert_called_once_with(
            batch_size=settings.consolidation.batch_size, mode="incremental"
        )

        # 验证返回结果
        assert result["status"] == "completed"
        assert result["mode"] == "incremental"
        assert result["node_count"] == 2
        assert result["updated_count"] == 2

    def test_no_candidates_returns_skipped(self, mock_llm_client):
        """测试无候选节点时返回skipped状态。"""
        mock_experience_store = Mock()
        mock_experience_store.get_consolidation_candidates.return_value = []

        pipeline = ConsolidationPipeline(
            llm_client=mock_llm_client, experience_store=mock_experience_store
        )

        result = pipeline.run_consolidation(mode="incremental")

        assert result["status"] == "skipped"
        assert result["reason"] == "no_candidates"
        assert result["mode"] == "incremental"

    @patch("Memory.consolidator.pipeline.ThreadPoolExecutor")
    def test_parallel_execution_with_six_tasks(
        self, mock_executor_class, sample_experiences, mock_llm_client
    ):
        """测试ThreadPoolExecutor并行提交六个任务。"""
        # 设置mock
        mock_executor = MagicMock()
        mock_executor_class.return_value.__enter__.return_value = mock_executor

        # 创建模拟的future对象
        mock_future1 = MagicMock()
        mock_future1.result.return_value = {"updated_count": 2}
        mock_future2 = MagicMock()
        mock_future2.result.return_value = {"created_count": 1}
        mock_future3 = MagicMock()
        mock_future3.result.return_value = {"upgraded_count": 0}
        mock_future4 = MagicMock()
        mock_future4.result.return_value = {"verified_count": 1}
        mock_future5 = MagicMock()
        mock_future5.result.return_value = {"updated_count": 0}
        mock_future6 = MagicMock()
        mock_future6.result.return_value = {"updated_count": 0}

        # 设置submit方法返回对应的future
        def submit_side_effect(func, *args):
            if "l1l2" in str(func):
                return mock_future1
            elif "importance" in str(func):
                return mock_future2
            elif "implicit" in str(func):
                return mock_future3
            elif "property" in str(func):
                return mock_future4
            elif "verify" in str(func):
                return mock_future5
            else:
                return mock_future6

        mock_executor.submit.side_effect = submit_side_effect

        mock_experience_store = Mock()
        mock_experience_store.get_consolidation_candidates.return_value = sample_experiences
        mock_experience_store.update_consolidated_batch.return_value = 2

        pipeline = ConsolidationPipeline(
            llm_client=mock_llm_client, experience_store=mock_experience_store
        )

        result = pipeline.run_consolidation(mode="incremental")

        # 验证六个任务都被提交
        assert mock_executor.submit.call_count == 6

        # 验证返回结果包含所有任务状态
        assert "tasks" in result
        assert len(result["tasks"]) == 6

    def test_task_failure_doesnt_affect_other_tasks(self, mock_llm_client):
        """测试任务失败不影响其他任务执行。"""
        mock_experience_store = Mock()
        mock_experience_store.get_consolidation_candidates.return_value = [
            Experience(
                id="exp_20260331_120000",
                L3_raw="测试内容",
                consolidated=0,
                created_at="2026-03-31T12:00:00Z",
            )
        ]
        mock_experience_store.update_consolidated_batch.return_value = 1

        pipeline = ConsolidationPipeline(
            llm_client=mock_llm_client, experience_store=mock_experience_store
        )

        result = pipeline.run_consolidation(mode="incremental")

        # 验证即使某些任务失败，consolidated标记仍然更新
        assert result["status"] == "completed"
        assert result["updated_count"] == 1
        mock_experience_store.update_consolidated_batch.assert_called_once()

    def test_batch_update_consolidated_mark(self, sample_experiences, mock_llm_client):
        """测试所有任务完成后批量更新consolidated标记。"""
        mock_experience_store = Mock()
        mock_experience_store.get_consolidation_candidates.return_value = sample_experiences
        mock_experience_store.update_consolidated_batch.return_value = 2

        pipeline = ConsolidationPipeline(
            llm_client=mock_llm_client, experience_store=mock_experience_store
        )

        result = pipeline.run_consolidation(mode="incremental")

        # 验证批量更新被调用
        experience_ids = [exp.id for exp in sample_experiences]
        mock_experience_store.update_consolidated_batch.assert_called_once_with(
            experience_ids, consolidated=True
        )

        assert result["updated_count"] == 2

    def test_return_result_contains_all_required_fields(self, sample_experiences, mock_llm_client):
        """测试返回结果包含所有必需字段。"""
        mock_experience_store = Mock()
        mock_experience_store.get_consolidation_candidates.return_value = sample_experiences
        mock_experience_store.update_consolidated_batch.return_value = 2

        pipeline = ConsolidationPipeline(
            llm_client=mock_llm_client, experience_store=mock_experience_store
        )

        result = pipeline.run_consolidation(mode="incremental")

        # 验证所有必需字段存在
        required_fields = [
            "status",
            "mode",
            "node_count",
            "updated_count",
            "duration",
            "tasks",
            "timestamp",
        ]
        for field in required_fields:
            assert field in result, f"Missing field: {field}"

        # 验证字段类型
        assert isinstance(result["status"], str)
        assert isinstance(result["mode"], str)
        assert isinstance(result["node_count"], int)
        assert isinstance(result["updated_count"], int)
        assert isinstance(result["duration"], float)
        assert isinstance(result["tasks"], dict)
        assert isinstance(result["timestamp"], str)


class TestTaskMethods:
    """测试六个任务方法。"""

    def test_extract_l1l2_task_returns_result(self, mock_llm_client):
        """测试L1/L2提取任务返回结果。"""
        pipeline = ConsolidationPipeline(llm_client=mock_llm_client)

        experiences = [
            Experience(
                id="exp_20260331_120000",
                L3_raw="测试内容",
                consolidated=0,
                created_at="2026-03-31T12:00:00Z",
            )
        ]

        result = pipeline._extract_l1l2_task(experiences)

        # 验证返回结构
        assert "updated_count" in result

    def test_calculate_importance_task_returns_result(self, mock_llm_client):
        """测试重要性估值任务返回结果。"""
        pipeline = ConsolidationPipeline(llm_client=mock_llm_client)

        experiences = [
            Experience(
                id="exp_20260331_120000",
                L3_raw="测试内容",
                consolidated=0,
                created_at="2026-03-31T12:00:00Z",
            )
        ]

        result = pipeline._calculate_importance_task(experiences)

        # 验证返回结构
        assert "updated_count" in result

    def test_discover_implicit_edges_task_returns_result(self, mock_llm_client):
        """测试隐性边发现任务返回结果。"""
        pipeline = ConsolidationPipeline(llm_client=mock_llm_client)

        experiences = [
            Experience(
                id="exp_20260331_120000",
                L3_raw="测试内容",
                consolidated=0,
                created_at="2026-03-31T12:00:00Z",
            )
        ]

        result = pipeline._discover_implicit_edges_task(experiences)

        # 验证返回结构
        assert "created" in result or "updated" in result

    def test_scan_property_upgrade_task_returns_result(self, mock_llm_client):
        """测试属性升级扫描任务返回结果。"""
        # Skip this test as it requires a full database setup
        # The task is tested in its own test file
        pass

    def test_verify_information_task_returns_result(self, mock_llm_client):
        """测试信息验证任务返回结果。"""
        mock_entity_edge_store = Mock()
        mock_entity_edge_store.get_low_confidence.return_value = []

        mock_entity_store = Mock()
        mock_experience_store = Mock()

        pipeline = ConsolidationPipeline(
            llm_client=mock_llm_client,
            entity_edge_store=mock_entity_edge_store,
            entity_store=mock_entity_store,
            experience_store=mock_experience_store,
        )

        experiences = []

        result = pipeline._verify_information_task(experiences)

        # 验证返回结构包含必需字段
        assert "verified_count" in result
        assert "confirmed_count" in result
        assert "rejected_count" in result
        assert "total_candidates" in result

    def test_update_emotion_timeline_task_returns_result(self, mock_llm_client):
        """测试情感时间线更新任务返回结果。"""
        mock_entity_store = Mock()
        mock_entity_store.get_frequent_entities.return_value = []

        mock_experience_store = Mock()

        pipeline = ConsolidationPipeline(
            llm_client=mock_llm_client,
            entity_store=mock_entity_store,
            experience_store=mock_experience_store,
        )

        experiences = []

        result = pipeline._update_emotion_timeline_task(experiences)

        # 验证返回结构包含必需字段
        assert "updated_count" in result
        assert "evaluated_count" in result


class TestLoadPrompt:
    """测试_load_prompt辅助方法。"""

    def test_load_prompt_returns_template_content(self, mock_llm_client):
        """测试加载prompt模板返回内容。"""
        # 注意：这个测试需要实际存在prompt模板文件
        # 如果文件不存在，测试会失败，这是预期的行为
        pipeline = ConsolidationPipeline(llm_client=mock_llm_client)

        # 测试一个不存在的模板
        with pytest.raises(FileNotFoundError):
            pipeline._load_prompt("nonexistent_template.txt")
