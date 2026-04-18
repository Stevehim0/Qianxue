"""Embedding模块 - 向量生成和存储。

本模块提供基于bge-base-zh模型的文本向量化服务，
以及ChromaDB向量存储和检索功能。

Exports:
    EmbeddingService: 文本转向量的服务类
    embedding_service: 全局EmbeddingService实例
    VectorStore: ChromaDB向量存储封装类
    vector_store: 全局VectorStore实例
"""

from Memory.embedding.model import EmbeddingService, embedding_service
from Memory.embedding.vector_store import VectorStore, vector_store

__all__ = [
    "EmbeddingService",
    "embedding_service",
    "VectorStore",
    "vector_store",
]
