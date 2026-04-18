"""存储层CRUD测试模块。

测试所有Store模块的增删改查操作：
- ExperienceStore: 体验节点
- ExperienceEdgeStore: 体验层边
- EntityStore: 信息层实体
- EntityEdgeStore: 信息层关系边
- CrossEdgeStore: 跨层边
- CoreStore: 核心层（单行表）
- StateStore: 状态层（单行表）
- ProfileStore: 个人档案
"""

import pytest
import numpy as np

from Memory.storage.experience_store import ExperienceStore, Experience
from Memory.storage.experience_edge_store import ExperienceEdgeStore, ExperienceEdge
from Memory.storage.entity_store import EntityStore, Entity
from Memory.storage.entity_edge_store import EntityEdgeStore, EntityEdge
from Memory.storage.cross_edge_store import CrossEdgeStore, CrossEdge
from Memory.storage.core_store import CoreStore, Core
from Memory.storage.state_store import StateStore, State
from Memory.storage.profile_store import ProfileStore, PersonProfile


class TestExperienceStore:
    """测试ExperienceStore。"""

    def test_create_experience(self, memory_db, test_data):
        """测试创建体验节点。"""
        store = ExperienceStore(memory_db)

        exp = Experience(
            id=test_data["experience"]["id"],
            L0_text=test_data["experience"]["L0_text"],
            L3_raw=test_data["experience"]["L3_raw"],
            emotion_category=test_data["experience"]["emotion_category"],
            emotion_intensity=test_data["experience"]["emotion_intensity"],
        )

        exp_id = store.create(exp)
        assert exp_id == test_data["experience"]["id"]

        # 验证创建成功
        retrieved = store.get(exp_id)
        assert retrieved is not None
        assert retrieved.id == exp_id
        assert retrieved.L3_raw == test_data["experience"]["L3_raw"]

    def test_embedding_blob_serialization(self, memory_db, test_data):
        """测试embedding字段的BLOB序列化。"""
        store = ExperienceStore(memory_db)

        # 创建带embedding的体验
        exp = Experience(
            id="test_blob_001",
            L0_text="测试BLOB序列化",
            L3_raw="测试内容",
            L0_embedding=test_data["embedding"],
        )

        store.create(exp)

        # 读取并验证embedding
        retrieved = store.get("test_blob_001")
        assert retrieved.L0_embedding is not None
        assert retrieved.L0_embedding.shape == (768,)
        assert retrieved.L0_embedding.dtype == np.float32
        np.testing.assert_array_almost_equal(retrieved.L0_embedding, test_data["embedding"])

    def test_update_experience(self, memory_db):
        """测试更新体验节点。"""
        store = ExperienceStore(memory_db)

        exp = Experience(
            id="test_update_001",
            L3_raw="原始内容",
            L0_text="原始摘要",
        )
        store.create(exp)

        # 更新
        exp.L0_text = "更新后的摘要"
        exp.L1_text = "补充的L1内容"
        success = store.update(exp)

        assert success is True
        retrieved = store.get("test_update_001")
        assert retrieved.L0_text == "更新后的摘要"
        assert retrieved.L1_text == "补充的L1内容"

    def test_delete_experience(self, memory_db):
        """测试删除体验节点。"""
        store = ExperienceStore(memory_db)

        exp = Experience(id="test_delete_001", L3_raw="待删除")
        store.create(exp)

        # 删除
        success = store.delete("test_delete_001")
        assert success is True

        # 验证删除
        retrieved = store.get("test_delete_001")
        assert retrieved is None

    def test_count(self, memory_db, sample_experiences):
        """测试统计体验节点数量。"""
        store = ExperienceStore(memory_db)

        # 创建多个体验
        for exp in sample_experiences:
            store.create(exp)

        assert store.count() == len(sample_experiences)


