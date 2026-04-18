"""测试L0摘要生成任务（Phase 14.1：长对话格式）。

验证：
1. dialogue参数正确传递
2. LLM生成AI第一人称视角摘要
3. 识别说话者（张三、李四等）
4. 包含AI感受或反应
"""

import pytest
from Memory.writer.tasks.l0_summary_task import generate_l0_summary
from Memory.llm.factory import LLMFactory
from Memory.embedding import embedding_service
from Memory.embedding.vector_store import vector_store
from Memory.storage.experience_store import experience_store


@pytest.fixture
def mock_llm_client(monkeypatch):
    """Mock LLM客户端，返回预设回复。"""
    class MockLLM:
        def call_with_retry(self, prompt, response_format, temperature, max_tokens):
            return "张三向我问Python的问题，我感到乐意帮助"

    monkeypatch.setattr("Memory.writer.tasks.l0_summary_task.LLMFactory.create_client", lambda: MockLLM())
    return MockLLM()


@pytest.fixture
def sample_dialogue():
    """示例长对话。"""
    return """
    张三：你好
    AI：你好呀，有什么可以帮助你的吗？
    张三：我想问一下Python的事
    AI：当然可以，你想了解什么？
    张三：主要是关于类和对象的概念
    """


def test_generate_l0_summary_uses_dialogue_parameter(sample_dialogue, mock_llm_client):
    """测试：generate_l0_summary使用dialogue参数。"""
    # Arrange
    experience_id = "exp_test_001"
    dialogue = sample_dialogue

    # Act
    l0_text = generate_l0_summary(
        experience_id=experience_id,
        dialogue=dialogue,
        llm_client=mock_llm_client,
        embedding_service=embedding_service,
        vector_store=vector_store,
        experience_store=experience_store,
    )

    # Assert
    assert l0_text is not None
    assert len(l0_text) > 0
    assert "张三" in l0_text  # 识别说话者


def test_l0_summary_first_person_perspective(sample_dialogue, mock_llm_client):
    """测试：L0摘要使用AI第一人称视角。

    验证：
    - 包含"我"字（第一人称）
    - 包含感受或反应（乐意帮助）
    - 不是客观描述（如"用户询问了XX"）
    """
    # Arrange
    experience_id = "exp_test_002"

    # Act
    l0_text = generate_l0_summary(
        experience_id=experience_id,
        dialogue=sample_dialogue,
        llm_client=mock_llm_client,
        embedding_service=embedding_service,
        vector_store=vector_store,
        experience_store=experience_store,
    )

    # Assert
    assert "我" in l0_text  # 第一人称
    assert "张三" in l0_text  # 识别说话者
    # 不应该出现"用户询问"这类客观描述
    assert "用户询问" not in l0_text
    assert "AI回答" not in l0_text


def test_l0_summary_includes_ai_feeling(sample_dialogue, mock_llm_client):
    """测试：L0摘要包含AI感受或反应。"""
    # Arrange
    experience_id = "exp_test_003"

    # Act
    l0_text = generate_l0_summary(
        experience_id=experience_id,
        dialogue=sample_dialogue,
        llm_client=mock_llm_client,
        embedding_service=embedding_service,
        vector_store=vector_store,
        experience_store=experience_store,
    )

    # Assert
    # 示例回复包含"乐意帮助"，验证AI感受
    assert "乐意" in l0_text or "帮助" in l0_text or "感到" in l0_text


def test_l0_summary_stored_in_database(sample_dialogue, mock_llm_client):
    """测试：L0摘要存储到数据库。"""
    # Arrange
    experience_id = "exp_test_004"

    # Act
    l0_text = generate_l0_summary(
        experience_id=experience_id,
        dialogue=sample_dialogue,
        llm_client=mock_llm_client,
        embedding_service=embedding_service,
        vector_store=vector_store,
        experience_store=experience_store,
    )

    # Assert
    exp = experience_store.get(experience_id)
    assert exp is not None
    assert exp.L0_text == l0_text
    assert exp.L0_embedding is not None
    assert exp.L0_embedding.shape == (768,)  # bge-base-zh维度


def test_l0_summary_stored_in_chromadb(sample_dialogue, mock_llm_client):
    """测试：L0向量存储到ChromaDB。"""
    # Arrange
    experience_id = "exp_test_005"

    # Act
    l0_text = generate_l0_summary(
        experience_id=experience_id,
        dialogue=sample_dialogue,
        llm_client=mock_llm_client,
        embedding_service=embedding_service,
        vector_store=vector_store,
        experience_store=experience_store,
    )

    # Assert
    results = vector_store.query_experience(
        query_embedding=embedding_service.encode(l0_text).tolist(),
        top_k=1
    )
    assert len(results["ids"][0]) > 0
    assert experience_id in results["ids"][0]
