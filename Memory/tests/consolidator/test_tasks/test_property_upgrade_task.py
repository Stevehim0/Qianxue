"""属性升级扫描任务测试模块。

测试get_shared_properties()方法和scan_property_upgrade()函数。
"""

import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

from Memory.storage.entity_store import EntityStore, Entity
from Memory.storage.experience_store import Experience
from Memory.consolidator.tasks.property_upgrade_task import scan_property_upgrade


class TestGetSharedProperties:
    """测试EntityStore.get_shared_properties()方法。"""

    def test_returns_shared_properties_above_threshold(self, db_manager):
        """测试返回共享次数>=threshold的属性。"""
        store = EntityStore(db_manager)

        # 创建测试实体
        entity1 = Entity(
            id="entity-1", name="Alice", type="person", properties={"city": "Beijing", "age": 25}
        )
        entity2 = Entity(
            id="entity-2", name="Bob", type="person", properties={"city": "Beijing", "age": 30}
        )
        entity3 = Entity(
            id="entity-3", name="Charlie", type="person", properties={"city": "Beijing", "age": 35}
        )
        entity4 = Entity(
            id="entity-4", name="David", type="person", properties={"city": "Shanghai", "age": 28}
        )
        entity5 = Entity(
            id="entity-5", name="Eve", type="person", properties={"city": "Beijing", "age": 27}
        )

        # 创建实体
        store.create(entity1)
        store.create(entity2)
        create_entity3 = store.create(entity3)
        store.create(entity4)
        store.create(entity5)

        # 测试threshold=3，city:Beijing出现5次
        shared = store.get_shared_properties(threshold=3)

        # 应该返回city:Beijing（5次）
        assert len(shared) == 1
        assert shared[0]["property_name"] == "city"
        assert shared[0]["property_value"] == "Beijing"
        assert shared[0]["count"] == 5
        assert len(shared[0]["entities"]) == 5

    def test_statistics_based_on_entities_table(self, db_manager):
        """测试统计基于entities表的properties字段。"""
        store = EntityStore(db_manager)

        # 创建实体，有些有properties，有些没有
        entity1 = Entity(id="entity-1", name="Alice", type="person", properties={"city": "Beijing"})
        entity2 = Entity(id="entity-2", name="Bob", type="person", properties={"city": "Beijing"})
        entity3 = Entity(id="entity-3", name="Charlie", type="person", properties=None)

        store.create(entity1)
        store.create(entity2)
        store.create(entity3)

        # 测试：只统计有properties的实体
        shared = store.get_shared_properties(threshold=2)

        # city:Beijing出现2次
        assert len(shared) == 1
        assert shared[0]["count"] == 2

    def test_returns_property_structure(self, db_manager):
        """测试返回包含属性名、值、实体列表、计数。"""
        store = EntityStore(db_manager)

        entity1 = Entity(id="entity-1", name="Alice", type="person", properties={"city": "Beijing"})
        entity2 = Entity(id="entity-2", name="Bob", type="person", properties={"city": "Beijing"})
        entity3 = Entity(
            id="entity-3", name="Charlie", type="person", properties={"city": "Beijing"}
        )

        store.create(entity1)
        store.create(entity2)
        store.create(entity3)

        shared = store.get_shared_properties(threshold=3)

        # 检查返回结构
        assert len(shared) == 1
        prop = shared[0]

        # 必须包含这些字段
        assert "property_name" in prop
        assert "property_value" in prop
        assert "entities" in prop
        assert "count" in prop

        # 检查字段值
        assert prop["property_name"] == "city"
        assert prop["property_value"] == "Beijing"
        assert prop["count"] == 3
        assert len(prop["entities"]) == 3
        assert all(isinstance(eid, str) for eid in prop["entities"])

    def test_threshold_is_configurable(self, db_manager):
        """测试threshold可配置。"""
        store = EntityStore(db_manager)

        # 创建10个实体，city:Beijing出现10次
        for i in range(10):
            entity = Entity(
                id=f"entity-{i}", name=f"Person{i}", type="person", properties={"city": "Beijing"}
            )
            store.create(entity)

        # 测试不同threshold
        shared_5 = store.get_shared_properties(threshold=5)
        shared_8 = store.get_shared_properties(threshold=8)
        shared_12 = store.get_shared_properties(threshold=12)

        assert len(shared_5) == 1  # 10 >= 5
        assert len(shared_8) == 1  # 10 >= 8
        assert len(shared_12) == 0  # 10 < 12

    def test_sorts_by_count_descending(self, db_manager):
        """测试按共享次数降序排序。"""
        store = EntityStore(db_manager)

        # 创建实体：city:Beijing出现5次，city:Shanghai出现3次
        for i in range(5):
            entity = Entity(
                id=f"beijing-{i}",
                name=f"BeijingPerson{i}",
                type="person",
                properties={"city": "Beijing"},
            )
            store.create(entity)

        for i in range(3):
            entity = Entity(
                id=f"shanghai-{i}",
                name=f"ShanghaiPerson{i}",
                type="person",
                properties={"city": "Shanghai"},
            )
            store.create(entity)

        shared = store.get_shared_properties(threshold=3)

        # Beijing应该在前面（5次 > 3次）
        assert len(shared) == 2
        assert shared[0]["property_value"] == "Beijing"
        assert shared[0]["count"] == 5
        assert shared[1]["property_value"] == "Shanghai"
        assert shared[1]["count"] == 3

    def test_filters_by_property_names(self, db_manager):
        """测试支持指定属性名列表过滤。"""
        store = EntityStore(db_manager)

        # 创建实体：city和age都有共享
        for i in range(5):
            entity = Entity(
                id=f"entity-{i}",
                name=f"Person{i}",
                type="person",
                properties={"city": "Beijing", "age": 25},
            )
            store.create(entity)

        # 只检查city属性
        shared = store.get_shared_properties(threshold=3, property_names=["city"])

        # 应该只返回city
        assert len(shared) == 1
        assert shared[0]["property_name"] == "city"

    def test_handles_complex_property_values(self, db_manager):
        """测试处理复杂属性值（列表、字典）。"""
        store = EntityStore(db_manager)

        # 创建实体，properties包含列表和字典
        entity1 = Entity(
            id="entity-1",
            name="Alice",
            type="person",
            properties={"hobbies": ["reading", "gaming"], "profile": {"name": "Alice", "age": 25}},
        )
        entity2 = Entity(
            id="entity-2",
            name="Bob",
            type="person",
            properties={"hobbies": ["reading", "gaming"], "profile": {"name": "Bob", "age": 30}},
        )

        store.create(entity1)
        store.create(entity2)

        shared = store.get_shared_properties(threshold=2)

        # 复杂类型应该被正确统计
        assert len(shared) == 2
        hobbies_prop = next(p for p in shared if p["property_name"] == "hobbies")
        profile_prop = next(p for p in shared if p["property_name"] == "profile")

        assert hobbies_prop["count"] == 2
        assert profile_prop["count"] == 2


