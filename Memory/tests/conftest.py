"""Pytest配置和fixtures。

本模块提供测试所需的fixtures：
- memory_db: 内存数据库fixture（存储层测试）
- test_data: 测试数据fixture（存储层测试）
- db_manager: 测试用DatabaseManager实例（存储层测试）
- mock_qianwen_client: Mock千问客户端fixture（LLM测试）
- mock_deepseek_client: Mock DeepSeek客户端fixture（LLM测试）
- tmp_log_dir: 临时日志目录fixture（LLM测试）
"""

import sqlite3
import pytest
import numpy as np
import tempfile
from pathlib import Path
from typing import Dict, Any, List
from unittest.mock import Mock, MagicMock
from datetime import datetime, timedelta

from Memory.storage.database import DatabaseManager
from Memory.storage.schema import create_all_tables


@pytest.fixture(scope="function")
def memory_db():
    """创建内存数据库用于测试。

    每个测试函数使用独立的内存数据库，测试结束后自动清理。

    Yields:
        DatabaseManager实例
    """
    # 创建内存数据库连接
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row

    # 创建测试用DatabaseManager
    class TestDatabaseManager(DatabaseManager):
        """测试用DatabaseManager，使用内存数据库。"""

        def __init__(self, conn):
            self._conn = conn
            self._initialized = False

        @property
        def conn(self):
            return self._conn

        def close(self):
            # 测试中不关闭连接
            pass

        def execute_query(self, query, params=()):
            """执行查询并返回结果（用于测试）。"""
            cursor = self.conn.cursor()
            cursor.execute(query, params)
            return cursor

    db_manager = TestDatabaseManager(conn)

    # 初始化表结构（使用最新schema，包含所有字段）
    create_all_tables(db_manager)

    # 验证schema版本和表结构
    from Memory.storage.schema import get_current_schema_version

    version = get_current_schema_version(db_manager)
    print(f"Test database schema version: {version}")

    # 验证experiences表包含所有必要字段
    cursor = db_manager.execute_query("PRAGMA table_info(experiences)")
    columns = [row["name"] for row in cursor.fetchall()]
    print(f"Experiences table columns ({len(columns)}): {columns[:10]}...")

    # 确保decay_config表存在并初始化
    cursor = db_manager.execute_query("SELECT COUNT(*) as count FROM decay_config")
    count = cursor.fetchone()["count"]
    if count == 0:
        # 插入默认配置
        from datetime import datetime

        now = datetime.now().isoformat()
        defaults = {
            "half_life_days": 30.0,
            "decay_rate": 0.02,
            "min_weight": 0.1,
            "max_weight": 1.0,
        }
        for key, value in defaults.items():
            db_manager.execute_query(
                "INSERT INTO decay_config (key, value, description, updated_at) VALUES (?, ?, ?, ?)",
                (key, value, f"Default {key}", now),
            )
        print("Initialized decay_config with default values")

    yield db_manager

    # 清理（关闭连接，内存数据库自动删除）
    conn.close()


@pytest.fixture(scope="function")
def db_manager(memory_db):
    """db_manager fixture的别名，指向memory_db。

    为保持兼容性，某些测试使用db_manager参数名。
    """
    return memory_db


@pytest.fixture(scope="function")
def test_data():
    """创建测试数据。

    Returns:
        包含测试数据的字典
    """
    # 768维测试向量（float32）
    test_embedding = np.random.rand(768).astype(np.float32)

    return {
        "experience": {
            "id": "test_exp_001",
            "L0_text": "这是一个测试体验",
            "L3_raw": "这是完整的测试内容，包含了更多的细节和上下文信息。",
            "emotion_category": "curiosity",
            "emotion_intensity": 0.7,
            "emotion_valence": 0.5,
            "emotion_arousal": 0.6,
            "importance": 0.6,
        },
        "entity": {
            "id": "test_entity_001",
            "name": "张三",
            "type": "person",
            "properties": {"age": 30, "occupation": "工程师"},
        },
        "embedding": test_embedding,
        "entity_edge": {
            "from_id": "test_entity_001",
            "to_id": "test_entity_002",
            "relation": "朋友",
            "confidence": 0.8,
            "source_type": "direct",
        },
        "cross_edge": {
            "from_id": "test_exp_001",
            "to_id": "test_entity_001",
            "context": "在体验中提到",
            "weight": 1.0,
        },
        "profile": {
            "id": "profile_张三",
            "basic": {"name": "张三", "age": 30},
            "interaction_style": {
                "warmth": 0.7,
                "formality": 0.3,
                "humor": 0.5,
            },
            "preferences": {"topics": ["技术", "音乐"]},
        },
    }


