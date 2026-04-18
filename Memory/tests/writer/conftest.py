"""写入层测试配置。

提供共享fixtures和测试工具。
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, MagicMock
from datetime import datetime

import numpy as np


@pytest.fixture
def temp_db_dir():
    """临时数据库目录。

    每个测试使用独立的数据库，测试结束后清理。
    """
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    shutil.rmtree(temp_dir)


@pytest.fixture
def mock_llm_client():
    """模拟LLM客户端。

    避免真实LLM调用，返回预设响应。
    """
    client = Mock()

    # L0摘要生成响应
    client.call_with_retry.side_effect = [
        # L0摘要
        "和朋友爬山看到美景，心情舒畅",
        # 实体识别
        '{"entities": [{"name": "张三", "type": "person", "is_new": true, "relation_to_self": "朋友", "confidence": 0.9}]}',
        # 情感分析
        '{"category": "joy", "intensity": 0.8, "valence": 0.7, "arousal": 0.6, "target": "爬山"}',
    ]

    return client


@pytest.fixture
def mock_embedding_service():
    """模拟Embedding服务。

    返回固定维度的随机向量。
    """
    service = Mock()

    def mock_encode(text: str):
        # 返回768维随机向量
        return np.random.rand(768).astype(np.float32)

    service.encode.side_effect = mock_encode
    return service


@pytest.fixture
def mock_vector_store():
    """模拟向量存储。

    模拟ChromaDB查询结果。
    """
    store = Mock()

    # 模拟query_entity返回空结果（无相似实体）
    store.query_entity.return_value = {"ids": [[]], "distances": [[]], "metadatas": [[]]}

    return store


@pytest.fixture
def sample_experience_id():
    """示例体验节点ID。"""
    return "exp_20260331_120000"


@pytest.fixture
def sample_raw_text():
    """示例原始文本。"""
    return "今天和张三去爬山，风景很美，心情很舒畅"


@pytest.fixture
def sample_emotion_snapshot():
    """示例情感快照。"""
    from Memory.writer.tasks.emotion_task import EmotionSnapshot

    return EmotionSnapshot(category="joy", intensity=0.8, valence=0.7, arousal=0.6, target="爬山")
