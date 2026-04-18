"""实体识别任务测试。"""

import pytest
from unittest.mock import Mock, MagicMock
from Memory.writer.tasks.entity_task import recognize_entities_and_create_edges


class TestEntityRecognition:
    """实体识别功能测试。"""

    def test_recognize_new_person_entity(
        self,
        mock_llm_client,
        mock_embedding_service,
        temp_db_dir,
    ):
        """测试识别并创建新人物实体。"""
        # 准备
        experience_id = "exp_20260409_120000"
        dialogue = "张三：我想学Python\nAI：好的，我来教你。"

        # Mock LLM返回实体识别结果
        mock_llm_client.call_with_retry.return_value = {
            "entities": [
                {
                    "name": "张三",
                    "type": "person",
                    "attributes": {
                        "learning_goal": "想学Python"
                    },
                    "confidence": 0.9
                },
                {
                    "name": "Python",
                    "type": "concept",
                    "attributes": {
                        "category": "编程语言"
                    },
                    "confidence": 1.0
                }
            ]
        }

        entity_store = Mock()
        entity_store.get_by_name.return_value = None  # 实体不存在
        entity_store.create.return_value = "entity-123"

        cross_edge_store = Mock()
        cross_edge_store.create.return_value = 1

        # 执行
        entity_ids = recognize_entities_and_create_edges(
            experience_id=experience_id,
            dialogue=dialogue,
            llm_client=mock_llm_client,
            embedding_service=mock_embedding_service,
            entity_store=entity_store,
            cross_edge_store=cross_edge_store,
        )

        # 验证
        assert len(entity_ids) == 2
        assert entity_store.create.call_count == 2
        assert cross_edge_store.create.call_count == 2

        # 验证第一次调用创建张三实体
        first_call_args = entity_store.create.call_args_list[0]
        created_entity = first_call_args[0][0]
        assert created_entity.name == "张三"
        assert created_entity.type == "person"
        assert "learning_goal" in created_entity.properties

        # 验证第二次调用创建Python实体
        second_call_args = entity_store.create.call_args_list[1]
        created_entity = second_call_args[0][0]
        assert created_entity.name == "Python"
        assert created_entity.type == "concept"

    def test_recognize_existing_entity_updates_properties(
        self,
        mock_llm_client,
        mock_embedding_service,
        temp_db_dir,
    ):
        """测试识别已存在的实体时更新属性。"""
        # 准备
        experience_id = "exp_20260409_120001"
        dialogue = "张三：我还想学机器学习\nAI：好的。"

        # Mock LLM返回实体识别结果
        mock_llm_client.call_with_retry.return_value = {
            "entities": [
                {
                    "name": "张三",
                    "type": "person",
                    "attributes": {
                        "learning_goal": "想学机器学习"
                    },
                    "confidence": 0.9
                }
            ]
        }

        # 准备：实体已存在
        entity_store = Mock()
        existing_entity = Mock()
        existing_entity.id = "entity-456"
        existing_entity.properties = {
            "learning_goal": "想学Python",
            "confidence": 0.8
        }
        entity_store.get_by_name.return_value = existing_entity

        cross_edge_store = Mock()
        cross_edge_store.create.return_value = 1

        # 执行
        entity_ids = recognize_entities_and_create_edges(
            experience_id=experience_id,
            dialogue=dialogue,
            llm_client=mock_llm_client,
            embedding_service=mock_embedding_service,
            entity_store=entity_store,
            cross_edge_store=cross_edge_store,
        )

        # 验证：不创建新实体，只更新属性
        assert len(entity_ids) == 1
        assert entity_ids[0] == "entity-456"
        assert not entity_store.create.called
        assert entity_store.update.called

        # 验证更新合并了属性
        update_call_args = entity_store.update.call_args
        assert update_call_args[1]["entity_id"] == "entity-456"
        updated_properties = update_call_args[1]["properties"]
        assert updated_properties["learning_goal"] == "想学机器学习"
        assert "updated_at" in updated_properties

    def test_recognize_multiple_entity_types(
        self,
        mock_llm_client,
        mock_embedding_service,
        temp_db_dir,
    ):
        """测试识别多种类型的实体。"""
        # 准备
        experience_id = "exp_20260409_120002"
        dialogue = "张三昨天去了北京参加AI会议"

        # Mock LLM返回多种类型实体
        mock_llm_client.call_with_retry.return_value = {
            "entities": [
                {
                    "name": "张三",
                    "type": "person",
                    "attributes": {},
                    "confidence": 0.9
                },
                {
                    "name": "北京",
                    "type": "place",
                    "attributes": {},
                    "confidence": 1.0
                },
                {
                    "name": "AI会议",
                    "type": "event",
                    "attributes": {},
                    "confidence": 0.8
                }
            ]
        }

        entity_store = Mock()
        entity_store.get_by_name.return_value = None
        entity_store.create.return_value = "entity-123"

        cross_edge_store = Mock()

        # 执行
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

        # 验证实体类型
        for i, call_args in enumerate(entity_store.create.call_args_list):
            entity = call_args[0][0]
            if entity.name == "张三":
                assert entity.type == "person"
            elif entity.name == "北京":
                assert entity.type == "place"
            elif entity.name == "AI会议":
                assert entity.type == "event"

    def test_invalid_entity_type_defaults_to_other(
        self,
        mock_llm_client,
        mock_embedding_service,
        temp_db_dir,
    ):
        """测试无效的实体类型默认为'other'。"""
        # 准备
        experience_id = "exp_20260409_120003"
        dialogue = "测试对话"

        # Mock LLM返回无效类型
        mock_llm_client.call_with_retry.return_value = {
            "entities": [
                {
                    "name": "某物",
                    "type": "invalid_type",
                    "attributes": {},
                    "confidence": 0.8
                }
            ]
        }

        entity_store = Mock()
        entity_store.get_by_name.return_value = None
        entity_store.create.return_value = "entity-123"

        cross_edge_store = Mock()

        # 执行
        recognize_entities_and_create_edges(
            experience_id=experience_id,
            dialogue=dialogue,
            llm_client=mock_llm_client,
            embedding_service=mock_embedding_service,
            entity_store=entity_store,
            cross_edge_store=cross_edge_store,
        )

        # 验证：类型被修正为'other'
        created_entity = entity_store.create.call_args[0][0]
        assert created_entity.type == "other"

    def test_cross_edge_context_is_contains_entity(
        self,
        mock_llm_client,
        mock_embedding_service,
        temp_db_dir,
    ):
        """测试跨层边的context为'contains_entity'。"""
        # 准备
        experience_id = "exp_20260409_120004"
        dialogue = "张三在这里"

        mock_llm_client.call_with_retry.return_value = {
            "entities": [
                {
                    "name": "张三",
                    "type": "person",
                    "attributes": {},
                    "confidence": 0.9
                }
            ]
        }

        entity_store = Mock()
        entity_store.get_by_name.return_value = None
        entity_store.create.return_value = "entity-123"

        cross_edge_store = Mock()

        # 执行
        recognize_entities_and_create_edges(
            experience_id=experience_id,
            dialogue=dialogue,
            llm_client=mock_llm_client,
            embedding_service=mock_embedding_service,
            entity_store=entity_store,
            cross_edge_store=cross_edge_store,
        )

        # 验证：跨层边的context
        cross_edge = cross_edge_store.create.call_args[0][0]
        assert cross_edge.context == "contains_entity"
        assert cross_edge.from_id == experience_id
        assert cross_edge.to_id == "entity-123"
