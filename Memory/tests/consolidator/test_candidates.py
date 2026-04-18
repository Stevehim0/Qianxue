"""巩固层存储层查询测试。

测试 ExperienceStore 的巩固层相关查询方法。
"""

import pytest
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from Memory.storage.database import DatabaseManager
from Memory.storage.experience_store import ExperienceStore, Experience
from Memory.storage.schema import create_all_tables


class TestGetConsolidationCandidates:
    """测试 get_consolidation_candidates() 方法。"""

    def test_incremental_mode_returns_unconsolidated_nodes(self):
        """测试增量模式返回 consolidated=0 的节点。"""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db_manager = DatabaseManager(db_path=str(db_path))
            create_all_tables(db_manager)

            store = ExperienceStore(db_manager)

            # 创建测试数据：3个未巩固，2个已巩固
            now = datetime.now()
            for i in range(3):
                exp = Experience(
                    id=f"exp_unconsolidated_{i}",
                    L3_raw=f"Unconsolidated content {i}",
                    consolidated=0,
                    created_at=(now - timedelta(hours=i)).isoformat(),
                )
                store.create(exp)

            for i in range(2):
                exp = Experience(
                    id=f"exp_consolidated_{i}",
                    L3_raw=f"Consolidated content {i}",
                    consolidated=1,
                    created_at=(now - timedelta(hours=i)).isoformat(),
                )
                store.create(exp)

            # 查询增量模式
            candidates = store.get_consolidation_candidates(batch_size=10, mode="incremental")

            assert len(candidates) == 3
            assert all(exp.consolidated == 0 for exp in candidates)

    def test_full_mode_returns_recent_nodes(self):
        """测试全量模式返回最近 N 天的节点。"""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db_manager = DatabaseManager(db_path=str(db_path))
            create_all_tables(db_manager)

            store = ExperienceStore(db_manager)

            # 创建测试数据：最近3天内5个，更早2个
            now = datetime.now()
            for i in range(5):
                exp = Experience(
                    id=f"exp_recent_{i}",
                    L3_raw=f"Recent content {i}",
                    consolidated=1,
                    created_at=(now - timedelta(days=i)).isoformat(),
                )
                store.create(exp)

            for i in range(2):
                exp = Experience(
                    id=f"exp_old_{i}",
                    L3_raw=f"Old content {i}",
                    consolidated=0,
                    created_at=(now - timedelta(days=10 + i)).isoformat(),
                )
                store.create(exp)

            # 查询全量模式（最近7天）
            candidates = store.get_consolidation_candidates(batch_size=10, mode="full", days=7)

            assert len(candidates) == 5
            assert all(exp.id.startswith("exp_recent_") for exp in candidates)

    def test_results_sorted_by_created_at_asc(self):
        """测试结果按 created_at 升序排序（旧节点优先）。"""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db_manager = DatabaseManager(db_path=str(db_path))
            create_all_tables(db_manager)

            store = ExperienceStore(db_manager)

            # 创建测试数据（乱序时间）
            now = datetime.now()
            times = [3, 1, 4, 2, 0]  # 小时前
            for i, hours_ago in enumerate(times):
                exp = Experience(
                    id=f"exp_{i}",
                    L3_raw=f"Content {i}",
                    consolidated=0,
                    created_at=(now - timedelta(hours=hours_ago)).isoformat(),
                )
                store.create(exp)

            # 查询增量模式
            candidates = store.get_consolidation_candidates(batch_size=10, mode="incremental")

            # 验证升序排序
            created_ats = [exp.created_at for exp in candidates]
            assert created_ats == sorted(created_ats)

    def test_batch_size_limits_return_count(self):
        """测试 batch_size 限制返回数量。"""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db_manager = DatabaseManager(db_path=str(db_path))
            create_all_tables(db_manager)

            store = ExperienceStore(db_manager)

            # 创建10个未巩固节点
            now = datetime.now()
            for i in range(10):
                exp = Experience(
                    id=f"exp_{i}",
                    L3_raw=f"Content {i}",
                    consolidated=0,
                    created_at=(now - timedelta(hours=i)).isoformat(),
                )
                store.create(exp)

            # 查询 batch_size=5
            candidates = store.get_consolidation_candidates(batch_size=5, mode="incremental")

            assert len(candidates) == 5


