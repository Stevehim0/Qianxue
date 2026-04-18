"""DecayConfigManager测试套件。

测试衰减参数配置管理器的读取、设置和验证功能。
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, patch
from io import StringIO

from Memory.consolidator.config_manager import DecayConfigManager
from Memory.storage.database import db_manager


class TestDecayConfigManagerBasic:
    """DecayConfigManager基础功能测试。"""

    def test_get_existing_parameter(self, db_with_schema):
        """测试get()方法读取存在的参数。"""
        manager = DecayConfigManager(db_with_schema)

        # 读取默认参数
        lambda_L0 = manager.get("lambda_L0")
        assert lambda_L0 is not None
        assert lambda_L0 == 0.01

        # 读取其他参数
        alpha = manager.get("alpha")
        assert alpha is not None
        assert alpha == 0.05

    def test_get_nonexistent_parameter(self, db_with_schema):
        """测试get()方法读取不存在的参数返回None。"""
        manager = DecayConfigManager(db_with_schema)

        # 读取不存在的参数
        result = manager.get("nonexistent_param")
        assert result is None

    def test_set_parameter(self, db_with_schema):
        """测试set()方法更新参数值。"""
        manager = DecayConfigManager(db_with_schema)

        # 设置新值
        success = manager.set("lambda_L0", 0.015)
        assert success is True

        # 验证值已更新
        updated_value = manager.get("lambda_L0")
        assert updated_value == 0.015

    def test_set_parameter_validation(self, db_with_schema):
        """测试set()方法参数验证失败抛出ValueError。"""
        manager = DecayConfigManager(db_with_schema)

        # 测试lambda参数必须大于0
        with pytest.raises(ValueError, match="lambda parameter must be > 0"):
            manager.set("lambda_L0", -0.1)

        with pytest.raises(ValueError, match="lambda parameter must be > 0"):
            manager.set("lambda_L0", 0)

        # 测试alpha必须在[0, 1]范围
        with pytest.raises(ValueError, match="alpha must be between 0 and 1"):
            manager.set("alpha", -0.1)

        with pytest.raises(ValueError, match="alpha must be between 0 and 1"):
            manager.set("alpha", 1.5)

        # 测试beta必须在[0, 1]范围
        with pytest.raises(ValueError, match="beta must be between 0 and 1"):
            manager.set("beta", -0.1)

        with pytest.raises(ValueError, match="beta must be between 0 and 1"):
            manager.set("beta", 1.5)

        # 测试dormancy_threshold必须在[0, 1]范围
        with pytest.raises(ValueError, match="dormancy_threshold must be between 0 and 1"):
            manager.set("dormancy_threshold", -0.1)

        with pytest.raises(ValueError, match="dormancy_threshold must be between 0 and 1"):
            manager.set("dormancy_threshold", 1.5)

    def test_list_all_parameters(self, db_with_schema):
        """测试list_all()方法返回所有参数。"""
        manager = DecayConfigManager(db_with_schema)

        configs = manager.list_all()

        # 验证返回11个默认参数
        assert len(configs) == 11

        # 验证必需的参数存在
        required_params = [
            "lambda_L0",
            "lambda_L1",
            "lambda_L2",
            "lambda_L3",
            "lambda_temporal",
            "lambda_thematic",
            "lambda_causal",
            "lambda_associative",
            "alpha",
            "beta",
            "dormancy_threshold",
        ]
        for param in required_params:
            assert param in configs
            assert "value" in configs[param]
            assert "description" in configs[param]

    def test_init_default_config(self, db_with_schema):
        """测试初始化时自动插入默认参数。"""
        # 先清空decay_config表
        with db_with_schema.transaction() as cursor:
            cursor.execute("DELETE FROM decay_config")

        # 创建新manager，应该自动初始化默认参数
        manager = DecayConfigManager(db_with_schema)

        # 验证默认参数已插入
        configs = manager.list_all()
        assert len(configs) == 11

        # 验证默认值正确
        assert configs["lambda_L0"]["value"] == 0.01
        assert configs["alpha"]["value"] == 0.05
        assert configs["beta"]["value"] == 0.5


@pytest.fixture
def db_with_schema(tmp_path):
    """创建带完整schema的测试数据库。"""
    from Memory.storage.schema import create_all_tables
    from Memory.storage.database import DatabaseManager

    # 创建临时数据库
    db_path = tmp_path / "test_decay_config.db"
    db = DatabaseManager(str(db_path))
    create_all_tables(db)

    # 创建decay_config表（如果schema.py中没有）
    with db.transaction() as cursor:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS decay_config (
                key TEXT PRIMARY KEY,
                value REAL NOT NULL,
                description TEXT,
                updated_at TEXT
            )
        """)

    return db