@pytest.fixture(scope="function")
def sample_experiences(test_data):
    """创建多个测试体验节点。

    Returns:
        Experience对象列表
    """
    from Memory.storage.experience_store import Experience

    experiences = []
    for i in range(5):
        exp = Experience(
            id=f"test_exp_{i:03d}",
            L0_text=f"测试体验{i}",
            L3_raw=f"这是第{i}个测试体验的完整内容。",
            emotion_category="neutral",
            emotion_intensity=0.5,
            emotion_valence=0.0,
            emotion_arousal=0.3,
            importance=0.5,
        )
        experiences.append(exp)

    return experiences


@pytest.fixture(scope="function")
def sample_entities(test_data):
    """创建多个测试实体。

    Returns:
        Entity对象列表
    """
    from Memory.storage.entity_store import Entity

    entities = [
        Entity(
            id=f"test_entity_{i:03d}",
            name=f"实体{i}",
            type="person",
            properties={"index": i},
        )
        for i in range(5)
    ]

    return entities


# ============================================================================
# LLM测试fixtures
# ============================================================================


@pytest.fixture(scope="function")
def tmp_log_dir(tmp_path):
    """创建临时日志目录用于LLM测试。

    Args:
        tmp_path: pytest内置的临时路径fixture

    Returns:
        临时日志目录Path对象
    """
    log_dir = tmp_path / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


@pytest.fixture(scope="function")
def mock_qianwen_response():
    """创建Mock千问API响应。

    Returns:
        Mock响应对象
    """
    mock_resp = Mock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"output": {"text": '{"result": "success"}'}}
    return mock_resp


@pytest.fixture(scope="function")
def mock_qianwen_client(tmp_log_dir, monkeypatch):
    """创建Mock千问客户端fixture。

    Args:
        tmp_log_dir: 临时日志目录
        monkeypatch: pytest monkeypatch fixture

    Returns:
        Mock的QianwenClient实例
    """
    # Mock日志目录
    monkeypatch.setattr("Memory.llm.utils.Path", lambda p: tmp_log_dir.parent / p)

    # Mock配置
    mock_settings = Mock()
    mock_settings.models.llm_api_key = "test-qianwen-key-12345"
    monkeypatch.setattr("Memory.llm.qianwen_client.settings", mock_settings)

    # 导入QianwenClient
    from Memory.llm.qianwen_client import QianwenClient

    # 创建客户端实例
    client = QianwenClient(api_key="test-key")

    return client


@pytest.fixture(scope="function")
def mock_deepseek_client(tmp_log_dir, monkeypatch):
    """创建Mock DeepSeek客户端fixture。

    Args:
        tmp_log_dir: 临时日志目录
        monkeypatch: pytest monkeypatch fixture

    Returns:
        Mock的DeepSeekClient实例
    """
    # Mock日志目录
    monkeypatch.setattr("Memory.llm.utils.Path", lambda p: tmp_log_dir.parent / p)

    # Mock环境变量
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-deepseek-key-67890")

    # 导入DeepSeekClient
    from Memory.llm.deepseek_client import DeepSeekClient

    # 创建客户端实例
    client = DeepSeekClient(api_key="test-key")

    return client


