"""测试数据类扩展功能。

测试覆盖：
- Experience数据类包含4个衰减字段
- ExperienceEdge数据类包含dormant字段
- ExperienceStore.create()包含新字段INSERT
- ExperienceStore._from_row()包含新字段解析
- ExperienceStore.update_decayed_fields()方法功能
- ExperienceEdgeStore.create()包含dormant字段INSERT
- ExperienceEdgeStore._from_row()包含dormant字段解析
- ExperienceEdgeStore.set_dormant()方法功能
- ExperienceEdgeStore.update_decayed_weight()方法功能
"""

import pytest
import tempfile
import os
from datetime import datetime
import numpy as np

from Memory.storage.experience_store import ExperienceStore, Experience
from Memory.storage.experience_edge_store import ExperienceEdgeStore, ExperienceEdge
from Memory.storage.schema import create_all_tables, migrate_to_v3
from Memory.storage.database import DatabaseManager


@pytest.fixture
def temp_db():
    """创建临时数据库实例。"""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db_manager = DatabaseManager(db_path=db_path)
    create_all_tables(db_manager)
    migrate_to_v3(db_manager)
    yield db_manager
    os.unlink(db_path)


@pytest.fixture
def experience_store(temp_db):
    """创建ExperienceStore实例。"""
    return ExperienceStore(temp_db)


@pytest.fixture
def edge_store(temp_db):
    """创建ExperienceEdgeStore实例。"""
    return ExperienceEdgeStore(temp_db)


class TestExperienceDataclassExtensions:
    """测试Experience数据类扩展。"""

    def test_experience_has_decay_fields(self):
        """测试1: Experience数据类包含4个衰减字段。"""
        exp = Experience(
            id="test_001",
            L3_raw="test content",
            L0_decayed=0.9,
            L1_decayed=0.8,
            L2_decayed=0.7,
            L3_decayed=0.6,
        )

        assert exp.L0_decayed == 0.9
        assert exp.L1_decayed == 0.8
        assert exp.L2_decayed == 0.7
        assert exp.L3_decayed == 0.6

    def test_experience_decay_fields_optional(self):
        """测试2: Experience衰减字段是Optional类型。"""
        exp = Experience(id="test_002", L3_raw="test")

        assert exp.L0_decayed is None
        assert exp.L1_decayed is None
        assert exp.L2_decayed is None
        assert exp.L3_decayed is None


class TestExperienceEdgeDataclassExtensions:
    """测试ExperienceEdge数据类扩展。"""

    def test_edge_has_dormant_field(self):
        """测试3: ExperienceEdge数据类包含dormant字段。"""
        edge = ExperienceEdge(from_id="exp_001", to_id="exp_002", type="temporal", dormant=1)

        assert edge.dormant == 1

    def test_edge_dormant_default_zero(self):
        """测试4: ExperienceEdge的dormant字段默认值为0。"""
        edge = ExperienceEdge(from_id="exp_001", to_id="exp_002", type="temporal")

        assert edge.dormant == 0


