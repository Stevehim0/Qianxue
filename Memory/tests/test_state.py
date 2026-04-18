"""状态层测试套件。

测试状态层的接口定义、默认实现和占位方法。
"""

import pytest

from Memory.state import MoodState, EnergyState, StateManager, StateUpdater, StateConstraints
from Memory.state.manager import DefaultStateManager
from Memory.state.updater import DefaultStateUpdater
from Memory.state.constraints import DefaultStateConstraints
from Memory.tests.conftest import mock_emotion_snapshot

# ========== 数据类测试 ==========


def test_mood_state_valid():
    """测试MoodState有效值。"""
    mood = MoodState(valence=0.5, arousal=0.6, label="愉快")

    assert mood.valence == 0.5
    assert mood.arousal == 0.6
    assert mood.label == "愉快"


def test_mood_state_invalid_valence():
    """测试MoodState无效valence值。"""
    with pytest.raises(ValueError, match="valence必须在"):
        MoodState(valence=1.5, arousal=0.5, label="无效")


def test_mood_state_invalid_arousal():
    """测试MoodState无效arousal值。"""
    with pytest.raises(ValueError, match="arousal必须在"):
        MoodState(valence=0.0, arousal=1.5, label="无效")


def test_energy_state_valid():
    """测试EnergyState有效值。"""
    energy = EnergyState(value=0.7, label="正常")

    assert energy.value == 0.7
    assert energy.label == "正常"


def test_energy_state_invalid_value():
    """测试EnergyState无效值。"""
    with pytest.raises(ValueError, match="value必须在"):
        EnergyState(value=1.5, label="无效")


# ========== StateManager测试 ==========


def test_default_state_manager_get_mood():
    """测试获取情绪状态。"""
    manager = DefaultStateManager()
    mood = manager.get_mood()

    assert isinstance(mood, MoodState)
    assert mood.valence == 0.0
    assert mood.arousal == 0.3
    assert mood.label == "平静"


def test_default_state_manager_get_energy():
    """测试获取精力状态。"""
    manager = DefaultStateManager()
    energy = manager.get_energy()

    assert isinstance(energy, EnergyState)
    assert energy.value == 0.5
    assert energy.label == "正常"


def test_default_state_manager_get_focus():
    """测试获取注意力焦点。"""
    manager = DefaultStateManager()
    focus = manager.get_focus()

    assert focus is None


def test_default_state_manager_get_confidence():
    """测试获取信心值。"""
    manager = DefaultStateManager()
    confidence = manager.get_confidence()

    assert confidence == 0.5


def test_default_state_manager_format_state_prompt():
    """测试格式化状态为prompt。"""
    manager = DefaultStateManager()
    prompt = manager.format_state_prompt()

    assert isinstance(prompt, str)
    assert len(prompt) > 0
    assert "[当前状态]" in prompt
    assert "[状态影响指导]" in prompt
    assert "情绪：平静" in prompt
    assert "精力：正常" in prompt
    assert "注意力：无" in prompt
    assert "信心" in prompt


def test_default_state_manager_confidence_label():
    """测试信心值标签生成。"""
    manager = DefaultStateManager()

    # 测试不同的信心值标签
    assert manager._confidence_label(0.9) == "自信"
    assert manager._confidence_label(0.6) == "正常"
    assert manager._confidence_label(0.4) == "犹豫"
    assert manager._confidence_label(0.2) == "迷茫"


# ========== StateUpdater测试 ==========


def test_default_state_updater_trigger_immediate(mock_emotion_snapshot):
    """测试即时更新触发（占位实现）。"""
    updater = DefaultStateUpdater()

    # 占位实现，可调用但不做任何事
    updater.trigger_immediate_update(mock_emotion_snapshot)

    # 不会抛出异常
    assert True


def test_default_state_updater_trigger_timed():
    """测试定时更新触发（占位实现）。"""
    updater = DefaultStateUpdater()

    # 占位实现，可调用但不做任何事
    updater.trigger_timed_update()

    # 不会抛出异常
    assert True


def test_default_state_updater_should_trigger_immediate(mock_emotion_snapshot):
    """测试即时更新判断（占位实现）。"""
    updater = DefaultStateUpdater()

    # Phase 4: 占位实现，总是返回False
    result = updater._should_trigger_immediate(mock_emotion_snapshot)

    assert result is False


def test_default_state_updater_experience_driven(mock_emotion_snapshot):
    """测试体验驱动更新（占位实现）。"""
    updater = DefaultStateUpdater()

    # 占位实现，可调用但不做任何事
    updater._experience_driven_update(mock_emotion_snapshot)

    # 不会抛出异常
    assert True