class TestEntityStore:
    """测试EntityStore。"""

    def test_create_entity(self, memory_db, test_data):
        """测试创建实体。"""
        store = EntityStore(memory_db)

        entity = Entity(
            id=test_data["entity"]["id"],
            name=test_data["entity"]["name"],
            type=test_data["entity"]["type"],
            properties=test_data["entity"]["properties"],
        )

        entity_id = store.create(entity)
        assert entity_id == test_data["entity"]["id"]

    def test_unique_name_constraint(self, memory_db):
        """测试name字段的UNIQUE约束。"""
        store = EntityStore(memory_db)

        entity1 = Entity(id="entity_001", name="张三", type="person")
        entity2 = Entity(id="entity_002", name="张三", type="person")

        store.create(entity1)

        # 第二个同名实体应该失败
        with pytest.raises(Exception):  # IntegrityError
            store.create(entity2)

    def test_get_by_name(self, memory_db):
        """测试根据名称获取实体。"""
        store = EntityStore(memory_db)

        entity = Entity(id="entity_001", name="李四", type="person")
        store.create(entity)

        retrieved = store.get_by_name("李四")
        assert retrieved is not None
        assert retrieved.name == "李四"

    def test_json_serialization(self, memory_db):
        """测试properties字段的JSON序列化。"""
        store = EntityStore(memory_db)

        properties = {
            "age": 30,
            "occupation": "工程师",
            "hobbies": ["阅读", "编程"],
        }

        entity = Entity(
            id="entity_json_001",
            name="测试JSON",
            type="person",
            properties=properties,
        )
        store.create(entity)

        # 读取并验证
        retrieved = store.get("entity_json_001")
        assert retrieved.properties == properties

    def test_embedding_blob(self, memory_db, test_data):
        """测试embedding字段的BLOB存储。"""
        store = EntityStore(memory_db)

        entity = Entity(
            id="entity_blob_001",
            name="测试BLOB",
            type="person",
            embedding=test_data["embedding"],
        )
        store.create(entity)

        # 读取并验证
        retrieved = store.get("entity_blob_001")
        assert retrieved.embedding is not None
        assert retrieved.embedding.shape == (768,)


class TestEntityEdgeStore:
    """测试EntityEdgeStore。"""

    def test_create_edge(self, memory_db, test_data):
        """测试创建关系边。"""
        # 先创建实体
        entity_store = EntityStore(memory_db)
        entity_store.create(Entity(id="entity_001", name="A", type="person"))
        entity_store.create(Entity(id="entity_002", name="B", type="person"))

        # 创建边
        edge_store = EntityEdgeStore(memory_db)
        edge = EntityEdge(
            from_id="entity_001",
            to_id="entity_002",
            relation="朋友",
            confidence=0.8,
        )
        edge_id = edge_store.create(edge)

        assert edge_id > 0

    def test_get_by_from(self, memory_db):
        """测试获取从指定实体出发的边。"""
        entity_store = EntityStore(memory_db)
        entity_store.create(Entity(id="e1", name="A", type="person"))
        entity_store.create(Entity(id="e2", name="B", type="person"))
        entity_store.create(Entity(id="e3", name="C", type="person"))

        edge_store = EntityEdgeStore(memory_db)
        edge_store.create(EntityEdge(from_id="e1", to_id="e2", relation="关系1"))
        edge_store.create(EntityEdge(from_id="e1", to_id="e3", relation="关系2"))

        edges = edge_store.get_by_from("e1")
        assert len(edges) == 2


class TestCrossEdgeStore:
    """测试CrossEdgeStore。"""

    def test_create_cross_edge(self, memory_db):
        """测试创建跨层边。"""
        # 创建测试数据和实体
        exp_store = ExperienceStore(memory_db)
        exp_store.create(Experience(id="exp_001", L3_raw="测试体验"))

        entity_store = EntityStore(memory_db)
        entity_store.create(Entity(id="entity_001", name="测试", type="person"))

        # 创建跨层边
        cross_store = CrossEdgeStore(memory_db)
        edge = CrossEdge(
            from_id="exp_001",
            to_id="entity_001",
            context="体验中提到",
        )
        edge_id = cross_store.create(edge)

        assert edge_id > 0


@pytest.mark.skip(reason="core_store 已废弃，数据现通过 Backend HTTP API 获取")
class TestCoreStore:
    """测试CoreStore（单行表）— 已废弃。"""

    def test_single_row_constraint(self, memory_db):
        """测试单行表约束。"""
        store = CoreStore(memory_db)

        core = store.get()
        assert core.id == 1

        # 再次获取，应该是同一个id
        core2 = store.get()
        assert core2.id == 1

    def test_update_stable_layer(self, memory_db):
        """测试更新稳定层。"""
        store = CoreStore(memory_db)

        success = store.update_stable_layer("新的稳定层内容", reason="测试更新")
        assert success is True

        core = store.get()
        assert core.stable_text == "新的稳定层内容"

    def test_anchors_json(self, memory_db):
        """测试anchors字段的JSON序列化。"""
        store = CoreStore(memory_db)

        # 清理可能存在的旧行和初始化标志，确保测试独立性
        with memory_db.transaction() as cursor:
            cursor.execute("DELETE FROM core WHERE id = ?", (store.SINGLE_ROW_ID,))
        store._initialized = False  # 重置初始化标志

        # 先get()创建默认行，然后update
        store.get()
        new_anchors = {
            "bottom_lines": ["底线1", "底线2"],
            "style_keywords": ["关键词1"],
        }
        store.update_anchors(new_anchors)

        core = store.get()
        assert core.anchors == new_anchors