class TestExperienceStoreExtensions:
    """测试ExperienceStore扩展功能。"""

    def test_create_with_decay_fields(self, experience_store):
        """测试5: ExperienceStore.create()包含新字段INSERT。"""
        exp = Experience(
            id="test_create_001",
            L3_raw="original content",
            L0_text="summary",
            L0_decayed=0.95,
            L1_decayed=0.85,
            L2_decayed=0.75,
            L3_decayed=0.65,
        )

        exp_id = experience_store.create(exp)
        assert exp_id == "test_create_001"

        # 验证数据正确存储
        retrieved = experience_store.get(exp_id)
        assert retrieved is not None
        assert retrieved.L0_decayed == 0.95
        assert retrieved.L1_decayed == 0.85
        assert retrieved.L2_decayed == 0.75
        assert retrieved.L3_decayed == 0.65

    def test_from_row_parses_decay_fields(self, experience_store):
        """测试6: ExperienceStore._from_row()包含新字段解析。"""
        # 先创建一个experience
        exp = Experience(id="test_parse_001", L3_raw="content", L0_decayed=0.88)
        experience_store.create(exp)

        # 再读取回来
        retrieved = experience_store.get("test_parse_001")
        assert retrieved is not None
        assert retrieved.L0_decayed == 0.88
        assert retrieved.L1_decayed is None  # 没有设置的字段应该是None
        assert retrieved.L2_decayed is None
        assert retrieved.L3_decayed is None

    def test_update_decayed_fields(self, experience_store):
        """测试7: ExperienceStore.update_decayed_fields()方法功能。"""
        # 创建experience
        exp = Experience(id="test_update_001", L3_raw="content")
        experience_store.create(exp)

        # 更新衰减字段
        exp.L0_decayed = 0.5
        exp.L1_decayed = 0.4
        exp.L2_decayed = 0.3
        exp.L3_decayed = 0.2

        success = experience_store.update_decayed_fields(exp)
        assert success is True

        # 验证更新成功
        retrieved = experience_store.get("test_update_001")
        assert retrieved.L0_decayed == 0.5
        assert retrieved.L1_decayed == 0.4
        assert retrieved.L2_decayed == 0.3
        assert retrieved.L3_decayed == 0.2

    def test_create_with_none_decay_fields(self, experience_store):
        """测试8: 创建experience时衰减字段可以为None。"""
        exp = Experience(id="test_none_001", L3_raw="content", L0_decayed=None, L1_decayed=None)

        exp_id = experience_store.create(exp)
        assert exp_id == "test_none_001"

        retrieved = experience_store.get(exp_id)
        assert retrieved.L0_decayed is None
        assert retrieved.L1_decayed is None


class TestExperienceEdgeStoreExtensions:
    """测试ExperienceEdgeStore扩展功能。"""

    def test_create_with_dormant_field(self, edge_store, experience_store):
        """测试9: ExperienceEdgeStore.create()包含dormant字段INSERT。"""
        # 先创建两个experience节点
        exp1 = Experience(id="edge_test_001", L3_raw="content1")
        exp2 = Experience(id="edge_test_002", L3_raw="content2")
        experience_store.create(exp1)
        experience_store.create(exp2)

        # 创建边
        edge = ExperienceEdge(
            from_id="edge_test_001", to_id="edge_test_002", type="temporal", dormant=1
        )

        edge_id = edge_store.create(edge)
        assert edge_id > 0

        # 验证数据正确存储
        retrieved = edge_store.get(edge_id)
        assert retrieved is not None
        assert retrieved.dormant == 1

    def test_from_row_parses_dormant_field(self, edge_store, experience_store):
        """测试10: ExperienceEdgeStore._from_row()包含dormant字段解析。"""
        # 先创建experience节点
        exp1 = Experience(id="parse_edge_001", L3_raw="content1")
        exp2 = Experience(id="parse_edge_002", L3_raw="content2")
        experience_store.create(exp1)
        experience_store.create(exp2)

        # 创建边
        edge = ExperienceEdge(
            from_id="parse_edge_001", to_id="parse_edge_002", type="thematic", dormant=0
        )
        edge_store.create(edge)

        # 读取回来
        retrieved = edge_store.get_by_from("parse_edge_001")[0]
        assert retrieved.dormant == 0

    def test_set_dormant(self, edge_store, experience_store):
        """测试11: ExperienceEdgeStore.set_dormant()方法功能。"""
        # 先创建experience节点
        exp1 = Experience(id="dormant_test_001", L3_raw="content1")
        exp2 = Experience(id="dormant_test_002", L3_raw="content2")
        experience_store.create(exp1)
        experience_store.create(exp2)

        # 创建边（默认dormant=0）
        edge = ExperienceEdge(from_id="dormant_test_001", to_id="dormant_test_002", type="causal")
        edge_id = edge_store.create(edge)

        # 设置为休眠
        success = edge_store.set_dormant(edge_id, True)
        assert success is True

        # 验证
        retrieved = edge_store.get(edge_id)
        assert retrieved.dormant == 1

        # 设置为活跃
        success = edge_store.set_dormant(edge_id, False)
        assert success is True

        retrieved = edge_store.get(edge_id)
        assert retrieved.dormant == 0

    def test_update_decayed_weight(self, edge_store, experience_store):
        """测试12: ExperienceEdgeStore.update_decayed_weight()方法功能。"""
        # 先创建experience节点
        exp1 = Experience(id="weight_test_001", L3_raw="content1")
        exp2 = Experience(id="weight_test_002", L3_raw="content2")
        experience_store.create(exp1)
        experience_store.create(exp2)

        # 创建边
        edge = ExperienceEdge(
            from_id="weight_test_001",
            to_id="weight_test_002",
            type="associative",
            decayed_weight=1.0,
        )
        edge_id = edge_store.create(edge)

        # 更新衰减权重
        success = edge_store.update_decayed_weight(edge_id, 0.5)
        assert success is True

        # 验证
        retrieved = edge_store.get(edge_id)
        assert retrieved.decayed_weight == 0.5

    def test_dormant_default_in_create(self, edge_store, experience_store):
        """测试13: 创建边时dormant字段使用默认值0。"""
        # 先创建experience节点
        exp1 = Experience(id="default_test_001", L3_raw="content1")
        exp2 = Experience(id="default_test_002", L3_raw="content2")
        experience_store.create(exp1)
        experience_store.create(exp2)

        # 创建边（不指定dormant）
        edge = ExperienceEdge(from_id="default_test_001", to_id="default_test_002", type="temporal")
        edge_id = edge_store.create(edge)

        # 验证默认值
        retrieved = edge_store.get(edge_id)
        assert retrieved.dormant == 0