def test_default_state_updater_baseline_regression():
    """测试基线回归更新（占位实现）。"""
    updater = DefaultStateUpdater()

    # 占位实现，可调用但不做任何事
    updater._baseline_regression_update()

    # 不会抛出异常
    assert True


def test_default_state_updater_reset_timer():
    """测试重置定时器（占位实现）。"""
    updater = DefaultStateUpdater()

    # 占位实现，可调用但不做任何事
    updater._reset_timer()

    # 不会抛出异常
    assert True


# ========== StateConstraints测试 ==========


def test_default_state_constraints_check_mood_bounds():
    """测试情绪约束检查（占位实现）。"""
    constraints = DefaultStateConstraints()
    identity = None  # core层已移除，constraints为占位实现

    # Phase 4: 占位实现，返回原值
    valence, arousal = constraints.check_mood_bounds(0.8, 0.9, identity)

    assert valence == 0.8
    assert arousal == 0.9


def test_default_state_constraints_check_energy_bounds():
    """测试精力约束检查（占位实现）。"""
    constraints = DefaultStateConstraints()
    identity = None  # core层已移除，constraints为占位实现

    # Phase 4: 占位实现，返回原值
    energy = constraints.check_energy_bounds(0.7, identity)

    assert energy == 0.7


def test_default_state_constraints_check_confidence_bounds():
    """测试信心约束检查（占位实现）。"""
    constraints = DefaultStateConstraints()
    identity = None  # core层已移除，constraints为占位实现

    # Phase 4: 占位实现，返回原值
    confidence = constraints.check_confidence_bounds(0.6, identity)

    assert confidence == 0.6


def test_default_state_constraints_derive_arousal_upper_bound():
    """测试推导arousal上限（占位实现）。"""
    constraints = DefaultStateConstraints()
    identity = None  # core层已移除，constraints为占位实现

    # Phase 4: 占位实现，返回1.0（无约束）
    upper_bound = constraints._derive_arousal_upper_bound(identity)

    assert upper_bound == 1.0


def test_default_state_constraints_derive_confidence_lower_bound():
    """测试推导confidence下限（占位实现）。"""
    constraints = DefaultStateConstraints()
    identity = None  # core层已移除，constraints为占位实现

    # Phase 4: 占位实现，返回0.0（无约束）
    lower_bound = constraints._derive_confidence_lower_bound(identity)

    assert lower_bound == 0.0


# ========== 集成测试 ==========


def test_state_layer_full_workflow(mock_emotion_snapshot):
    """测试状态层完整工作流。"""
    # 1. 创建StateManager并读取状态
    manager = DefaultStateManager()
    mood = manager.get_mood()
    energy = manager.get_energy()
    focus = manager.get_focus()
    confidence = manager.get_confidence()

    assert isinstance(mood, MoodState)
    assert isinstance(energy, EnergyState)
    assert focus is None
    assert isinstance(confidence, float)

    # 2. 格式化状态为prompt
    prompt = manager.format_state_prompt()
    assert len(prompt) > 0
    assert "[当前状态]" in prompt

    # 3. 创建StateUpdater并测试触发
    updater = DefaultStateUpdater()
    updater.trigger_immediate_update(mock_emotion_snapshot)
    updater.trigger_timed_update()

    # 4. 创建StateConstraints并测试约束检查
    constraints = DefaultStateConstraints()
    identity = None  # core层已移除，constraints为占位实现

    val, arousal = constraints.check_mood_bounds(0.8, 0.9, identity)
    assert val == 0.8  # 占位实现，不做约束


def test_protocol_interface_compliance():
    """测试Protocol接口合规性。"""
    # DefaultStateManager应符合StateManager Protocol
    manager: StateManager = DefaultStateManager()

    # 所有Protocol方法都应该可用
    assert hasattr(manager, "get_mood")
    assert hasattr(manager, "get_energy")
    assert hasattr(manager, "get_focus")
    assert hasattr(manager, "get_confidence")
    assert hasattr(manager, "format_state_prompt")

    # DefaultStateUpdater应符合StateUpdater Protocol
    updater: StateUpdater = DefaultStateUpdater()

    assert hasattr(updater, "trigger_immediate_update")
    assert hasattr(updater, "trigger_timed_update")

    # DefaultStateConstraints应符合StateConstraints Protocol
    constraints: StateConstraints = DefaultStateConstraints()

    assert hasattr(constraints, "check_mood_bounds")
    assert hasattr(constraints, "check_energy_bounds")
    assert hasattr(constraints, "check_confidence_bounds")
