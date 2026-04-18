"""巩固层配置测试。

测试 ConsolidationConfig 配置类的默认值和验证逻辑。
"""

import pytest
from Memory.config.settings import ConsolidationConfig, Settings


class TestConsolidationConfigDefaults:
    """测试 ConsolidationConfig 默认值。"""

    def test_batch_size_default(self):
        """测试 batch_size 默认值为 20。"""
        config = ConsolidationConfig()
        assert config.batch_size == 20

    def test_max_workers_default(self):
        """测试 max_workers 默认值为 None。"""
        config = ConsolidationConfig()
        assert config.max_workers is None

    def test_similarity_threshold_default(self):
        """测试 similarity_threshold 默认值为 0.7。"""
        config = ConsolidationConfig()
        assert config.similarity_threshold == 0.7

    def test_min_importance_for_l1l2_default(self):
        """测试 min_importance_for_l1l2 默认值为 0.5。"""
        config = ConsolidationConfig()
        assert config.min_importance_for_l1l2 == 0.5

    def test_property_upgrade_threshold_default(self):
        """测试 property_upgrade_threshold 默认值为 5。"""
        config = ConsolidationConfig()
        assert config.property_upgrade_threshold == 5


class TestConsolidationConfigFields:
    """测试 ConsolidationConfig 包含所有必需字段。"""

    def test_has_batch_size_field(self):
        """测试包含 batch_size 字段。"""
        config = ConsolidationConfig()
        assert hasattr(config, "batch_size")

    def test_has_max_workers_field(self):
        """测试包含 max_workers 字段。"""
        config = ConsolidationConfig()
        assert hasattr(config, "max_workers")

    def test_has_similarity_threshold_field(self):
        """测试包含 similarity_threshold 字段。"""
        config = ConsolidationConfig()
        assert hasattr(config, "similarity_threshold")

    def test_has_min_importance_for_l1l2_field(self):
        """测试包含 min_importance_for_l1l2 字段。"""
        config = ConsolidationConfig()
        assert hasattr(config, "min_importance_for_l1l2")

    def test_has_property_upgrade_threshold_field(self):
        """测试包含 property_upgrade_threshold 字段。"""
        config = ConsolidationConfig()
        assert hasattr(config, "property_upgrade_threshold")


class TestSettingsConsolidationAttribute:
    """测试 Settings 类包含 consolidation 属性。"""

    def test_settings_has_consolidation(self):
        """测试 Settings 包含 consolidation 属性。"""
        settings = Settings()
        assert hasattr(settings, "consolidation")

    def test_consolidation_is_consolidation_config(self):
        """测试 consolidation 属性是 ConsolidationConfig 类型。"""
        settings = Settings()
        assert isinstance(settings.consolidation, ConsolidationConfig)


class TestConsolidationConfigValidation:
    """测试配置值范围验证。"""

    def test_similarity_threshold_valid_range(self):
        """测试 similarity_threshold 在 [0, 1] 范围内有效。"""
        config = ConsolidationConfig(similarity_threshold=0.5)
        assert config.similarity_threshold == 0.5

    def test_similarity_threshold_boundary_0(self):
        """测试 similarity_threshold 边界值 0 有效。"""
        config = ConsolidationConfig(similarity_threshold=0.0)
        assert config.similarity_threshold == 0.0

    def test_similarity_threshold_boundary_1(self):
        """测试 similarity_threshold 边界值 1 有效。"""
        config = ConsolidationConfig(similarity_threshold=1.0)
        assert config.similarity_threshold == 1.0

    def test_similarity_threshold_invalid_negative(self):
        """测试 similarity_threshold 小于 0 抛出 ValueError。"""
        with pytest.raises(ValueError, match="similarity_threshold"):
            ConsolidationConfig(similarity_threshold=-0.1)

    def test_similarity_threshold_invalid_greater_than_1(self):
        """测试 similarity_threshold 大于 1 抛出 ValueError。"""
        with pytest.raises(ValueError, match="similarity_threshold"):
            ConsolidationConfig(similarity_threshold=1.1)

    def test_min_importance_for_l1l2_valid_range(self):
        """测试 min_importance_for_l1l2 在 (0, 1] 范围内有效。"""
        config = ConsolidationConfig(min_importance_for_l1l2=0.6)
        assert config.min_importance_for_l1l2 == 0.6

    def test_min_importance_for_l1l2_boundary_1(self):
        """测试 min_importance_for_l1l2 边界值 1 有效。"""
        config = ConsolidationConfig(min_importance_for_l1l2=1.0)
        assert config.min_importance_for_l1l2 == 1.0

    def test_min_importance_for_l1l2_invalid_0(self):
        """测试 min_importance_for_l1l2 等于 0 抛出 ValueError。"""
        with pytest.raises(ValueError, match="min_importance_for_l1l2"):
            ConsolidationConfig(min_importance_for_l1l2=0.0)

    def test_min_importance_for_l1l2_invalid_negative(self):
        """测试 min_importance_for_l1l2 小于 0 抛出 ValueError。"""
        with pytest.raises(ValueError, match="min_importance_for_l1l2"):
            ConsolidationConfig(min_importance_for_l1l2=-0.1)

    def test_min_importance_for_l1l2_invalid_greater_than_1(self):
        """测试 min_importance_for_l1l2 大于 1 抛出 ValueError。"""
        with pytest.raises(ValueError, match="min_importance_for_l1l2"):
            ConsolidationConfig(min_importance_for_l1l2=1.1)

    def test_property_upgrade_threshold_valid(self):
        """测试 property_upgrade_threshold >= 1 有效。"""
        config = ConsolidationConfig(property_upgrade_threshold=10)
        assert config.property_upgrade_threshold == 10

    def test_property_upgrade_threshold_boundary_1(self):
        """测试 property_upgrade_threshold 边界值 1 有效。"""
        config = ConsolidationConfig(property_upgrade_threshold=1)
        assert config.property_upgrade_threshold == 1

    def test_property_upgrade_threshold_invalid_0(self):
        """测试 property_upgrade_threshold 等于 0 抛出 ValueError。"""
        with pytest.raises(ValueError, match="property_upgrade_threshold"):
            ConsolidationConfig(property_upgrade_threshold=0)

    def test_property_upgrade_threshold_invalid_negative(self):
        """测试 property_upgrade_threshold 小于 0 抛出 ValueError。"""
        with pytest.raises(ValueError, match="property_upgrade_threshold"):
            ConsolidationConfig(property_upgrade_threshold=-1)
