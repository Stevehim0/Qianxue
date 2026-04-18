"""测试信息提取任务（Phase 14.1：替代实体识别，Phase 15：待重设计）。

验证：
1. dialogue参数正确传递
2. LLM提取信息（知识/事实/意图）
3. 创建信息实体（info_content作为name）
4. 创建跨层边（context="contains_information"）

注意：这是Phase 14.1创建的测试，用于验证信息提取功能。
Phase 15将重设计此功能，区分"实体识别"和"信息提取"。
"""

import pytest
from Memory.writer.tasks.entity_task import extract_information_and_create_edges
from Memory.llm.factory import LLMFactory
from Memory.embedding import embedding_service
from Memory.storage.entity_store import entity_store
from Memory.storage.cross_edge_store import cross_edge_store


@pytest.fixture
def mock_llm_client(monkeypatch):
    """Mock LLM客户端，返回预设信息提取结果。"""
    class MockLLM:
        def call_with_retry(self, prompt, response_format, temperature, max_tokens):
            return {
                "information": [
                    {
                        "type": "learning_topic",
                        "content": "张三想学Python",
                        "source": "张三",
                        "confidence": 0.9
                    },
                    {
                        "type": "food_preference",
                        "content": "苹果是甜的",
                        "source": "张三",
                        "confidence": 0.8
                    }
                ]
            }

    # 修正monkeypatch路径，使用正确的模块路径
    monkeypatch.setattr("Memory.llm.factory.LLMFactory.create_client", lambda: MockLLM())
    return MockLLM()


@pytest.fixture
def sample_dialogue():
    """示例长对话。"""
    return """
    张三：我想学Python
    AI：好的，Python是一门很实用的语言
    张三：对了，苹果是甜的
    AI：是的，大多数苹果都是甜的
    """


@pytest.mark.skip(reason="Phase 15: 信息提取功能需要重设计，当前实现将信息作为实体创建")
def test_extract_information_uses_dialogue_parameter(sample_dialogue, mock_llm_client):
    """测试：extract_information_and_create_edges使用dialogue参数。

    注意：Phase 15将重设计此功能，区分"实体识别"和"信息提取"。
    当前实现创建信息实体，未来应该将信息作为实体属性。
    """
    # Arrange
    experience_id = "exp_test_001"

    # Act
    entity_ids = extract_information_and_create_edges(
        experience_id=experience_id,
        dialogue=sample_dialogue,
        llm_client=mock_llm_client,
        embedding_service=embedding_service,
        entity_store=entity_store,
        cross_edge_store=cross_edge_store,
    )

    # Assert
    # 当前实现：创建2个信息实体
    # Phase 15修复后：应该创建1个人实体，信息作为属性
    assert len(entity_ids) == 2  # 两条信息


@pytest.mark.skip(reason="Phase 15: 信息提取功能需要重设计")
def test_extract_information_creates_info_entities(sample_dialogue, mock_llm_client):
    """测试：创建信息实体，info_content作为name。

    当前行为：创建信息实体（如"张三想学Python"）
    Phase 15修复后：应该创建人实体（如"张三"），信息作为属性
    """
    # Arrange
    experience_id = "exp_test_002"

    # Act
    entity_ids = extract_information_and_create_edges(
        experience_id=experience_id,
        dialogue=sample_dialogue,
        llm_client=mock_llm_client,
        embedding_service=embedding_service,
        entity_store=entity_store,
        cross_edge_store=cross_edge_store,
    )

    # Assert
    # 验证实体name是信息内容
    for entity_id in entity_ids:
        entity = entity_store.get(entity_id)
        assert entity is not None
        # name应该是"张三想学Python"或"苹果是甜的"
        assert entity.name in ["张三想学Python", "苹果是甜的"]
        # type应该是"learning_topic"或"food_preference"
        assert entity.type in ["learning_topic", "food_preference"]
        # properties包含source和confidence
        assert "source" in entity.properties
        assert "confidence" in entity.properties


@pytest.mark.skip(reason="Phase 15: 信息提取功能需要重设计")
def test_extract_information_creates_cross_edges(sample_dialogue, mock_llm_client):
    """测试：创建跨层边，context为contains_information。"""
    # Arrange
    experience_id = "exp_test_003"

    # Act
    entity_ids = extract_information_and_create_edges(
        experience_id=experience_id,
        dialogue=sample_dialogue,
        llm_client=mock_llm_client,
        embedding_service=embedding_service,
        entity_store=entity_store,
        cross_edge_store=cross_edge_store,
    )

    # Assert
    # 验证每个信息实体都有跨层边
    for entity_id in entity_ids:
        edges = cross_edge_store.get_by_experience(experience_id)
        edge_to_entity = [e for e in edges if e.to_id == entity_id]
        assert len(edge_to_entity) == 1
        assert edge_to_entity[0].context == "contains_information"


@pytest.mark.skip(reason="Phase 15: 信息提取功能需要重设计")
def test_extract_information_custom_types(sample_dialogue, mock_llm_client):
    """测试：LLM自定义信息类型。

    当前行为：LLM自定义信息类型（如"learning_topic"）
    Phase 15修复后：应该使用固定实体类型（如"person"），信息作为属性
    """
    # Arrange
    experience_id = "exp_test_004"

    # Act
    entity_ids = extract_information_and_create_edges(
        experience_id=experience_id,
        dialogue=sample_dialogue,
        llm_client=mock_llm_client,
        embedding_service=embedding_service,
        entity_store=entity_store,
        cross_edge_store=cross_edge_store,
    )

    # Assert
    # 验证type是LLM自定义的（不预设person/location等）
    for entity_id in entity_ids:
        entity = entity_store.get(entity_id)
        assert entity.type in ["learning_topic", "food_preference"]
        # 不应该是旧的实体类型
        assert entity.type not in ["person", "location", "object", "concept"]
