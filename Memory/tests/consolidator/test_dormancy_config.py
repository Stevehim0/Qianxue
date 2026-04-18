"""测试休眠阈值配置功能。

测试覆盖：
- ConsolidationConfig包含dormancy_threshold字段
- 字段默认值为0.05
- __post_init__包含dormancy_threshold验证（0-1范围）
- Settings.get_summary()包含dormancy_threshold
"""

import pytest
from Memory.config.settings import Settings, ConsolidationConfig


class TestDormancyThresholdConfig:
    """测试休眠阈值配置。"""

    def test_consolidation_config_has_dormancy_threshold(self):
        """测试1: ConsolidationConfig包含dormancy_threshold字段。"""
        config = ConsolidationConfig()
        assert hasattr(config, "dormancy_threshold")
        assert config.dormancy_threshold == 0.05

    def test_dormancy_threshold_default_value(self):
        """测试2: dormancy_threshold字段默认值为0.05。"""
        config = ConsolidationConfig()
        assert config.dormancy_threshold == 0.05

    def test_dormancy_threshold_custom_value(self):
        """测试3: dormancy_threshold可以自定义值。"""
        config = ConsolidationConfig(dormancy_threshold=0.1)
        assert config.dormancy_threshold == 0.1

    def test_dormancy_threshold_validation_valid_range(self):
        """测试4: dormancy_threshold验证接受有效范围内的值。"""
        # 边界值测试
        config1 = ConsolidationConfig(dormancy_threshold=0.0)
        assert config1.dormancy_threshold == 0.0

        config2 = ConsolidationConfig(dormancy_threshold=1.0)
        assert config2.dormancy_threshold == 1.0

        config3 = ConsolidationConfig(dormancy_threshold=0.5)
        assert config3.dormancy_threshold == 0.5

    def test_dormancy_threshold_validation_invalid_low(self):
        """测试5: dormancy_threshold验证拒绝小于0的值。"""
        with pytest.raises(ValueError) as exc_info:
            ConsolidationConfig(dormancy_threshold=-0.1)

        assert "dormancy_threshold must be between 0 and 1" in str(exc_info.value)

    def test_dormancy_threshold_validation_invalid_high(self):
        """测试6: dormancy_threshold验证拒绝大于1的值。"""
        with pytest.raises(ValueError) as exc_info:
            ConsolidationConfig(dormancy_threshold=1.5)

        assert "dormancy_threshold must be between 0 and 1" in str(exc_info.value)

    def test_settings_includes_dormancy_threshold(self):
        """测试7: Settings包含dormancy_threshold配置。"""
        settings = Settings()
        assert hasattr(settings.consolidation, "dormancy_threshold")
        assert settings.consolidation.dormancy_threshold == 0.05

    def test_settings_get_summary_includes_dormancy_threshold(self):
        """测试8: Settings.get_summary()包含dormancy_threshold。"""
        settings = Settings()
        summary = settings.get_summary()

        assert "consolidation" in summary
        assert "dormancy_threshold" in summary["consolidation"]
        assert summary["consolidation"]["dormancy_threshold"] == 0.05

    def test_settings_custom_dormancy_threshold(self):
        """测试9: Settings可以自定义dormancy_threshold。"""
        settings = Settings(consolidation=ConsolidationConfig(dormancy_threshold=0.15))

        assert settings.consolidation.dormancy_threshold == 0.15

        summary = settings.get_summary()
        assert summary["consolidation"]["dormancy_threshold"] == 0.15


class TestDormancyThresholdIntegration:
    """测试休眠阈值配置的集成场景。"""

    def test_consolidation_config_all_fields_valid(self):
        """测试10: ConsolidationConfig所有字段都可以正常设置。"""
        config = ConsolidationConfig(
            batch_size=30,
            max_workers=4,
            similarity_threshold=0.8,
            min_importance_for_l1l2=0.6,
            property_upgrade_threshold=10,
            dormancy_threshold=0.03,
        )

        assert config.batch_size == 30
        assert config.max_workers == 4
        assert config.similarity_threshold == 0.8
        assert config.min_importance_for_l1l2 == 0.6
        assert config.property_upgrade_threshold == 10
        assert config.dormancy_threshold == 0.03

    def test_dormancy_threshold_edge_cases(self):
        """测试11: dormancy_threshold边界值测试。"""
        # 测试非常小的值
        config1 = ConsolidationConfig(dormancy_threshold=0.001)
        assert config1.dormancy_threshold == 0.001

        # 测试非常大的值
        config2 = ConsolidationConfig(dormancy_threshold=0.999)
        assert config2.dormancy_threshold == 0.999

    def test_settings_summary_complete(self):
        """测试12: Settings.get_summary()返回完整的配置信息。"""
        settings = Settings()
        summary = settings.get_summary()

        consolidation_summary = summary["consolidation"]
        expected_keys = [
            "batch_size",
            "max_workers",
            "similarity_threshold",
            "min_importance_for_l1l2",
            "property_upgrade_threshold",
            "dormancy_threshold",
        ]

        for key in expected_keys:
            assert key in consolidation_summary, f"Missing key: {key}"
