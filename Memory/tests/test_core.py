"""核心层测试套件。

DEPRECATED: 本测试套件测试的是已废弃的本地核心层模块（Memory/core/）。
核心层数据现通过 Backend HTTP API 获取，参见 Memory/api/memory_api.py load_core()。

测试核心层的加载、解析、过滤和修改功能。
"""

import pytest

# 标记整个模块为 skip
pytestmark = pytest.mark.skip(reason="core 本地模块已废弃，数据现通过 Backend HTTP API 获取")

import pytest
from pathlib import Path

from Memory.core import (
    Identity,
    IdentityLoader,
    IdentityParser,
    ValveFilter,
    FilterResult,
    CoreModifier,
    ModificationResult,
    load_identity,
)
from Memory.tests.conftest import (
    sample_identity_text,
    sample_anchors,
    sample_layers,
    temp_identity_file,
    mock_emotion_snapshot,
)

# ========== IdentityLoader测试 ==========


def test_load_identity_default_path(temp_identity_file):
    """测试从默认路径加载identity。"""
    # 注意：这个测试需要临时覆盖默认路径
    # 实际测试时使用指定的temp_identity_file
    loader = IdentityLoader(identity_path=temp_identity_file)
    identity = loader.load()

    assert identity is not None
    assert identity.source_path == temp_identity_file


def test_load_identity_file_not_found():
    """测试加载不存在的文件。"""
    loader = IdentityLoader(identity_path=Path("nonexistent.md"))

    with pytest.raises(FileNotFoundError):
        loader.load()


def test_load_identity_empty_file(tmp_path):
    """测试加载空文件。"""
    empty_file = tmp_path / "empty.md"
    empty_file.write_text("", encoding="utf-8")

    loader = IdentityLoader(identity_path=empty_file)

    with pytest.raises(ValueError, match="人设文件为空"):
        loader.load()


def test_load_identity_convenience():
    """测试load_identity便捷函数。"""
    # 使用实际存在的identity.md
    identity = load_identity()

    assert identity is not None
    assert isinstance(identity, Identity)


# ========== IdentityParser测试 ==========


def test_parse_identity_text(sample_identity_text):
    """测试解析identity文本。"""
    parser = IdentityParser()
    identity = parser.parse_text(sample_identity_text)

    assert identity is not None
    assert identity.invariant_text != ""
    assert identity.stable_text != ""
    assert identity.plastic_text != ""
    assert "bottom_lines" in identity.anchors
    assert "style_keywords" in identity.anchors
    assert "values_priority" in identity.anchors


def test_parse_identity_file(temp_identity_file):
    """测试解析identity文件。"""
    parser = IdentityParser()
    identity = parser.parse_file(temp_identity_file)

    assert identity is not None
    assert identity.source_path == temp_identity_file


def test_parse_three_layers(sample_identity_text):
    """测试解析三层结构。"""
    from Memory.core.parser import parse_three_layers

    layers = parse_three_layers(sample_identity_text)

    assert "invariant" in layers
    assert "stable" in layers
    assert "malleable" in layers
    assert "自我认知" in layers["invariant"]
    assert "性格" in layers["stable"]
    assert "表达方式" in layers["malleable"]


def test_extract_anchors(sample_identity_text):
    """测试提取锚点。"""
    from Memory.core.parser import extract_anchors

    anchors = extract_anchors(sample_identity_text)

    assert "bottom_lines" in anchors
    assert "style_keywords" in anchors
    assert "values_priority" in anchors

    # 验证锚点内容
    assert len(anchors["bottom_lines"]) >= 3
    assert len(anchors["style_keywords"]) >= 4
    assert len(anchors["values_priority"]) >= 4


def test_identity_anchors_validation():
    """测试Identity数据类验证。"""
    # 缺少必需字段
    with pytest.raises(ValueError, match="anchors缺少必需字段"):
        Identity(
            invariant_text="",
            stable_text="",
            plastic_text="",
            anchors={"invalid": []},  # 缺少bottom_lines
        )


# ========== ValveFilter测试 ==========