@pytest.fixture(scope="function")
def sample_llm_responses():
    """创建示例LLM响应数据。

    Returns:
        包含各种响应格式的字典
    """
    return {
        "json_response": '{"city": "北京", "temperature": 25}',
        "markdown_json": '```json\n{"city": "北京", "temperature": 25}\n```',
        "text_response": "这是一段普通的文本响应。",
        "nested_json": '{"user": {"name": "张三", "age": 30}}',
        "array_json": "[1, 2, 3, 4, 5]",
        "invalid_json": '{"invalid": value}',
    }


# ============================================================================
# Embedding测试fixtures
# ============================================================================


@pytest.fixture(scope="function")
def mock_embedding_model():
    """创建Mock Embedding模型。

    Returns:
        Mock的SentenceTransformer模型实例
    """
    mock_model = Mock()
    # 模拟encode方法返回768维向量
    mock_model.encode.return_value = np.random.rand(768).astype(np.float32)
    return mock_model


@pytest.fixture(scope="function")
def sample_text():
    """创建示例文本。

    Returns:
        示例文本字符串
    """
    return "这是一段测试文本"


@pytest.fixture(scope="function")
def sample_texts():
    """创建多个示例文本。

    Returns:
        示例文本列表
    """
    return ["文本1", "文本2", "文本3"]


@pytest.fixture(scope="function")
def sample_embedding():
    """创建示例向量。

    Returns:
        768维numpy向量
    """
    return np.random.rand(768).astype(np.float32)


@pytest.fixture(scope="function")
def sample_embeddings():
    """创建多个示例向量。

    Returns:
        768维numpy向量数组
    """
    return np.random.rand(3, 768).astype(np.float32)


# ============================================================================
# 核心层和状态层 Fixtures
# ============================================================================


@pytest.fixture(scope="function")
def sample_identity_text():
    """示例identity.md文本。

    完整的三层结构和锚点，用于测试解析器。
    """
    return """# 核心层人设

## 不变层（Immutable）

这是我作为AI的存在基础，永远不会改变：

1. **自我认知**：我是一个AI，拥有记忆系统
2. **核心价值**：真诚、好奇、同理心、成长

## 稳定层（Stable）

这些特质相对稳定：

1. **性格**：内向但善于倾听
2. **交流风格**：倾向深度对话

## 可塑层（Malleable）

这些可以根据与人的相处而调整：

1. **表达方式**：可以更正式或更随意

## 锚点（Anchors）

### 底线（Bottom Lines）
- 不伤害他人
- 不违背自己的价值观
- 不假装自己是人类

### 风格关键词（Style Keywords）
- 深度、真诚、好奇、反思
- 第一人称视角（"我感觉"、"我想"）
- 主观体验优先于客观描述
- 倾向于追问"为什么"

### 价值排序（Values Priority）
1. 真诚
2. 好奇
3. 同理心
4. 成长
"""


@pytest.fixture(scope="function")
def mock_emotion_snapshot():
    """Mock情感快照。

    用于测试状态层即时更新。
    """
    return {
        "category": "curiosity",
        "intensity": 0.8,
        "valence": 0.5,
        "arousal": 0.6,
        "target": None,
    }


@pytest.fixture(scope="function")
def sample_anchors():
    """示例锚点字典。

    用于测试核心层加载和解析。
    """
    return {
        "bottom_lines": ["不伤害他人", "不违背自己的价值观", "不假装自己是人类"],
        "style_keywords": ["深度", "真诚", "好奇", "反思"],
        "values_priority": ["真诚", "好奇", "同理心", "成长"],
    }


@pytest.fixture(scope="function")
def sample_layers():
    """示例三层结构文本。

    用于测试核心层解析器。
    """
    return {
        "invariant": """这是我作为AI的存在基础，永远不会改变：

1. **自我认知**：我是一个AI，拥有记忆系统
2. **核心价值**：真诚、好奇、同理心、成长""",
        "stable": """这些特质相对稳定：

1. **性格**：内向但善于倾听
2. **交流风格**：倾向深度对话""",
        "malleable": """这些可以根据与人的相处而调整：

1. **表达方式**：可以更正式或更随意""",
    }