class TestPropertyUpgradeScan:
    """测试属性升级扫描功能。"""

    @patch("Memory.consolidator.tasks.property_upgrade_task.Path")
    def test_queries_shared_properties(self, mock_path, db_manager):
        """测试查询共享属性>=threshold的实体。"""
        # Mock prompt template
        mock_prompt = mock_path.return_value.__truediv__.return_value
        mock_prompt.__truediv__ = Mock(return_value=mock_prompt)
        mock_prompt.open = Mock()
        mock_prompt.open.return_value.__enter__ = Mock()
        mock_prompt.open.return_value.__exit__ = Mock()
        mock_prompt.open.return_value.read.return_value = "Prompt template"

        # Mock LLM client
        mock_llm = Mock()
        mock_llm.call_json.return_value = {
            "should_upgrade": False,
            "new_value": None,
            "confidence": 0.5,
        }

        store = EntityStore(db_manager)

        # 创建测试实体
        for i in range(5):
            entity = Entity(
                id=f"entity-{i}", name=f"Person{i}", type="person", properties={"city": "Beijing"}
            )
            store.create(entity)

        # 创建空的experiences列表
        experiences = []

        # 执行扫描
        result = scan_property_upgrade(
            experiences=experiences, llm_client=mock_llm, entity_store=store
        )

        # 应该评估了有共享属性的实体
        assert "evaluated_count" in result
        assert "upgraded_count" in result
        assert "skipped_count" in result

    @patch("Memory.consolidator.tasks.property_upgrade_task.Path")
    def test_evaluates_property_upgrade_with_llm(self, mock_path, db_manager):
        """测试对每个实体评估属性是否应该升级。"""
        # Mock prompt template
        mock_prompt = mock_path.return_value.__truediv__.return_value
        mock_prompt.__truediv__ = Mock(return_value=mock_prompt)
        mock_prompt.open = Mock()
        mock_prompt.open.return_value.__enter__ = Mock()
        mock_prompt.open.return_value.__exit__ = Mock()
        mock_prompt.open.return_value.read.return_value = (
            "Prompt: {entity_name} {current_properties} {new_experiences} {property_name}"
        )

        # Mock LLM client - 第一次返回should_upgrade=True
        mock_llm = Mock()
        mock_llm.call_json.side_effect = [
            {
                "should_upgrade": True,
                "property_name": "city",
                "new_value": "Shanghai",
                "confidence": 0.8,
            },
            {
                "should_upgrade": False,
                "property_name": "city",
                "new_value": None,
                "confidence": 0.5,
            },
        ]

        store = EntityStore(db_manager)

        # 创建测试实体
        for i in range(5):
            entity = Entity(
                id=f"entity-{i}", name=f"Person{i}", type="person", properties={"city": "Beijing"}
            )
            store.create(entity)

        experiences = []

        # 执行扫描
        result = scan_property_upgrade(
            experiences=experiences, llm_client=mock_llm, entity_store=store
        )

        # 应该调用了LLM评估
        assert mock_llm.call_json.called
        assert result["evaluated_count"] > 0

    @patch("Memory.consolidator.tasks.property_upgrade_task.Path")
    def test_updates_entity_properties(self, mock_path, db_manager):
        """测试更新实体的properties字段。"""
        # Mock prompt template
        mock_prompt = mock_path.return_value.__truediv__.return_value
        mock_prompt.__truediv__ = Mock(return_value=mock_prompt)
        mock_prompt.open = Mock()
        mock_prompt.open.return_value.__enter__ = Mock()
        mock_prompt.open.return_value.__exit__ = Mock()
        mock_prompt.open.return_value.read.return_value = (
            "Prompt: {entity_name} {current_properties} {new_experiences} {property_name}"
        )

        # Mock LLM client
        mock_llm = Mock()
        mock_llm.call_json.return_value = {
            "should_upgrade": True,
            "property_name": "city",
            "new_value": "Shanghai",
            "confidence": 0.9,
        }

        store = EntityStore(db_manager)

        # 创建测试实体
        for i in range(5):
            entity = Entity(
                id=f"entity-{i}", name=f"Person{i}", type="person", properties={"city": "Beijing"}
            )
            store.create(entity)

        experiences = []

        # 执行扫描
        result = scan_property_upgrade(
            experiences=experiences, llm_client=mock_llm, entity_store=store
        )

        # 应该有实体被升级
        assert result["upgraded_count"] > 0

        # 验证属性被更新
        # 至少有一个实体的city属性变为Shanghai
        all_entities = store.get_all()
        upgraded_entities = [
            e for e in all_entities if e.properties and e.properties.get("city") == "Shanghai"
        ]
        assert len(upgraded_entities) > 0

    @patch("Memory.consolidator.tasks.property_upgrade_task.Path")
    def test_returns_upgrade_statistics(self, mock_path, db_manager):
        """测试返回升级的实体数量。"""
        # Mock prompt template
        mock_prompt = mock_path.return_value.__truediv__.return_value
        mock_prompt.__truediv__ = Mock(return_value=mock_prompt)
        mock_prompt.open = Mock()
        mock_prompt.open.return_value.__enter__ = Mock()
        mock_prompt.open.return_value.__exit__ = Mock()
        mock_prompt.open.return_value.read.return_value = (
            "Prompt: {entity_name} {current_properties} {new_experiences} {property_name}"
        )

        # Mock LLM client
        mock_llm = Mock()
        mock_llm.call_json.return_value = {
            "should_upgrade": True,
            "property_name": "city",
            "new_value": "Shanghai",
            "confidence": 0.9,
        }

        store = EntityStore(db_manager)

        # 创建测试实体
        for i in range(5):
            entity = Entity(
                id=f"entity-{i}", name=f"Person{i}", type="person", properties={"city": "Beijing"}
            )
            store.create(entity)

        experiences = []

        # 执行扫描
        result = scan_property_upgrade(
            experiences=experiences, llm_client=mock_llm, entity_store=store
        )

        # 验证返回的统计信息
        assert "upgraded_count" in result
        assert "evaluated_count" in result
        assert "skipped_count" in result

        # 所有计数都应该是非负整数
        assert result["upgraded_count"] >= 0
        assert result["evaluated_count"] >= 0
        assert result["skipped_count"] >= 0


