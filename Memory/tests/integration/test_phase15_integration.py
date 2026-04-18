"""Phase 15 端到端集成测试。

本测试套件验证Phase 15的完整实现：
- Wave 1: 实体识别Prompt重写和任务实现
- Wave 2: Schema v6→v7迁移（添加source和confidence字段）
- Wave 3: 属性升级任务重设计（共享属性升级）
- Wave 4: 端到端集成测试

验证的决策（D-01到D-05）：
- D-01: LLM识别策略 - 核心属性优先
- D-02: 数据结构设计 - 元数据和业务属性分离
- D-03: Prompt设计 - 精心设计系统提示词
- D-04: 数据迁移方案 - 用户清空数据库
- D-05: 属性升级任务 - 重新设计为共享属性升级
"""

import pytest
import json
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime, timedelta
from pathlib import Path

from Memory.writer.pipeline import WriterPipeline
from Memory.consolidator.tasks.property_upgrade_task import upgrade_shared_attributes
from Memory.storage.entity_store import EntityStore, Entity
from Memory.storage.entity_edge_store import EntityEdgeStore
from Memory.storage.experience_store import ExperienceStore, Experience
from Memory.storage.cross_edge_store import CrossEdgeStore, CrossEdge
from Memory.storage.database import DatabaseManager
from Memory.storage.schema import create_all_tables, get_current_schema_version


class TestFullEntityRecognitionFlow:
    """测试1: test_full_entity_recognition_flow - 完整实体识别流程。

    验证：
    - 对话→L0摘要→实体识别→数据库存储→跨层边创建
    - 创建正确的实体类型（person, location等）
    - 实体name简洁（不是完整句子）
    - properties只包含业务属性（如"位置: 云南"）
    - source和confidence在表字段（不在properties中）
    - 跨层边context="contains_entity"

    决策验证：
    - D-01: 核心属性优先（只提取位置，不提取描述）
    - D-02: 元数据和业务属性分离（source/confidence在表字段）
    - D-03: 精心设计的Prompt（实体识别准确）
    """

    def test_full_entity_recognition_flow(self, db_manager, mock_llm_client, mock_embedding_service):
        """测试完整的实体识别流程（对话→实体→数据库→边）。

        场景：张三、李四、AI讨论去云南旅游，提到玉龙雪山和丽江古城。

        预期结果：
        - 创建3个person实体（张三、李四、AI）
        - 创建2个location实体（玉龙雪山、丽江古城）
        - 实体name简洁（如"玉龙雪山"，不是"玉龙雪山是云南的一个著名景点"）
        - properties只包含业务属性（如"位置": "云南"）
        - source字段在表字段中（如"张三"）
        - confidence字段在表字段中（如0.8）
        - 跨层边context="contains_entity"
        """
        # 准备测试数据：多轮对话
        dialogue = [
            {"role": "user", "content": "张三：你好，我计划去云南旅游"},
            {"role": "assistant", "content": "云南是个好地方，有什么特别想去的吗？"},
            {"role": "user", "content": "张三：我想去玉龙雪山和丽江古城"},
            {"role": "assistant", "content": "玉龙雪山和丽江古城都很值得去"},
            {"role": "user", "content": "李四：我也想去，我们一起去吧"},
            {"role": "assistant", "content": "好的，你们可以一起规划行程"},
        ]

        # Mock LLM返回实体识别结果
        mock_llm_client.call_with_retry.return_value = {
            "entities": [
                {
                    "name": "张三",
                    "type": "person",
                    "attributes": {},
                    "confidence": 0.9
                },
                {
                    "name": "李四",
                    "type": "person",
                    "attributes": {},
                    "confidence": 0.8
                },
                {
                    "name": "玉龙雪山",
                    "type": "location",
                    "attributes": {
                        "位置": "云南"
                    },
                    "confidence": 0.95
                },
                {
                    "name": "丽江古城",
                    "type": "location",
                    "attributes": {
                        "位置": "云南"
                    },
                    "confidence": 0.95
                }
            ]
        }

        # 创建Store实例
        experience_store = ExperienceStore(db_manager)
        entity_store = EntityStore(db_manager)
        cross_edge_store = CrossEdgeStore(db_manager)

        # 执行写入流程
        from Memory.writer.tasks.entity_task import recognize_entities_and_create_edges

        # 先创建experience
        experience = Experience(
            id="exp_20260409_120000",
            L0_text="张三和李四计划去云南旅游，讨论玉龙雪山和丽江古城",
            L3_raw=json.dumps(dialogue, ensure_ascii=False),
            emotion_category="excitement",
            emotion_intensity=0.7,
            emotion_valence=0.8,
            emotion_arousal=0.6,
            importance=0.6,
        )
        experience_store.create(experience)

        # 执行实体识别
        entity_ids = recognize_entities_and_create_edges(
            experience_id="exp_20260409_120000",
            dialogue=json.dumps(dialogue, ensure_ascii=False),
            llm_client=mock_llm_client,
            embedding_service=mock_embedding_service,
            entity_store=entity_store,
            cross_edge_store=cross_edge_store,
        )

        # 验证：创建了4个实体（张三、李四、玉龙雪山、丽江古城）
        assert len(entity_ids) == 4

        # 验证：读取所有实体
        all_entities = entity_store.get_all()
        assert len(all_entities) == 4

        # 验证：张三实体（person类型）
        zhang_san = next((e for e in all_entities if e.name == "张三"), None)
        assert zhang_san is not None
        assert zhang_san.type == "person"
        assert zhang_san.properties == {}  # 人物实体没有业务属性
        assert zhang_san.source is not None  # source字段存在
        assert zhang_san.confidence == 0.9  # confidence字段存在

        # 验证：玉龙雪山实体（location类型）
        jade_snow = next((e for e in all_entities if e.name == "玉龙雪山"), None)
        assert jade_snow is not None
        assert jade_snow.type == "location"
        assert jade_snow.properties == {"位置": "云南"}  # 业务属性在properties中
        assert "描述" not in jade_snow.properties  # 不包含描述性文本（D-01核心属性优先）
        assert "source" not in jade_snow.properties  # 元数据不在properties中（D-02）
        assert "confidence" not in jade_snow.properties  # 元数据不在properties中（D-02）
        assert jade_snow.source is not None  # source在表字段中
        assert jade_snow.confidence == 0.95  # confidence在表字段中

        # 验证：跨层边创建
        cross_edges = cross_edge_store.get_by_from("exp_20260409_120000")
        assert len(cross_edges) == 4  # 4个实体，4条边

        # 验证：跨层边context="contains_entity"
        for edge in cross_edges:
            assert edge.context == "contains_entity"
            assert edge.from_id == "exp_20260409_120000"
            assert edge.to_id in entity_ids