class TestCliConfigCommands:
    """CLI config子命令测试。"""

    @patch("sys.stdout", new_callable=StringIO)
    def test_config_list_all_parameters(self, mock_stdout, db_with_schema):
        """测试config --list列出所有参数。"""
        from Memory.consolidator import __main__

        # Mock DecayConfigManager
        with patch("Memory.consolidator.__main__.DecayConfigManager") as MockManager:
            mock_manager = Mock()
            mock_manager.list_all.return_value = {
                "lambda_L0": {"value": 0.01, "description": "L0摘要衰减率"},
                "lambda_L1": {"value": 0.02, "description": "L1要点衰减率"},
                "alpha": {"value": 0.05, "description": "强化系数"},
                "beta": {"value": 0.5, "description": "情感保护系数"},
            }
            MockManager.return_value = mock_manager

            with patch("sys.argv", ["Memory.consolidator", "config", "--list"]):
                result = __main__.main()

            assert result == 0
            output = mock_stdout.getvalue()
            assert "衰减参数配置" in output
            assert "lambda_L0" in output
            assert "0.010" in output
            assert "alpha" in output

    @patch("sys.stdout", new_callable=StringIO)
    def test_config_set_parameter(self, mock_stdout, db_with_schema):
        """测试config --set更新单个参数。"""
        from Memory.consolidator import __main__

        with patch("Memory.consolidator.__main__.DecayConfigManager") as MockManager:
            mock_manager = Mock()
            mock_manager.set.return_value = True
            MockManager.return_value = mock_manager

            with patch(
                "sys.argv", ["Memory.consolidator", "config", "--set", "lambda_L0", "0.015"]
            ):
                result = __main__.main()

            assert result == 0
            mock_manager.set.assert_called_once_with("lambda_L0", 0.015)
            output = mock_stdout.getvalue()
            assert "✓ 参数已更新" in output
            assert "lambda_L0 = 0.015" in output

    @patch("sys.stdout", new_callable=StringIO)
    def test_config_set_invalid_parameter(self, mock_stdout, db_with_schema):
        """测试config --set更新非法值显示错误。"""
        from Memory.consolidator import __main__

        with patch("Memory.consolidator.__main__.DecayConfigManager") as MockManager:
            mock_manager = Mock()
            mock_manager.set.side_effect = ValueError("lambda parameter must be > 0, got -0.1")
            MockManager.return_value = mock_manager

            with patch("sys.argv", ["Memory.consolidator", "config", "--set", "lambda_L0", "-0.1"]):
                result = __main__.main()

            assert result == 1
            output = mock_stdout.getvalue()
            assert "✗ 参数验证失败" in output
            assert "lambda parameter must be > 0" in output

    @patch("sys.stdout", new_callable=StringIO)
    def test_config_output_format(self, mock_stdout, db_with_schema):
        """测试config子命令输出格式正确。"""
        from Memory.consolidator import __main__

        with patch("Memory.consolidator.__main__.DecayConfigManager") as MockManager:
            mock_manager = Mock()
            mock_manager.list_all.return_value = {
                "lambda_L0": {"value": 0.01, "description": "L0摘要衰减率"},
                "alpha": {"value": 0.05, "description": "强化系数"},
            }
            MockManager.return_value = mock_manager

            with patch("sys.argv", ["Memory.consolidator", "config", "--list"]):
                result = __main__.main()

            assert result == 0
            output = mock_stdout.getvalue()
            # 验证格式对齐
            assert "=" in output
            assert "#" in output
            # 验证分组显示
            assert "[分层衰减参数]" in output
            assert "[其他参数]" in output


class TestConfigManagerIntegration:
    """ConfigManager与Pipeline集成测试。"""

    def test_pipeline_initializes_config_manager(self, db_with_schema):
        """测试Pipeline初始化时自动创建config_manager。"""
        from Memory.consolidator.pipeline import ConsolidationPipeline

        # 创建Pipeline（不传入config_manager）
        pipeline = ConsolidationPipeline()

        # 验证config_manager已初始化
        assert pipeline.config_manager is not None
        assert isinstance(pipeline.config_manager, DecayConfigManager)

    def test_pipeline_uses_injected_config_manager(self, db_with_schema):
        """测试Pipeline支持外部注入config_manager。"""
        from Memory.consolidator.pipeline import ConsolidationPipeline

        # 创建自定义config_manager
        custom_manager = DecayConfigManager(db_with_schema)

        # 创建Pipeline并注入config_manager
        pipeline = ConsolidationPipeline(config_manager=custom_manager)

        # 验证使用的是注入的config_manager
        assert pipeline.config_manager is custom_manager

    def test_decay_calculation_task_reads_parameters(self, db_with_schema):
        """测试_decay_calculation_task从config_manager读取参数。"""
        from Memory.consolidator.pipeline import ConsolidationPipeline

        # 创建config_manager并设置测试参数
        manager = DecayConfigManager(db_with_schema)
        manager.set("lambda_L0", 0.025)
        manager.set("alpha", 0.08)

        # 创建Pipeline并注入config_manager
        pipeline = ConsolidationPipeline(config_manager=manager)

        # 调用_decay_calculation_task
        result = pipeline._decay_calculation_task()

        # 验证参数读取正确
        assert result["status"] == "not_implemented"
        # 注意：实际的衰减计算将在08-02计划中实现
        # 这里只验证参数传递机制