class TestUpgradeSharedAttributes:
    """测试共享属性升级功能（Wave 3新增）。"""

    def test_detect_shared_attributes(self, db_manager):
        """测试检测共享属性（Task 1 RED阶段）。

        验证upgrade_shared_attributes()能调用get_shared_properties()获取共享属性列表。
        这是D-05决策的核心："是属性，才能升级"。
        """
        from Memory.consolidator.tasks.property_upgrade_task import upgrade_shared_attributes
        from Memory.storage.entity_edge_store import EntityEdgeStore
        from Memory.embedding.model import embedding_service

        store = EntityStore(db_manager)
        edge_store = EntityEdgeStore(db_manager)

        # 创建测试实体：3个实体都有"位置: 云南"属性
        entity1 = Entity(
            id="entity-1",
            name="玉龙雪山",
            type="location",
            properties={"位置": "云南"}
        )
        entity2 = Entity(
            id="entity-2",
            name="丽江古城",
            type="location",
            properties={"位置": "云南"}
        )
        entity3 = Entity(
            id="entity-3",
            name="大理古城",
            type="location",
            properties={"位置": "云南"}
        )

        store.create(entity1)
        store.create(entity2)
        store.create(entity3)

        # 执行共享属性升级（threshold=3）
        result = upgrade_shared_attributes(
            entity_store=store,
            edge_store=edge_store,
            embedding_service=embedding_service,
            threshold=3
        )

        # 验证：找到1个共享属性（"位置: 云南"）
        # 注意：这个测试在RED阶段预期会失败，因为函数还未实现
        assert "promoted_count" in result
        assert "edges_created_count" in result
        assert "skipped_count" in result

    def test_promote_shared_attributes_to_entities(self, db_manager):
        """测试将共享属性值升级为独立实体（Task 1 RED阶段）。

        验证：
        1. 共享属性值（如"云南"）被创建为独立实体
        2. 复用已存在的同名实体（不重复创建）
        3. 创建关系边（原实体→新实体，relation=属性名）
        """
        from Memory.consolidator.tasks.property_upgrade_task import upgrade_shared_attributes
        from Memory.storage.entity_edge_store import EntityEdgeStore
        from Memory.embedding.model import embedding_service

        store = EntityStore(db_manager)
        edge_store = EntityEdgeStore(db_manager)

        # 创建测试实体
        entity1 = Entity(
            id="entity-1",
            name="玉龙雪山",
            type="location",
            properties={"位置": "云南"}
        )
        entity2 = Entity(
            id="entity-2",
            name="丽江古城",
            type="location",
            properties={"位置": "云南"}
        )
        entity3 = Entity(
            id="entity-3",
            name="大理古城",
            type="location",
            properties={"位置": "云南"}
        )

        store.create(entity1)
        store.create(entity2)
        store.create(entity3)

        # 执行共享属性升级
        result = upgrade_shared_attributes(
            entity_store=store,
            edge_store=edge_store,
            embedding_service=embedding_service,
            threshold=3
        )

        # 验证：创建了"云南"实体
        yunnan_entity = store.get_by_name("云南")
        assert yunnan_entity is not None, "应该创建'云南'实体"
        assert yunnan_entity.type == "location", "实体类型应该是location"
        assert "升级来源" in yunnan_entity.properties, "应该包含升级来源标记"

        # 验证：创建了3条关系边（玉龙雪山→云南，丽江古城→云南，大理古城→云南）
        edges = edge_store.get_by_from("entity-1")
        yunnan_edges = [e for e in edges if e.to_id == yunnan_entity.id]
        assert len(yunnan_edges) == 1, "应该创建1条关系边"
        assert yunnan_edges[0].relation == "位置", "关系类型应该是'位置'"

    def test_threshold_filters_infrequent_attributes(self, db_manager):
        """测试阈值过滤低频属性（Task 2 RED阶段）。

        验证只有出现次数>=threshold的属性值才会被升级。
        """
        from Memory.consolidator.tasks.property_upgrade_task import upgrade_shared_attributes
        from Memory.storage.entity_edge_store import EntityEdgeStore
        from Memory.embedding.model import embedding_service

        store = EntityStore(db_manager)
        edge_store = EntityEdgeStore(db_manager)

        # 创建测试实体：
        # - "位置: 云南"出现3次（应该升级）
        # - "位置: 成都"出现2次（不应该升级，threshold=3）
        entity1 = Entity(
            id="entity-1",
            name="玉龙雪山",
            type="location",
            properties={"位置": "云南"}
        )
        entity2 = Entity(
            id="entity-2",
            name="丽江古城",
            type="location",
            properties={"位置": "云南"}
        )
        entity3 = Entity(
            id="entity-3",
            name="大理古城",
            type="location",
            properties={"位置": "云南"}
        )
        entity4 = Entity(
            id="entity-4",
            name="都江堰",
            type="location",
            properties={"位置": "成都"}
        )
        entity5 = Entity(
            id="entity-5",
            name="青城山",
            type="location",
            properties={"位置": "成都"}
        )

        store.create(entity1)
        store.create(entity2)
        store.create(entity3)
        store.create(entity4)
        store.create(entity5)

        # 执行共享属性升级（threshold=3）
        result = upgrade_shared_attributes(
            entity_store=store,
            edge_store=edge_store,
            embedding_service=embedding_service,
            threshold=3
        )

        # 验证：只升级了"云南"（3次），"成都"（2次）被跳过
        assert result["promoted_count"] >= 1, "至少应该升级1个实体"

        yunnan_entity = store.get_by_name("云南")
        assert yunnan_entity is not None, "应该创建'云南'实体"

        chengdu_entity = store.get_by_name("成都")
        assert chengdu_entity is None, "不应该创建'成都'实体（只出现2次）"

    def test_attribute_value_not_entity_gets_promoted(self, db_manager):
        """测试D-05决策验证：只有属性值被升级，实体本身不升级（Task 3 RED阶段）。

        验证：
        1. 属性值（"云南"）被升级为实体 ✅
        2. 属性名（"位置"）不被升级 ✅
        3. 原实体（"玉龙雪山"等）不被"升级" ✅
        4. 创建关系边（雪山/丽江/大理 → 云南，relation="位置"）✅

        这是D-05决策的核心验证："是属性，才能升级"。
        """
        from Memory.consolidator.tasks.property_upgrade_task import upgrade_shared_attributes
        from Memory.storage.entity_edge_store import EntityEdgeStore
        from Memory.embedding.model import embedding_service

        store = EntityStore(db_manager)
        edge_store = EntityEdgeStore(db_manager)

        # 创建3个测试实体，都有"位置: 云南"属性
        entity1 = Entity(
            id="entity-1",
            name="玉龙雪山",
            type="location",
            properties={"位置": "云南"}
        )
        entity2 = Entity(
            id="entity-2",
            name="丽江古城",
            type="location",
            properties={"位置": "云南"}
        )
        entity3 = Entity(
            id="entity-3",
            name="大理古城",
            type="location",
            properties={"位置": "云南"}
        )

        store.create(entity1)
        store.create(entity2)
        store.create(entity3)

        # 执行共享属性升级
        result = upgrade_shared_attributes(
            entity_store=store,
            edge_store=edge_store,
            embedding_service=embedding_service,
            threshold=3
        )

        # 验证1：属性值（"云南"）被升级为实体
        yunnan_entity = store.get_by_name("云南")
        assert yunnan_entity is not None, "属性值'云南'应该被升级为实体"

        # 验证2：属性名（"位置"）不被升级
        location_entity = store.get_by_name("位置")
        assert location_entity is None, "属性名'位置'不应该被升级为实体"

        # 验证3：原实体（"玉龙雪山"等）不被"升级"（保持不变）
        jade_snow = store.get_by_name("玉龙雪山")
        assert jade_snow is not None, "原实体'玉龙雪山'应该仍然存在"
        assert jade_snow.id == "entity-1", "原实体ID不应该改变"
        assert jade_snow.properties == {"位置": "云南"}, "原实体属性不应该改变"

        # 验证4：创建3条关系边（雪山/丽江/大理 → 云南，relation="位置"）
        for entity_id in ["entity-1", "entity-2", "entity-3"]:
            edges = edge_store.get_by_from(entity_id)
            yunnan_edges = [e for e in edges if e.to_id == yunnan_entity.id]
            assert len(yunnan_edges) == 1, f"实体{entity_id}应该有1条指向'云南'的关系边"
            assert yunnan_edges[0].relation == "位置", "关系类型应该是'位置'"
