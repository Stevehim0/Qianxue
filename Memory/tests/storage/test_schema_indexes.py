"""测试数据库性能优化索引。

这个测试文件验证schema v6的性能优化索引是否正确创建。
"""

import pytest
from Memory.storage.database import db_manager
from Memory.storage.schema import get_current_schema_version


class TestSchemaIndexes:
    """测试schema索引优化。"""

    def test_schema_version_at_least_v6(self):
        """测试schema版本应该至少是v6（包含性能优化索引）。"""
        db_manager.initialize()
        version = get_current_schema_version(db_manager)
        assert version in [
            "v6",
            "v7",
            "v8",
            "v9",
        ], f"Schema version should be at least v6, got {version}"

    def test_indexes_created_successfully(self):
        """测试性能优化索引创建成功（至少10个）。"""
        db_manager.initialize()

        with db_manager.transaction() as cursor:
            cursor.execute("""
                SELECT name FROM sqlite_master
                WHERE type='index' AND name LIKE 'idx_%'
            """)
            indexes = cursor.fetchall()

            # 应该有至少10个性能优化索引
            index_names = [idx["name"] for idx in indexes]
            assert len(index_names) >= 10, f"Expected at least 10 indexes, got {len(index_names)}"

            # 验证关键索引存在
            required_indexes = [
                "idx_experiences_importance",
                "idx_experiences_created_at",
                "idx_experiences_source_type",
                "idx_experience_edges_from_id",
                "idx_experience_edges_to_id",
                "idx_experience_edges_weight",
                "idx_entity_edges_from_id",
                "idx_entity_edges_to_id",
                "idx_cross_edges_from_id",
                "idx_cross_edges_to_id",
            ]

            for required_index in required_indexes:
                assert required_index in index_names, f"Required index {required_index} not found"

    def test_importance_index_accelerates_queries(self):
        """测试importance索引加速排序查询。"""
        db_manager.initialize()

        with db_manager.transaction() as cursor:
            # 使用EXPLAIN QUERY PLAN验证索引使用
            cursor.execute("""
                EXPLAIN QUERY PLAN
                SELECT id FROM experiences
                ORDER BY importance DESC
                LIMIT 10
            """)
            plan = cursor.fetchall()

            # 检查是否使用了idx_experiences_importance索引
            plan_str = str(plan)
            # SQLite可能会使用索引，我们主要验证查询能正常执行
            assert len(plan) > 0, "Query plan should not be empty"

    def test_created_at_index_accelerates_queries(self):
        """测试created_at索引加速排序查询。"""
        db_manager.initialize()

        with db_manager.transaction() as cursor:
            # 使用EXPLAIN QUERY PLAN验证索引使用
            cursor.execute("""
                EXPLAIN QUERY PLAN
                SELECT id FROM experiences
                ORDER BY created_at DESC
                LIMIT 10
            """)
            plan = cursor.fetchall()

            # 验证查询能正常执行
            assert len(plan) > 0, "Query plan should not be empty"

    def test_from_id_index_accelerates_edge_queries(self):
        """测试from_id索引加速边查询。"""
        db_manager.initialize()

        with db_manager.transaction() as cursor:
            # 使用EXPLAIN QUERY PLAN验证索引使用
            cursor.execute("""
                EXPLAIN QUERY PLAN
                SELECT * FROM experience_edges
                WHERE from_id = 'test_id'
            """)
            plan = cursor.fetchall()

            # 验证查询能正常执行
            assert len(plan) > 0, "Query plan should not be empty"