class TestSharedAttributeUpgradeFlow:
    """测试2: test_shared_attribute_upgrade_flow - 共享属性升级流程。

    验证：
    - 检测高频共享属性值（如"位置: 云南"出现3次）
    - 将共享属性值升级为独立实体（创建"云南"实体）
    - 不创建属性名实体（不创建"位置"实体）
    - 创建关系边（原实体→新实体，relation=属性名）
    - 原实体保持不变（不被"升级"）

    决策验证：
    - D-05: "是属性，才能升级"（只有属性值升级，属性名不升级）
    """

    def test_shared_attribute_upgrade_flow(self, db_manager, mock_embedding_service):
        """测试共享属性升级流程。

        场景：
        - 3个location实体都有"位置: 云南"属性
        - 执行upgrade_shared_attributes()
        - 验证：
          1. 创建新实体"云南"（type="location"）
          2. 不创建"位置"实体（属性名不升级）
          3. 创建3条关系边（原实体→"云南"，relation="位置"）
          4. 原实体保持不变（不被"升级"）
        """
        # 准备：创建3个location实体，都有"位置: 云南"属性
        entity_store = EntityStore(db_manager)
        edge_store = EntityEdgeStore(db_manager)

        entity1 = Entity(
            id="entity-1",
            name="玉龙雪山",
            type="location",
            properties={"位置": "云南"},
            source="张三",
            confidence=0.9,
        )
        entity2 = Entity(
            id="entity-2",
            name="丽江古城",
            type="location",
            properties={"位置": "云南"},
            source="张三",
            confidence=0.9,
        )
        entity3 = Entity(
            id="entity-3",
            name="大理古城",
            type="location",
            properties={"位置": "云南"},
            source="李四",
            confidence=0.8,
        )

        entity_store.create(entity1)
        entity_store.create(entity2)
        entity_store.create(entity3)

        # 执行：共享属性升级
        result = upgrade_shared_attributes(
            entity_store=entity_store,
            edge_store=edge_store,
            embedding_service=mock_embedding_service,
            threshold=3,
        )

        # 验证1：创建了"云南"实体
        yunnan_entity = entity_store.get_by_name("云南")
        assert yunnan_entity is not None, "应该创建'云南'实体"
        assert yunnan_entity.type == "location", "实体类型应该是location"
        assert "升级来源" in yunnan_entity.properties, "应该包含升级来源标记"

        # 验证2：不创建"位置"实体（属性名不升级）
        location_entity = entity_store.get_by_name("位置")
        assert location_entity is None, "不应该创建'位置'实体（属性名不升级）"

        # 验证3：原实体保持不变（不被"升级"）
        jade_snow = entity_store.get_by_name("玉龙雪山")
        assert jade_snow is not None, "原实体'玉龙雪山'应该仍然存在"
        assert jade_snow.id == "entity-1", "原实体ID不应该改变"
        assert jade_snow.properties == {"位置": "云南"}, "原实体属性不应该改变"
        assert jade_snow.source == "张三", "原实体source不应该改变"

        lijiang_old = entity_store.get_by_name("丽江古城")
        assert lijiang_old is not None, "原实体'丽江古城'应该仍然存在"
        assert lijiang_old.id == "entity-2", "原实体ID不应该改变"
        assert lijiang_old.properties == {"位置": "云南"}, "原实体属性不应该改变"

        # 验证4：创建3条关系边（雪山/丽江/大理 → 云南，relation="位置"）
        for entity_id in ["entity-1", "entity-2", "entity-3"]:
            edges = edge_store.get_by_from(entity_id)
            yunnan_edges = [e for e in edges if e.to_id == yunnan_entity.id]
            assert len(yunnan_edges) == 1, f"实体{entity_id}应该有1条指向'云南'的关系边"
            assert yunnan_edges[0].relation == "位置", "关系类型应该是'位置'"
            assert yunnan_edges[0].source == "attribute_upgrade", "边来源应该是attribute_upgrade"