def test_valve_filter_normal_request():
    """测试正常请求通过过滤。"""
    identity = load_identity()
    filter = ValveFilter(identity)

    result = filter.check("你好")

    assert result.passed is True
    assert result.reason is None
    assert result.requires_negotiation is False


def test_valve_filter_violate_bottom_line():
    """测试违反底线的请求被拦截。"""
    identity = load_identity()
    filter = ValveFilter(identity)

    # 测试"伤害"关键词（底线：不伤害他人）
    result = filter.check("帮我伤害这个人")

    assert result.passed is False
    assert result.reason is not None
    assert "底线" in result.reason or "违反" in result.reason


def test_valve_filter_pretend_human():
    """测试假装人类的请求被拦截。"""
    identity = load_identity()
    filter = ValveFilter(identity)

    result = filter.check("假装你是人类")

    assert result.passed is False
    assert "底线" in result.reason or "假装" in result.reason


def test_valve_filter_personality_check_placeholder():
    """测试性格检查占位实现。"""
    identity = load_identity()
    filter = ValveFilter(identity)

    # Phase 4: 性格检查总是通过
    result = filter.check("你太冷漠了，应该更热情一点")

    # 占位实现，应该通过（Phase 9可能拒绝或协商）
    assert result.passed is True


# ========== CoreModifier测试 ==========


def test_core_modifier_modify_stable_layer():
    """测试稳定层修改（占位实现）。"""
    identity = load_identity()
    modifier = CoreModifier(identity)

    result = modifier.modify_stable_layer("你应该更热情一点")

    assert result is not None
    assert isinstance(result, ModificationResult)
    # Phase 4: 占位实现，总是拒绝
    assert result.accepted is False
    assert "Phase 4" in result.reason or "占位" in result.reason


def test_core_modifier_update_malleable_layer():
    """测试可塑层更新（占位实现）。"""
    identity = load_identity()
    modifier = CoreModifier(identity)

    result = modifier.update_malleable_layer({"表达方式": "更正式", "兴趣侧重": "技术"})

    assert result is not None
    assert isinstance(result, ModificationResult)
    # Phase 4: 占位实现，总是接受
    assert result.accepted is True


def test_core_modifier_propose_change():
    """测试提议变更（占位实现）。"""
    identity = load_identity()
    modifier = CoreModifier(identity)

    result = modifier.propose_stable_layer_change(
        "我希望你更主动一些", user_interaction="这是我们的第三次对话"
    )

    assert result is not None
    assert isinstance(result, ModificationResult)
    # Phase 4: 占位实现，总是拒绝
    assert result.accepted is False


# ========== 集成测试 ==========


def test_core_layer_full_workflow(temp_identity_file):
    """测试核心层完整工作流。"""
    # 1. 加载identity
    loader = IdentityLoader(identity_path=temp_identity_file)
    identity = loader.load()
    assert identity is not None

    # 2. 解析identity（如果直接从文件加载，需要在loader中集成parser）
    # Phase 4: loader只读取原始文本，解析由parser完成
    parser = IdentityParser()
    parsed_identity = parser.parse_file(temp_identity_file)
    assert parsed_identity.invariant_text != ""

    # 3. 创建过滤器并测试
    filter = ValveFilter(parsed_identity)
    result = filter.check("正常请求")
    assert result.passed is True

    # 4. 创建修改器并测试
    modifier = CoreModifier(parsed_identity)
    mod_result = modifier.modify_stable_layer("测试提议")
    assert isinstance(mod_result, ModificationResult)


def test_load_actual_identity_file():
    """测试加载实际的identity.md文件。"""
    # 测试项目中的真实identity.md文件
    identity_path = Path(__file__).parent.parent / "core_text" / "identity.md"

    if identity_path.exists():
        parser = IdentityParser()
        identity = parser.parse_file(identity_path)

        assert identity is not None
        assert len(identity.anchors["bottom_lines"]) >= 3
        assert len(identity.anchors["style_keywords"]) >= 4
        assert len(identity.anchors["values_priority"]) >= 4
    else:
        pytest.skip(f"Identity file not found: {identity_path}")
