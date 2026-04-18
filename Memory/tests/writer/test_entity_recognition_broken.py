"""测试实体识别Broken State（Phase 15：实体识别重设计）。

验证当前实现的三个关键问题：
1. 实体识别功能语义不清晰（改名但功能未变）
2. 信息实体创建逻辑混乱（信息应该是属性，不是实体）
3. 与Phase 14.1设计不一致（应该提取"张三"，不是"张三想学Python"）

所有测试标记为SKIPPED，因为功能尚未修复。
"""

import pytest
from Memory.writer.tasks.entity_task import extract_information_and_create_edges
from Memory.llm.factory import LLMFactory
from Memory.embedding.model import embedding_service
from Memory.storage.entity_store import entity_store
from Memory.storage.cross_edge_store import cross_edge_store
from Memory.storage.database import db_manager


@pytest.fixture(scope="module")
def setup_database():
    """初始化测试数据库。"""
    if not db_manager.initialized:
        db_manager.initialize()
    yield
    # 清理测试数据
    # (可选：清理测试创建的entities和cross_edges)


@pytest.fixture
def sample_dialogue():
    """示例对话（包含张三的多个信息）。"""
    return """
    张三：你好
    AI：你好呀，有什么可以帮助你的吗？
    张三：我想学Python
    AI：好的，Python是很好的语言
    张三：我喜欢吃苹果
    AI：苹果确实很健康
    """


@pytest.mark.skip(reason="ISSUE-1: 实体识别功能语义不清晰 - 函数名是extract_information但实际仍做实体识别")
def test_extract_information_should_extract_person_entities_not_information_entities(
    sample_dialogue, setup_database
):
    """测试：extract_information应该提取"张三"实体，不是"张三想学Python"实体。

    当前行为（BROKEN）:
    - 创建实体：name="张三想学Python", type="learning_topic"
    - 创建实体：name="我喜欢吃苹果", type="food_preference"

    期望行为（FIXED）:
    - 创建实体：name="张三", type="person"
    - 添加属性：properties["knowledge"] = ["想学Python"]
    - 添加属性：properties["preferences"] = ["喜欢吃苹果"]
    """
    # Arrange
    experience_id = "exp_20260409_test_001"
    llm_client = LLMFactory.create_client()

    # Act
    entity_ids = extract_information_and_create_edges(
        experience_id=experience_id,
        dialogue=sample_dialogue,
        llm_client=llm_client,
        embedding_service=embedding_service,
        entity_store=entity_store,
        cross_edge_store=cross_edge_store,
    )

    # Assert (当前会fail，因为创建的是信息实体不是人实体)
    # 应该找到"张三"实体
    # zhang_san_entity = entity_store.get_by_name("张三")
    # assert zhang_san_entity is not None
    # assert zhang_san_entity.type == "person"
    #
    # 应该有属性记录"想学Python"和"喜欢吃苹果"
    # assert "想学Python" in zhang_san_entity.properties.get("knowledge", [])
    # assert "喜欢吃苹果" in zhang_san_entity.properties.get("preferences", [])
    pytest.skip("Broken: 当前创建信息实体，不创建人实体")


@pytest.mark.skip(reason="ISSUE-2: 信息被当作实体创建，应该作为实体属性")
def test_information_should_be_entity_properties_not_separate_entities(
    sample_dialogue, setup_database
):
    """测试：信息应该是实体的属性，不是独立的实体。

    当前行为（BROKEN）:
    - Entity 1: name="张三想学Python", type="learning_topic"
    - Entity 2: name="我喜欢吃苹果", type="food_preference"

    期望行为（FIXED）:
    - Entity: name="张三", type="person"
    - Properties: {"knowledge": ["想学Python"], "preferences": ["喜欢吃苹果"]}
    """
    # Arrange
    experience_id = "exp_20260409_test_002"
    llm_client = LLMFactory.create_client()

    # Act
    entity_ids = extract_information_and_create_edges(
        experience_id=experience_id,
        dialogue=sample_dialogue,
        llm_client=llm_client,
        embedding_service=embedding_service,
        entity_store=entity_store,
        cross_edge_store=cross_edge_store,
    )

    # Assert (当前会fail)
    # 应该只有1个实体（张三），不是3个实体（张三+两个信息）
    # assert len(entity_ids) == 1
    #
    # zhang_san = entity_store.get_by_name("张三")
    # assert "想学Python" in zhang_san.properties.get("knowledge", [])
    pytest.skip("Broken: 信息被当作实体，不是属性")


@pytest.mark.skip(reason="ISSUE-3: 函数名与实际功能不匹配")
def test_function_name_should_match_actual_behavior(
    sample_dialogue, setup_database
):
    """测试：函数名应该反映实际行为。

    当前状态（BROKEN）:
    - 函数名：extract_information_and_create_edges
    - 实际行为：创建信息实体
    - 问题：语义混淆（"提取信息"vs"创建实体"）

    期望状态（FIXED）:
    - 选项A：改函数名为recognize_entities_and_extract_properties
    - 选项B：改函数名为extract_information_for_entities
    - 选项C：重设计整个流程（分离实体识别和信息提取）
    """
    # 这个测试主要用于文档化问题，不需要实际断言
    pytest.skip("Design issue: 需要决策函数语义")