class TestBackwardCompatibility:
    """测试向后兼容性。"""

    def test_old_data_without_decay_fields(self, experience_store, temp_db):
        """测试14: 旧数据（不含衰减字段）可以正常读取。"""
        # 手动插入一条不含衰减字段的数据（模拟旧数据）
        with temp_db.transaction() as cursor:
            cursor.execute(
                """
                INSERT INTO experiences (id, L3_raw, created_at)
                VALUES (?, ?, ?)
            """,
                ("old_data_001", "old content", datetime.now().isoformat()),
            )

        # 读取应该成功，衰减字段为None
        retrieved = experience_store.get("old_data_001")
        assert retrieved is not None
        assert retrieved.L3_raw == "old content"
        assert retrieved.L0_decayed is None
        assert retrieved.L1_decayed is None
        assert retrieved.L2_decayed is None
        assert retrieved.L3_decayed is None

    def test_old_edge_without_dormant_field(self, edge_store, experience_store, temp_db):
        """测试15: 旧边（不含dormant字段）可以正常读取。"""
        # 先创建experience节点
        exp1 = Experience(id="old_edge_001", L3_raw="content1")
        exp2 = Experience(id="old_edge_002", L3_raw="content2")
        experience_store.create(exp1)
        experience_store.create(exp2)

        # 手动插入一条不含dormant字段的边（模拟旧数据）
        with temp_db.transaction() as cursor:
            cursor.execute(
                """
                INSERT INTO experience_edges (from_id, to_id, type, weight, created_at)
                VALUES (?, ?, ?, ?, ?)
            """,
                ("old_edge_001", "old_edge_002", "temporal", 1.0, datetime.now().isoformat()),
            )

        # 读取应该成功，dormant字段使用默认值0
        retrieved = edge_store.get_by_from("old_edge_001")[0]
        assert retrieved is not None
        assert retrieved.dormant == 0