class TestUpdateConsolidatedBatch:
    """测试 update_consolidated_batch() 方法。"""

    def test_batch_update_consolidated_mark(self):
        """测试批量更新 consolidated 标记。"""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db_manager = DatabaseManager(db_path=str(db_path))
            create_all_tables(db_manager)

            store = ExperienceStore(db_manager)

            # 创建5个未巩固节点
            now = datetime.now()
            exp_ids = []
            for i in range(5):
                exp_id = f"exp_{i}"
                exp_ids.append(exp_id)
                exp = Experience(
                    id=exp_id,
                    L3_raw=f"Content {i}",
                    consolidated=0,
                    created_at=(now - timedelta(hours=i)).isoformat(),
                )
                store.create(exp)

            # 批量更新为已巩固
            updated_count = store.update_consolidated_batch(exp_ids, consolidated=True)

            assert updated_count == 5

            # 验证更新结果
            for exp_id in exp_ids:
                exp = store.get(exp_id)
                assert exp.consolidated == 1

    def test_batch_update_to_unconsolidated(self):
        """测试批量更新为未巩固状态。"""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db_manager = DatabaseManager(db_path=str(db_path))
            create_all_tables(db_manager)

            store = ExperienceStore(db_manager)

            # 创建已巩固节点
            now = datetime.now()
            exp_ids = []
            for i in range(3):
                exp_id = f"exp_{i}"
                exp_ids.append(exp_id)
                exp = Experience(
                    id=exp_id,
                    L3_raw=f"Content {i}",
                    consolidated=1,
                    created_at=(now - timedelta(hours=i)).isoformat(),
                )
                store.create(exp)

            # 批量更新为未巩固
            updated_count = store.update_consolidated_batch(exp_ids, consolidated=False)

            assert updated_count == 3

            # 验证更新结果
            for exp_id in exp_ids:
                exp = store.get(exp_id)
                assert exp.consolidated == 0

    def test_empty_id_list_returns_zero(self):
        """测试空 ID 列表返回 0。"""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db_manager = DatabaseManager(db_path=str(db_path))
            create_all_tables(db_manager)

            store = ExperienceStore(db_manager)

            updated_count = store.update_consolidated_batch([], consolidated=True)

            assert updated_count == 0


class TestUpdateL1L2:
    """测试 update_l1l2() 方法。"""

    def test_update_l1l2_fields(self):
        """测试更新 L1_text 和 L2_text 字段。"""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db_manager = DatabaseManager(db_path=str(db_path))
            create_all_tables(db_manager)

            store = ExperienceStore(db_manager)

            # 创建测试节点
            exp = Experience(id="exp_test", L3_raw="Original content", L1_text=None, L2_text=None)
            store.create(exp)

            # 更新 L1/L2
            success = store.update_l1l2(
                experience_id="exp_test", l1_text="Key point 1", l2_text="Detail 1"
            )

            assert success is True

            # 验证更新结果
            updated_exp = store.get("exp_test")
            assert updated_exp.L1_text == "Key point 1"
            assert updated_exp.L2_text == "Detail 1"

    def test_update_l1_only(self):
        """测试只更新 L1_text（L2 保持 None）。"""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db_manager = DatabaseManager(db_path=str(db_path))
            create_all_tables(db_manager)

            store = ExperienceStore(db_manager)

            # 创建测试节点
            exp = Experience(id="exp_test", L3_raw="Original content", L1_text=None, L2_text=None)
            store.create(exp)

            # 只更新 L1
            success = store.update_l1l2(experience_id="exp_test", l1_text="Key point only")

            assert success is True

            # 验证更新结果
            updated_exp = store.get("exp_test")
            assert updated_exp.L1_text == "Key point only"
            assert updated_exp.L2_text is None

    def test_update_nonexistent_experience_returns_false(self):
        """测试更新不存在的节点返回 False。"""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db_manager = DatabaseManager(db_path=str(db_path))
            create_all_tables(db_manager)

            store = ExperienceStore(db_manager)

            success = store.update_l1l2(
                experience_id="nonexistent", l1_text="Key point", l2_text="Detail"
            )

            assert success is False


class TestUpdateImportance:
    """测试 update_importance() 方法。"""

    def test_update_importance_field(self):
        """测试更新 importance 字段。"""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db_manager = DatabaseManager(db_path=str(db_path))
            create_all_tables(db_manager)

            store = ExperienceStore(db_manager)

            # 创建测试节点
            exp = Experience(id="exp_test", L3_raw="Original content", importance=0.5)
            store.create(exp)

            # 更新重要度
            success = store.update_importance(experience_id="exp_test", importance=0.8)

            assert success is True

            # 验证更新结果
            updated_exp = store.get("exp_test")
            assert updated_exp.importance == 0.8

    def test_update_nonexistent_experience_returns_false(self):
        """测试更新不存在的节点返回 False。"""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db_manager = DatabaseManager(db_path=str(db_path))
            create_all_tables(db_manager)

            store = ExperienceStore(db_manager)

            success = store.update_importance(experience_id="nonexistent", importance=0.9)

            assert success is False