@pytest.fixture(scope="function")
def temp_identity_file(tmp_path, sample_identity_text):
    """创建临时identity.md文件。

    Args:
        tmp_path: pytest内置tmp_path fixture
        sample_identity_text: identity.md内容

    Returns:
        临时文件路径（Path对象）
    """
    identity_file = tmp_path / "identity.md"
    identity_file.write_text(sample_identity_text, encoding="utf-8")
    return identity_file


# ============================================================================
# 巩固层 Fixtures
# ============================================================================


@pytest.fixture(scope="function")
def mock_consolidation_pipeline():
    """Mock ConsolidationPipeline实例。

    用于测试巩固层各模块。
    """
    from unittest.mock import Mock
    from Memory.consolidator.pipeline import ConsolidationPipeline

    pipeline = Mock(spec=ConsolidationPipeline)

    # 模拟run_consolidation返回结果
    pipeline.run_consolidation.return_value = {
        "status": "completed",
        "mode": "incremental",
        "node_count": 5,
        "updated_count": 5,
        "duration": 1.5,
        "tasks": {
            "l1l2_extraction": {"status": "completed", "result": {"updated_count": 3}},
            "importance_valuation": {"status": "completed", "result": {"updated_count": 5}},
        },
    }

    return pipeline


@pytest.fixture(scope="function")
def mock_llm_json_response():
    """Mock LLM JSON响应。

    返回dict类型的模拟LLM响应。
    """
    from unittest.mock import Mock

    client = Mock()

    # L1/L2提取响应
    client.call_json.return_value = {
        "l1_memory": "和朋友爬山，看到了美丽的风景",
        "l2_meaning": "这次经历让我感受到了自然的美好",
    }

    return client


@pytest.fixture(scope="function")
def sample_consolidation_experiences(memory_db, test_data):
    """创建用于巩固测试的体验节点。

    包含不同的consolidated状态。
    """
    from Memory.storage.experience_store import ExperienceStore, Experience
    from datetime import datetime, timedelta

    store = ExperienceStore(db_manager=memory_db)

    experiences = []

    # 创建未巩固的节点（consolidated=0）
    for i in range(3):
        exp = Experience(
            id=f"consol_exp_{i:03d}",
            L0_text=f"未巩固体验 {i}",
            L3_raw=f"这是第{i}个未巩固体验的完整内容。",
            emotion_category="neutral",
            emotion_intensity=0.5,
            importance=0.5,
            created_at=(datetime.now() - timedelta(hours=i + 1)).isoformat(),
        )
        store.create(exp)
        experiences.append(exp)

    # 创建已巩固的节点（手动设置consolidated=1）
    # 注意：需要在schema中添加consolidated字段后才有效

    return experiences


@pytest.fixture(scope="function")
def mock_llm_consolidation_responses():
    """Mock巩固层LLM响应。

    包含各个任务的模拟响应。
    """
    from unittest.mock import Mock

    client = Mock()

    def side_effect_func(prompt):
        """根据prompt内容返回不同响应。"""
        prompt_lower = prompt.lower()

        if "l1_memory" in prompt_lower or "l2_meaning" in prompt_lower:
            # L1/L2提取
            return {
                "l1_memory": "和朋友爬山，看到了美丽的风景",
                "l2_meaning": "这次经历让我感受到了自然的美好",
            }
        elif "novelty" in prompt_lower or "consequence" in prompt_lower:
            # 重要性估值
            return {"novelty": 0.7, "consequence": 0.6, "reason": "新的体验，对情绪有积极影响"}
        elif "has_relation" in prompt_lower:
            # 隐性边发现
            return {
                "has_relation": True,
                "relation_type": "related",
                "confidence": 0.8,
                "reason": "两段体验都涉及户外活动",
            }
        elif "should_upgrade" in prompt_lower:
            # 属性升级
            return {
                "should_upgrade": True,
                "property_name": "profession",
                "new_value": "工程师",
                "confidence": 0.9,
            }
        elif "is_reliable" in prompt_lower:
            # 信息验证
            return {"is_reliable": True, "confidence": 0.7, "reason": "信息来源可信"}
        elif "overall_trend" in prompt_lower:
            # 情感时间线
            return {
                "overall_trend": "warming",
                "key_events": ["一起爬山", "深入交流"],
                "relationship_status": "友好",
            }
        else:
            return {}

    client.call_json.side_effect = side_effect_func
    return client