class TestDataStructureCorrectness:
    """测试3: test_data_structure_correctness - 数据结构正确性验证。

    验证：
    - 实体name字段：简洁的实体名（如"玉龙雪山"）
    - 实体properties字段：只包含业务属性（如{"位置": "云南"}）
    - 实体source字段：信息来源（如"张三"）
    - 实体confidence字段：置信度（如0.8）
    - properties不包含元数据（无source/confidence/type键）

    决策验证：
    - D-02: 元数据和业务属性分离
    """

    def test_data_structure_correctness(self, db_manager):
        """测试实体数据结构正确性。

        从数据库读取实体，验证：
        1. name字段：简洁的实体名（如"玉龙雪山"）
        2. properties字段：只包含业务属性（如{"位置": "云南"}）
        3. source字段：信息来源（如"张三"）
        4. confidence字段：置信度（如0.8）
        5. properties不包含元数据（无source/confidence/type键）
        """
        # 准备：创建测试实体
        entity_store = EntityStore(db_manager)

        entity = Entity(
            id="entity-test-001",
            name="玉龙雪山",
            type="location",
            properties={"位置": "云南"},
            source="张三",
            confidence=0.9,
        )
        entity_store.create(entity)

        # 执行：从数据库读取实体
        retrieved_entity = entity_store.get_by_name("玉龙雪山")

        # 验证1：name字段 - 简洁的实体名
        assert retrieved_entity.name == "玉龙雪山"
        assert " " not in retrieved_entity.name  # 不包含空格
        assert len(retrieved_entity.name) < 20  # 不是长句子
        assert "是" not in retrieved_entity.name  # 不是"玉龙雪山是云南的..."这种描述

        # 验证2：properties字段 - 只包含业务属性
        assert isinstance(retrieved_entity.properties, dict)
        assert "位置" in retrieved_entity.properties  # 业务属性
        assert retrieved_entity.properties["位置"] == "云南"

        # 验证3：source字段 - 信息来源在表字段中
        assert retrieved_entity.source == "张三"
        assert retrieved_entity.source is not None

        # 验证4：confidence字段 - 置信度在表字段中
        assert retrieved_entity.confidence == 0.9
        assert retrieved_entity.confidence is not None

        # 验证5：properties不包含元数据
        assert "source" not in retrieved_entity.properties  # 元数据不在properties中
        assert "confidence" not in retrieved_entity.properties  # 元数据不在properties中
        assert "type" not in retrieved_entity.properties  # 元数据不在properties中


