"""巩固层CLI命令测试。"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from io import StringIO

from Memory.consolidator.pipeline import ConsolidationPipeline


@pytest.fixture
def mock_pipeline():
    """Mock ConsolidationPipeline实例。"""
    pipeline = Mock(spec=ConsolidationPipeline)

    # 模拟正常执行结果
    pipeline.run_consolidation.return_value = {
        "status": "completed",
        "mode": "incremental",
        "node_count": 5,
        "updated_count": 5,
        "duration": 1.5,
        "tasks": {
            "l1l2_extraction": {"status": "completed", "result": {"updated_count": 3}},
            "importance_valuation": {"status": "completed", "result": {"updated_count": 5}},
            "implicit_edges": {"status": "completed", "result": {"created": 2}},
            "property_upgrade": {"status": "completed", "result": {"upgraded_count": 0}},
            "information_verification": {"status": "completed", "result": {}},
            "emotion_timeline": {"status": "completed", "result": {"updated_count": 1}},
        },
    }

    return pipeline


class TestRunConsolidation:
    """CLI run命令测试。"""

    @patch("sys.stdout", new_callable=StringIO)
    @patch(
        "Memory.consolidator.__main__.ConsolidationPipeline",
        return_value=Mock(
            run_consolidation=Mock(
                return_value={
                    "status": "completed",
                    "mode": "incremental",
                    "node_count": 5,
                    "updated_count": 5,
                    "duration": 1.5,
                    "tasks": {},
                }
            )
        ),
    )
    def test_run_consolidation_default_mode(self, mock_pipeline_class, mock_stdout):
        """测试默认增量模式。"""
        from Memory.consolidator import __main__

        # 模拟命令行参数
        with patch("sys.argv", ["Memory.consolidator", "run"]):
            result = __main__.main()

        assert result == 0
        # 验证调用了run_consolidation
        mock_pipeline_instance = mock_pipeline_class.return_value
        mock_pipeline_instance.run_consolidation.assert_called_once_with(mode="incremental")

    @patch("sys.stdout", new_callable=StringIO)
    @patch(
        "Memory.consolidator.__main__.ConsolidationPipeline",
        return_value=Mock(
            run_consolidation=Mock(
                return_value={
                    "status": "completed",
                    "mode": "full",
                    "node_count": 10,
                    "updated_count": 10,
                    "duration": 2.0,
                    "tasks": {},
                }
            )
        ),
    )
    def test_run_consolidation_full_mode(self, mock_pipeline_class, mock_stdout):
        """测试全量模式。"""
        from Memory.consolidator import __main__

        with patch("sys.argv", ["Memory.consolidator", "run", "--mode", "full"]):
            result = __main__.main()

        assert result == 0
        mock_pipeline_instance = mock_pipeline_class.return_value
        mock_pipeline_instance.run_consolidation.assert_called_once_with(mode="full")

    @patch(
        "Memory.consolidator.__main__.ConsolidationPipeline",
        return_value=Mock(
            run_consolidation=Mock(
                return_value={"status": "skipped", "reason": "no_candidates", "mode": "incremental"}
            )
        ),
    )
    def test_run_consolidation_no_candidates(self, mock_pipeline_class):
        """测试无候选节点情况。"""
        from Memory.consolidator import __main__

        with patch("sys.argv", ["Memory.consolidator", "run"]):
            result = __main__.main()

        assert result == 0

    @patch(
        "Memory.consolidator.__main__.ConsolidationPipeline",
        return_value=Mock(run_consolidation=Mock(side_effect=Exception("Test error"))),
    )
    def test_run_consolidation_error_handling(self, mock_pipeline_class):
        """测试错误处理。"""
        from Memory.consolidator import __main__

        with patch("sys.argv", ["Memory.consolidator", "run"]):
            result = __main__.main()

        assert result == 1