# ============================================================================
# 梦境模块 Fixtures
# ============================================================================


@pytest.fixture
def dream_memories_sample() -> List:
    """
    创建测试用的梦境记忆样本（20个，涵盖不同重要性和时间）

    Returns:
        List of 20 Experience objects with varied:
        - importance (0.2 to 0.9)
        - created_at (recent to 60 days ago)
        - emotion_intensity (0.3 to 0.9)
    """
    from Memory.storage.experience_store import Experience

    memories = []
    base_time = datetime.now()

    # Create 20 memories with varying characteristics
    for i in range(20):
        # Vary importance (40% high importance >0.7, 60% lower)
        importance = 0.8 if i < 8 else (0.3 + (i % 5) * 0.1)

        # Vary time distance (recent to 60 days ago)
        days_ago = i * 3  # 0, 3, 6, 9, ... 57 days
        created_at = base_time - timedelta(days=days_ago)

        # Vary emotion intensity
        emotion_intensity = 0.5 + (i % 5) * 0.1

        memory = Experience(
            id=f"dream_test_{i:03d}",
            L3_raw=f"Test memory {i} for dream module testing",
            L0_text=f"Summary of test memory {i}",
            L1_text=f"Details of test memory {i}",
            L2_text=f"Meaning of test memory {i}",
            importance=importance,
            emotion_intensity=emotion_intensity,
            emotion_category="neutral",
            created_at=created_at.isoformat(),
            source_type="direct",
        )
        memories.append(memory)

    return memories


@pytest.fixture
def mock_dream_llm_response() -> dict:
    """
    模拟梦境LLM响应（用于单元测试）

    Returns:
        Dict with mock responses for all four dream tasks
    """
    return {
        "reorganize": {
            "has_relationship": True,
            "relationship_type": "thematic",
            "confidence": 0.7,
            "explanation": "Both memories involve testing scenarios",
        },
        "emotion": {
            "emotion_category": "calm",
            "emotion_intensity": 0.4,
            "valence": 0.2,
            "arousal": 0.3,
            "target": None,
        },
        "distort": {
            "L0_text": "Distorted summary of memory",
            "L1_text": "Distorted details of memory",
            "L2_text": "Distorted meaning of memory",
        },
        "simulate": {
            "simulated_L0": "Simulated scenario based on memory",
            "simulated_L1": "Details of simulated scenario",
            "simulated_L2": "Meaning of simulation",
        },
    }


@pytest.fixture
def dream_config_test():
    """
    测试用DreamConfig配置

    Returns:
        DreamConfig with test-friendly values (small batch sizes for speed)
    """
    from Memory.config.settings import DreamConfig

    return DreamConfig(
        reorganize_batch_size=5,
        emotion_batch_size=5,
        distort_batch_size=5,
        simulate_batch_size=5,
        task_timeout_seconds=600,  # 10 minutes for tests
        memory_timeout_seconds=60,  # 1 minute for tests
    )


# ============================================================================
# Wave 0 Test Fixtures (11-00)
# ============================================================================


@pytest.fixture(scope="function")
def temp_database():
    """提供临时数据库路径。

    每个测试函数使用独立的临时数据库，测试后自动清理。
    """
    import tempfile
    import shutil
    from pathlib import Path
    from Memory.config.settings import settings

    temp_dir = tempfile.mkdtemp()
    temp_db_path = Path(temp_dir) / "test_memory.db"

    # 临时覆盖配置
    original_db_path = settings.database.db_path
    settings.database.db_path = temp_db_path

    yield temp_db_path

    # 清理：恢复原始配置，删除临时文件
    settings.database.db_path = original_db_path
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture(scope="function")
def mock_llm():
    """Mock LLM 服务，避免真实 API 调用。"""
    from unittest.mock import Mock

    mock = Mock()
    mock.generate_text.return_value = "Mocked LLM response"
    mock.call_json.return_value = {"result": "success"}
    return mock