class TestStateStore:
    """测试StateStore（单行表）。"""

    def test_single_row_constraint(self, memory_db):
        """测试单行表约束。"""
        store = StateStore(memory_db)

        state = store.get()
        assert state.id == 1

    def test_update_mood(self, memory_db):
        """测试更新情感状态。"""
        store = StateStore(memory_db)

        # 清理可能存在的旧行和初始化标志，确保测试独立性
        with memory_db.transaction() as cursor:
            cursor.execute("DELETE FROM state WHERE id = ?", (store.SINGLE_ROW_ID,))
        store._initialized = False  # 重置初始化标志

        # 先get()创建默认行，然后update
        store.get()
        store.update_mood(valence=0.8, arousal=0.9)

        state = store.get()
        assert state.mood_valence == 0.8
        assert state.mood_arousal == 0.9
        assert state.mood_label == "兴奋"

    def test_update_energy(self, memory_db):
        """测试更新精力。"""
        store = StateStore(memory_db)

        # 清理可能存在的旧行和初始化标志，确保测试独立性
        with memory_db.transaction() as cursor:
            cursor.execute("DELETE FROM state WHERE id = ?", (store.SINGLE_ROW_ID,))
        store._initialized = False  # 重置初始化标志

        # 先get()创建默认行，然后update
        store.get()
        store.update_energy(value=0.9)

        state = store.get()
        assert state.energy_value == 0.9
        assert state.energy_label == "充沛"

    def test_auto_label_generation(self, memory_db):
        """测试自动标签生成。"""
        store = StateStore(memory_db)

        # 清理可能存在的旧行和初始化标志，确保测试独立性
        with memory_db.transaction() as cursor:
            cursor.execute("DELETE FROM state WHERE id = ?", (store.SINGLE_ROW_ID,))
        store._initialized = False  # 重置初始化标志

        # 先get()创建默认行，然后update
        store.get()

        # 测试不同情感组合的标签
        # 注意：当前代码逻辑中arousal < 0.3会优先匹配"平静"
        store.update_mood(valence=0.8, arousal=0.8)
        assert store.get().mood_label == "兴奋"

        store.update_mood(valence=-0.5, arousal=0.8)
        assert store.get().mood_label == "愤怒"

        store.update_mood(valence=0.0, arousal=0.2)
        assert store.get().mood_label == "平静"


class TestProfileStore:
    """测试ProfileStore。"""

    def test_create_profile(self, memory_db, test_data):
        """测试创建个人档案。"""
        store = ProfileStore(memory_db)

        profile = PersonProfile(
            id=test_data["profile"]["id"],
            basic=test_data["profile"]["basic"],
            interaction_style=test_data["profile"]["interaction_style"],
            preferences=test_data["profile"]["preferences"],
        )

        profile_id = store.create(profile)
        assert profile_id == test_data["profile"]["id"]

    def test_get_by_name(self, memory_db):
        """测试根据人名获取档案。"""
        store = ProfileStore(memory_db)

        profile = PersonProfile(
            id="profile_张三",
            basic={"name": "张三"},
        )
        store.create(profile)

        retrieved = store.get_by_name("张三")
        assert retrieved is not None
        assert retrieved.id == "profile_张三"

    def test_json_fields(self, memory_db, test_data):
        """测试JSON字段的序列化。"""
        store = ProfileStore(memory_db)

        profile = PersonProfile(
            id="profile_json_test",
            basic=test_data["profile"]["basic"],
            interaction_style=test_data["profile"]["interaction_style"],
            preferences=test_data["profile"]["preferences"],
        )
        store.create(profile)

        retrieved = store.get("profile_json_test")
        assert retrieved.basic == test_data["profile"]["basic"]
        assert retrieved.interaction_style == test_data["profile"]["interaction_style"]
        assert retrieved.preferences == test_data["profile"]["preferences"]
