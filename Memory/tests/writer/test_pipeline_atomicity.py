"""测试WriterPipeline原子性修复

验证延迟写入架构确保：
1. 正常情况下，所有数据完整写入
2. 任何步骤失败时，数据库中没有"半成品"记录
"""

import pytest
import tempfile
import os
from pathlib import Path

from Memory.writer.pipeline import WriterPipeline
from Memory.storage.experience_store import ExperienceStore
from Memory.storage.entity_store import EntityStore
from Memory.storage.database import db_manager
from Memory.config.settings import settings


@pytest.fixture
def temp_db():
    """创建临时数据库"""
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    temp_path = temp_file.name
    temp_file.close()

    # 更新配置使用临时数据库
    original_db_path = settings.database_path
    settings.database_path = temp_path

    # 初始化数据库
    db_manager.initialize()

    yield temp_path

    # 清理
    settings.database_path = original_db_path
    if os.path.exists(temp_path):
        os.remove(temp_path)


@pytest.fixture
def pipeline(temp_db):
    """创建测试用的WriterPipeline实例"""
    return WriterPipeline()


class TestPipelineAtomicity:
    """测试WriterPipeline原子性"""

    def test_normal_processing_complete_data(self, pipeline):
        """测试正常情况：所有数据完整写入"""
        dialogue = """
        张三：你好，我想学习Python
        AI：好的，Python是一门很好的编程语言
        张三：请给我一些学习建议
        """

        # 执行处理
        exp_id = pipeline.process_event(dialogue=dialogue)

        # 验证体验节点存在
        exp_store = ExperienceStore()
        experience = exp_store.get(exp_id)
        assert experience is not None
        assert experience.L3_raw == dialogue.strip()
        assert experience.L0_text is not None  # L0摘要应该存在
        assert experience.L0_embedding is not None  # L0向量应该存在

        # 验证实体存在
        entity_store = EntityStore()
        entities = entity_store.get_by_experience(exp_id)
        assert len(entities) > 0  # 应该有实体被提取

        print(f"✅ 正常处理测试通过：体验节点{exp_id}，包含{len(entities)}个实体")

    def test_llm_failure_no_data_written(self, pipeline, monkeypatch):
        """测试LLM调用失败：不应该有任何数据写入数据库"""
        dialogue = "测试对话"

        # Mock LLM调用失败
        def mock_generate_fail(*args, **kwargs):
            raise Exception("LLM调用失败")

        monkeypatch.setattr(pipeline.llm_client, 'call_with_retry', mock_generate_fail)

        # 执行处理，预期失败
        with pytest.raises(Exception, match="LLM调用失败"):
            pipeline.process_event(dialogue=dialogue)

        # 验证数据库中没有记录
        exp_store = ExperienceStore()
        all_experiences = exp_store.get_all()
        assert len(all_experiences) == 0  # 应该没有记录

        print("✅ LLM失败测试通过：数据库中没有半成品记录")

    def test_embedding_failure_no_data_written(self, pipeline, monkeypatch):
        """测试embedding生成失败：不应该有任何数据写入数据库"""
        dialogue = "测试对话"

        # Mock embedding生成失败
        def mock_embedding_fail(*args, **kwargs):
            raise Exception("Embedding生成失败")

        monkeypatch.setattr(pipeline.embedding_service, 'encode', mock_embedding_fail)

        # 执行处理，预期失败
        with pytest.raises(Exception, match="Embedding生成失败"):
            pipeline.process_event(dialogue=dialogue)

        # 验证数据库中没有记录
        exp_store = ExperienceStore()
        all_experiences = exp_store.get_all()
        assert len(all_experiences) == 0  # 应该没有记录

        print("✅ Embedding失败测试通过：数据库中没有半成品记录")

    def test_atomic_write_failure_rollback(self, pipeline, monkeypatch):
        """测试原子写入失败：事务应该回滚，无数据写入"""
        dialogue = "测试对话"

        # 让前面的处理成功，但在写入时失败
        original_call = pipeline.llm_client.call_with_retry
        call_count = [0]

        def mock_call_succeed_then_fail(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] <= 3:  # 前3次调用成功
                return original_call(*args, **kwargs)
            else:  # 第4次调用失败（写入阶段）
                raise Exception("写入阶段失败")

        monkeypatch.setattr(pipeline.llm_client, 'call_with_retry', mock_call_succeed_then_fail)

        # 执行处理，预期失败
        with pytest.raises(Exception):
            pipeline.process_event(dialogue=dialogue)

        # 验证数据库中没有记录
        exp_store = ExperienceStore()
        all_experiences = exp_store.get_all()
        assert len(all_experiences) == 0  # 应该没有记录

        print("✅ 写入失败测试通过：事务回滚，数据库中没有半成品记录")


class TestPipelineIDGeneration:
    """测试ID生成避免冲突"""

    def test_unique_ids_with_same_timestamp(self, pipeline):
        """测试相同时间戳生成的ID是唯一的"""
        import time

        dialogue = "测试对话"

        # 使用相同时间戳创建多个体验节点
        timestamp = time.time()
        ids = []
        for _ in range(10):
            exp_id = pipeline.process_event(dialogue=dialogue, timestamp=timestamp)
            ids.append(exp_id)

        # 验证所有ID都是唯一的
        assert len(set(ids)) == 10  # 所有ID应该不同

        print(f"✅ ID唯一性测试通过：生成了10个不同的ID")


class TestPipelineBackwardCompatibility:
    """测试向后兼容性"""

    def test_api_interface_unchanged(self, pipeline):
        """测试API接口没有变化"""
        # 原有的API调用方式应该仍然有效
        dialogue = "测试对话"

        # 原有的调用方式
        exp_id = pipeline.process_event(dialogue=dialogue)

        # 应该返回体验节点ID
        assert exp_id is not None
        assert exp_id.startswith("exp_")

        print("✅ API兼容性测试通过：原有接口保持不变")


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v", "-s"])