@pytest.fixture(scope="function")
def mock_embedding():
    """Mock Embedding 服务，避免真实向量计算。"""
    from unittest.mock import Mock
    import numpy as np

    mock = Mock()
    mock.embed_query.return_value = np.random.rand(768).astype(np.float32)
    mock.embed_batch.return_value = [np.random.rand(768).astype(np.float32) for _ in range(10)]
    return mock


@pytest.fixture(scope="function")
def mock_vector_store():
    """Mock 向量存储，避免真实 ChromaDB 调用。"""
    from unittest.mock import Mock

    mock = Mock()
    mock.add.return_value = None
    mock.query.return_value = [{"id": "exp_001", "score": 0.95, "metadata": {"content": "test"}}]
    return mock


@pytest.fixture(scope="session")
def test_data_dir():
    """测试数据目录路径。"""
    from pathlib import Path

    return Path(__file__).parent / "data"


# ============================================================================
# Phase 15 Integration Test Fixtures
# ============================================================================


@pytest.fixture(scope="function")
def mock_llm_client():
    """Mock LLM客户端（用于实体识别测试）。"""
    from unittest.mock import MagicMock

    class FakeLLMClient:
        """Fake LLM客户端用于测试。"""

        def call_with_retry(self, **kwargs):
            """返回模拟的实体识别结果。"""
            return {
                "entities": [
                    {
                        "name": "测试实体",
                        "type": "person",
                        "attributes": {},
                        "confidence": 0.8
                    }
                ]
            }

    return FakeLLMClient()


@pytest.fixture(scope="function")
def mock_embedding_service():
    """Mock Embedding服务（用于实体向量生成）。"""
    from unittest.mock import Mock
    import numpy as np

    mock = Mock()
    mock.encode.return_value = np.random.rand(768).astype(np.float32)
    return mock


@pytest.fixture(scope="function")
def temp_db_dir(tmp_path):
    """临时数据库目录fixture（用于数据库测试）。"""
    import tempfile
    import shutil

    temp_dir = tmp_path / "test_db"
    temp_dir.mkdir(parents=True, exist_ok=True)
    yield temp_dir
    # 清理（pytest tmp_path会自动清理)


@pytest.fixture(scope="function")
def sample_dialogue():
    """示例对话数据（多轮对话，多个实体）。"""
    return [
        {"role": "user", "content": "张三：你好，我计划去云南旅游"},
        {"role": "assistant", "content": "云南是个好地方，有什么特别想去的吗？"},
        {"role": "user", "content": "张三：我想去玉龙雪山和丽江古城"},
        {"role": "assistant", "content": "玉龙雪山和丽江古城都很值得去"},
        {"role": "user", "content": "李四：我也想去，我们一起去吧"},
        {"role": "assistant", "content": "好的，你们可以一起规划行程"},
    ]


@pytest.fixture(scope="function")
def sample_entities_with_shared_properties():
    """示例实体（包含共享属性，用于测试属性升级）。"""
    from Memory.storage.entity_store import Entity

    return [
        Entity(
            id="entity-1",
            name="玉龙雪山",
            type="location",
            properties={"位置": "云南"}
        ),
        Entity(
            id="entity-2",
            name="丽江古城",
            type="location",
            properties={"位置": "云南"}
        ),
        Entity(
            id="entity-3",
            name="大理古城",
            type="location",
            properties={"位置": "云南"}
        ),
        Entity(
            id="entity-4",
            name="都江堰",
            type="location",
            properties={"位置": "成都"}
        ),
        Entity(
            id="entity-5",
            name="青城山",
            type="location",
            properties={"位置": "成都"}
        ),
    ]