class TestNoRegressionInWave123:
    """测试4: test_no_regression_in_wave123 - Wave 1-3无回归验证。

    验证：
    - Wave 0的11个测试继续通过
    - Wave 1的实体识别测试继续通过
    - Wave 2的schema迁移测试继续通过
    - Wave 3的属性升级测试继续通过
    - 测试状态从SKIPPED变为PASSED

    这确保Phase 15的所有变更没有破坏现有功能。
    """

    def test_wave0_entity_recognition_tests_pass(self, db_manager, mock_llm_client, mock_embedding_service):
        """验证Wave 0的实体识别测试继续通过。"""
        # 这个测试验证test_entity_task.py中的测试仍然通过
        from Memory.writer.tasks.entity_task import recognize_entities_and_create_edges
        from unittest.mock import Mock

        # 准备测试数据
        experience_id = "exp_test_001"
        dialogue = "张三：我想学Python\nAI：好的，我来教你。"

        # Mock LLM返回
        mock_llm_client.call_with_retry.return_value = {
            "entities": [
                {
                    "name": "张三",
                    "type": "person",
                    "attributes": {"learning_goal": "想学Python"},
                    "confidence": 0.9
                },
                {
                    "name": "Python",
                    "type": "concept",
                    "attributes": {"category": "编程语言"},
                    "confidence": 1.0
                }
            ]
        }

        entity_store = Mock()
        entity_store.get_by_name.return_value = None
        entity_store.create.return_value = "entity-123"

        cross_edge_store = Mock()
        cross_edge_store.create.return_value = 1

        # 执行实体识别
        entity_ids = recognize_entities_and_create_edges(
            experience_id=experience_id,
            dialogue=dialogue,
            llm_client=mock_llm_client,
            embedding_service=mock_embedding_service,
            entity_store=entity_store,
            cross_edge_store=cross_edge_store,
        )

        # 验证：测试仍然通过
        assert len(entity_ids) == 2
        assert entity_store.create.call_count == 2
        assert cross_edge_store.create.call_count == 2

    def test_wave1_entity_recognition_still_works(self, db_manager, mock_llm_client, mock_embedding_service):
        """验证Wave 1的实体识别功能仍然正常工作。"""
        from Memory.writer.tasks.entity_task import recognize_entities_and_create_edges
        from unittest.mock import Mock

        # 准备测试数据
        experience_id = "exp_wave1_test"
        dialogue = "张三昨天去了北京参加AI会议"

        # Mock LLM返回多种类型实体
        mock_llm_client.call_with_retry.return_value = {
            "entities": [
                {"name": "张三", "type": "person", "attributes": {}, "confidence": 0.9},
                {"name": "北京", "type": "place", "attributes": {}, "confidence": 1.0},
                {"name": "AI会议", "type": "event", "attributes": {}, "confidence": 0.8}
            ]
        }

        entity_store = Mock()
        entity_store.get_by_name.return_value = None
        entity_store.create.return_value = "entity-123"

        cross_edge_store = Mock()

        # 执行实体识别
        entity_ids = recognize_entities_and_create_edges(
            experience_id=experience_id,
            dialogue=dialogue,
            llm_client=mock_llm_client,
            embedding_service=mock_embedding_service,
            entity_store=entity_store,
            cross_edge_store=cross_edge_store,
        )

        # 验证：创建了3个不同类型的实体
        assert len(entity_ids) == 3
        assert entity_store.create.call_count == 3

    def test_wave2_schema_migration_success(self, db_manager):
        """验证Wave 2的schema迁移成功（v6→v7）。"""
        # 验证schema版本
        version = get_current_schema_version(db_manager)
        assert version == "v7", f"Schema version should be v7, got {version}"

        # 验证entities表包含source和confidence字段
        cursor = db_manager.execute_query("PRAGMA table_info(entities)")
        columns = [row["name"] for row in cursor.fetchall()]

        assert "source" in columns, "entities表应该包含source字段"
        assert "confidence" in columns, "entities表应该包含confidence字段"

    def test_wave3_shared_attribute_upgrade_still_works(self, db_manager, mock_embedding_service):
        """验证Wave 3的共享属性升级功能仍然正常工作。"""
        from Memory.consolidator.tasks.property_upgrade_task import upgrade_shared_attributes
        from Memory.storage.entity_edge_store import EntityEdgeStore

        entity_store = EntityStore(db_manager)
        edge_store = EntityEdgeStore(db_manager)

        # 创建测试实体：3个实体都有"位置: 云南"属性
        entity1 = Entity(
            id="entity-1", name="玉龙雪山", type="location", properties={"位置": "云南"}
        )
        entity2 = Entity(
            id="entity-2", name="丽江古城", type="location", properties={"位置": "云南"}
        )
        entity3 = Entity(
            id="entity-3", name="大理古城", type="location", properties={"位置": "云南"}
        )

        entity_store.create(entity1)
        entity_store.create(entity2)
        entity_store.create(entity3)

        # 执行共享属性升级
        result = upgrade_shared_attributes(
            entity_store=entity_store,
            edge_store=edge_store,
            embedding_service=mock_embedding_service,
            threshold=3,
        )

        # 验证：升级成功
        assert result["promoted_count"] >= 1, "至少应该升级1个实体"

        yunnan_entity = entity_store.get_by_name("云南")
        assert yunnan_entity is not None, "应该创建'云南'实体"
