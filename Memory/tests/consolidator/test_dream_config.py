"""
测试DreamConfig配置类

Tests:
- DreamConfig dataclass exists with all required fields
- Default values match CONTEXT.md decisions (dream_batch_size=20, etc.)
- Field validation works (batch_size > 0, timeouts >= 60)
- Settings class has dream property returning DreamConfig instance
- Settings.get_summary() includes dream configuration
- Invalid values raise ValueError in __post_init__
"""

import pytest
from Memory.config.settings import DreamConfig, Settings


def test_dream_config_dataclass_exists():
    """验证DreamConfig数据类存在"""
    config = DreamConfig()

    # Verify all required fields exist
    assert hasattr(config, "reorganize_batch_size")
    assert hasattr(config, "emotion_batch_size")
    assert hasattr(config, "distort_batch_size")
    assert hasattr(config, "simulate_batch_size")
    assert hasattr(config, "important_ratio")
    assert hasattr(config, "random_ratio")
    assert hasattr(config, "task_timeout_seconds")
    assert hasattr(config, "memory_timeout_seconds")
    assert hasattr(config, "dream_confidence")
    assert hasattr(config, "dream_importance_multiplier")
    assert hasattr(config, "allow_l3_modification")
    assert hasattr(config, "audit_log_path")


def test_dream_config_default_values():
    """验证默认值匹配CONTEXT.md决策"""
    config = DreamConfig()

    # Batch sizes (D-03: default 20)
    assert config.reorganize_batch_size == 20
    assert config.emotion_batch_size == 20
    assert config.distort_batch_size == 20
    assert config.simulate_batch_size == 20

    # Sampling ratios (D-02: 40% important + 60% random)
    assert config.important_ratio == 0.4
    assert config.random_ratio == 0.6

    # Timeouts (D-08, D-14: task 30min, memory 5min)
    assert config.task_timeout_seconds == 1800
    assert config.memory_timeout_seconds == 300

    # Dream node markers (D-09)
    assert config.dream_confidence == 0.3
    assert config.dream_importance_multiplier == 0.5

    # L3 protection (D-15)
    assert config.allow_l3_modification is False

    # Audit log path (D-20)
    assert "dream_audit.log" in config.audit_log_path


def test_dream_config_validation_batch_size_positive():
    """验证批量大小必须大于0"""
    with pytest.raises(ValueError, match="batch_size must be > 0"):
        DreamConfig(reorganize_batch_size=0)

    with pytest.raises(ValueError, match="batch_size must be > 0"):
        DreamConfig(emotion_batch_size=-1)


def test_dream_config_validation_sampling_ratios_sum_to_one():
    """验证采样比例总和必须为1.0"""
    with pytest.raises(ValueError, match="Sampling ratios must sum to 1.0"):
        DreamConfig(important_ratio=0.5, random_ratio=0.3)  # Sum = 0.8

    with pytest.raises(ValueError, match="Sampling ratios must sum to 1.0"):
        DreamConfig(important_ratio=0.7, random_ratio=0.5)  # Sum = 1.2


def test_dream_config_validation_timeouts_minimum():
    """验证超时必须>=60秒"""
    with pytest.raises(ValueError, match="task_timeout_seconds must be >= 60"):
        DreamConfig(task_timeout_seconds=30)

    with pytest.raises(ValueError, match="memory_timeout_seconds must be >= 60"):
        DreamConfig(memory_timeout_seconds=30)


def test_dream_config_validation_confidence_range():
    """验证置信度和重要性系数范围在[0, 1]"""
    with pytest.raises(ValueError, match="dream_confidence must be between 0 and 1"):
        DreamConfig(dream_confidence=1.5)

    with pytest.raises(ValueError, match="dream_confidence must be between 0 and 1"):
        DreamConfig(dream_confidence=-0.1)

    with pytest.raises(ValueError, match="dream_importance_multiplier must be between 0 and 1"):
        DreamConfig(dream_importance_multiplier=1.5)


def test_settings_has_dream_property():
    """验证Settings类有dream属性返回DreamConfig实例"""
    settings = Settings()

    # Verify dream property exists
    assert hasattr(settings, "dream")

    # Verify it returns DreamConfig instance
    assert isinstance(settings.dream, DreamConfig)


def test_settings_get_summary_includes_dream_config():
    """验证Settings.get_summary()包含dream配置"""
    settings = Settings()
    summary = settings.get_summary()

    # Verify dream section exists
    assert "dream" in summary

    # Verify key fields are included
    dream_summary = summary["dream"]
    assert "reorganize_batch_size" in dream_summary
    assert "emotion_batch_size" in dream_summary
    assert "distort_batch_size" in dream_summary
    assert "simulate_batch_size" in dream_summary
    assert "important_ratio" in dream_summary
    assert "task_timeout_seconds" in dream_summary


def test_dream_config_custom_values():
    """验证可以自定义DreamConfig值"""
    config = DreamConfig(
        reorganize_batch_size=10,
        emotion_batch_size=15,
        important_ratio=0.5,
        random_ratio=0.5,
        task_timeout_seconds=3600,
    )

    assert config.reorganize_batch_size == 10
    assert config.emotion_batch_size == 15
    assert config.important_ratio == 0.5
    assert config.random_ratio == 0.5
    assert config.task_timeout_seconds == 3600
