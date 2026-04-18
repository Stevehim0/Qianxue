"""Embedding服务测试模块。

本模块测试EmbeddingService和VectorStore的功能。
"""

import os
from pathlib import Path
from unittest.mock import Mock, patch
import tempfile
import shutil

import pytest
import numpy as np

from Memory.embedding.model import EmbeddingService
from Memory.embedding.vector_store import VectorStore


class TestEmbeddingService:
    """测试EmbeddingService类。"""

    def test_init(self):
        """测试初始化。"""
        service = EmbeddingService(model_name="BAAI/bge-base-zh")
        assert service.model_name == "BAAI/bge-base-zh"
        assert service._model is None

    def test_model_lazy_loading(self):
        """测试懒加载。"""
        service = EmbeddingService()
        assert service._model is None

        with patch("Memory.embedding.model.SentenceTransformer") as mock_st:
            mock_model = Mock()
            mock_model.encode.return_value = np.random.rand(768).astype(np.float32)
            mock_st.return_value = mock_model

            _ = service.model
            assert service._model is not None
            mock_st.assert_called_once()

    def test_encode_single(self, mock_embedding_model):
        """测试单条文本编码。"""
        service = EmbeddingService()
        service._model = mock_embedding_model

        result = service.encode("测试文本")
        assert isinstance(result, np.ndarray)
        assert result.dtype == np.float32
        assert result.shape == (768,)

    def test_encode_batch(self, mock_embedding_model):
        """测试批量编码。"""
        service = EmbeddingService()
        service._model = mock_embedding_model

        texts = ["文本1", "文本2", "文本3"]
        result = service.encode_batch(texts)
        assert result.shape == (3, 768)
        assert result.dtype == np.float32

    @pytest.mark.skipif(
        not os.path.exists(os.path.expanduser("~/.cache/torch/sentence_transformers/")),
        reason="Model not downloaded",
    )
    def test_vector_dimension_real(self):
        """测试真实模型向量维度。"""
        service = EmbeddingService()
        vector = service.encode("测试")
        assert vector.shape == (768,)


class TestVectorStore:
    """测试VectorStore类。"""

    @pytest.fixture
    def temp_store(self, tmp_path):
        """创建临时VectorStore。"""
        temp_dir = tmp_path / "chroma_test"
        temp_dir.mkdir(parents=True, exist_ok=True)
        store = VectorStore(persist_dir=temp_dir)
        yield store
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_init(self, temp_store):
        """测试初始化。"""
        assert temp_store.client is not None
        assert temp_store.exp_collection is not None

    def test_add_experience(self, temp_store, sample_embedding):
        """测试添加体验向量。"""
        temp_store.add_experience(
            exp_id="exp001", embedding=sample_embedding.tolist(), metadata={"text": "测试"}
        )
        stats = temp_store.get_collection_stats()
        assert stats["experience_count"] == 1

    def test_query_experience(self, temp_store, sample_embedding):
        """测试查询体验向量。"""
        temp_store.add_experience("exp001", sample_embedding.tolist())

        results = temp_store.query_experience(query_embedding=sample_embedding.tolist(), top_k=1)
        assert "ids" in results
        assert "exp001" in results["ids"][0]

    def test_upsert_experience(self, temp_store, sample_embedding):
        """测试更新体验向量。"""
        temp_store.add_experience("exp001", sample_embedding.tolist())

        new_emb = np.random.rand(768).astype(np.float32)
        temp_store.upsert_experience("exp001", new_emb.tolist())

        stats = temp_store.get_collection_stats()
        assert stats["experience_count"] == 1

    def test_add_entity(self, temp_store, sample_embedding):
        """测试添加实体向量。"""
        temp_store.add_entity(entity_id="ent001", embedding=sample_embedding.tolist())
        stats = temp_store.get_collection_stats()
        assert stats["entity_count"] == 1

    def test_collection_stats(self, temp_store):
        """测试统计信息。"""
        stats = temp_store.get_collection_stats()
        assert stats["experience_count"] == 0
        assert stats["entity_count"] == 0
