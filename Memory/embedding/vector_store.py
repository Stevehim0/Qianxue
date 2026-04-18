"""ChromaDB向量存储封装模块。

本模块封装ChromaDB的PersistentClient，提供向量存取检索功能。
包含两个独立的collection：
- experience_L0: 存储体验层L0摘要的向量
- entities: 存储信息层实体的向量

参考：Memory/技术选型文档.md §四 ChromaDB向量检索
"""

import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

import chromadb
from chromadb.config import Settings

from Memory.config.settings import settings

logger = logging.getLogger(__name__)


class VectorStore:
    """ChromaDB向量存储封装类。

    提供向量存储、检索、更新和删除操作。
    使用PersistentClient实现本地持久化。

    Attributes:
        client: ChromaDB PersistentClient实例
        exp_collection: 体验L0摘要向量集合
        entity_collection: 信息层实体向量集合
    """

    # Collection名称常量
    COLLECTION_EXPERIENCE_L0 = "experience_L0"
    COLLECTION_ENTITIES = "entities"

    # 相似度空间类型
    METRIC_COSINE = "cosine"

    def __init__(self, persist_dir: Optional[Path] = None):
        """初始化VectorStore。

        Args:
            persist_dir: ChromaDB持久化目录，默认使用settings中的配置

        Raises:
            RuntimeError: ChromaDB初始化失败时抛出异常
        """
        self.persist_dir = persist_dir or settings.database.chroma_persist_dir

        try:
            # 确保持久化目录存在
            self.persist_dir.mkdir(parents=True, exist_ok=True)

            # 创建PersistentClient
            self.client = chromadb.PersistentClient(
                path=str(self.persist_dir),
                settings=Settings(
                    anonymized_telemetry=False,  # 禁用匿名遥测
                    allow_reset=True,  # 允许重置（用于测试）
                ),
            )

            # 创建或获取collection
            self.exp_collection = self._get_or_create_collection(self.COLLECTION_EXPERIENCE_L0)
            self.entity_collection = self._get_or_create_collection(self.COLLECTION_ENTITIES)

            logger.info(
                f"VectorStore initialized: {self.persist_dir}, "
                f"collections: {self.COLLECTION_EXPERIENCE_L0}, {self.COLLECTION_ENTITIES}"
            )

        except Exception as e:
            logger.error(f"Failed to initialize ChromaDB: {e}")
            raise RuntimeError(f"ChromaDB initialization failed: {e}") from e

    def _get_or_create_collection(self, name: str):
        """获取或创建collection。

        Args:
            name: Collection名称

        Returns:
            ChromaDB Collection对象
        """
        return self.client.get_or_create_collection(
            name=name, metadata={self.METRIC_COSINE: self.METRIC_COSINE}
        )

    # ========== 体验L0摘要向量操作 ==========

    def add_experience(
        self, exp_id: str, embedding: List[float], metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """添加体验L0摘要向量。

        Args:
            exp_id: 体验节点ID
            embedding: 768维向量（list格式，ChromaDB要求）
            metadata: 元数据字典（如L0_text, created_at等）
        """
        if metadata is None:
            metadata = {}

        self.exp_collection.add(ids=[exp_id], embeddings=[embedding], metadatas=[metadata])
        logger.debug(f"Added experience vector: {exp_id}")

    def upsert_experience(
        self, exp_id: str, embedding: List[float], metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """添加或更新体验L0摘要向量。

        Args:
            exp_id: 体验节点ID
            embedding: 768维向量（list格式）
            metadata: 元数据字典
        """
        if metadata is None:
            metadata = {}

        self.exp_collection.upsert(ids=[exp_id], embeddings=[embedding], metadatas=[metadata])
        logger.debug(f"Upserted experience vector: {exp_id}")

    def query_experience(
        self, query_embedding: List[float], top_k: int = 10, where: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """查询最相似的体验L0摘要。

        Args:
            query_embedding: 查询向量（768维list）
            top_k: 返回结果数量
            where: 元数据过滤条件（可选）

        Returns:
            ChromaDB查询结果字典，包含ids, distances, metadatas
        """
        results = self.exp_collection.query(
            query_embeddings=[query_embedding], n_results=top_k, where=where
        )
        return results

    def delete_experience(self, exp_id: str) -> None:
        """删除体验L0摘要向量。

        Args:
            exp_id: 体验节点ID
        """
        self.exp_collection.delete(ids=[exp_id])
        logger.debug(f"Deleted experience vector: {exp_id}")

    # ========== 实体向量操作 ==========

    def add_entity(
        self, entity_id: str, embedding: List[float], metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """添加实体向量。

        Args:
            entity_id: 实体ID
            embedding: 768维向量（list格式）
            metadata: 元数据字典（如name, type等）
        """
        if metadata is None:
            metadata = {}

        self.entity_collection.add(ids=[entity_id], embeddings=[embedding], metadatas=[metadata])
        logger.debug(f"Added entity vector: {entity_id}")

    def upsert_entity(
        self, entity_id: str, embedding: List[float], metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """添加或更新实体向量。

        Args:
            entity_id: 实体ID
            embedding: 768维向量（list格式）
            metadata: 元数据字典
        """
        if metadata is None:
            metadata = {}

        self.entity_collection.upsert(ids=[entity_id], embeddings=[embedding], metadatas=[metadata])
        logger.debug(f"Upserted entity vector: {entity_id}")

    def query_entity(
        self, query_embedding: List[float], top_k: int = 10, where: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """查询最相似的实体。

        Args:
            query_embedding: 查询向量（768维list）
            top_k: 返回结果数量
            where: 元数据过滤条件（可选）

        Returns:
            ChromaDB查询结果字典
        """
        results = self.entity_collection.query(
            query_embeddings=[query_embedding], n_results=top_k, where=where
        )
        return results

    def delete_entity(self, entity_id: str) -> None:
        """删除实体向量。

        Args:
            entity_id: 实体ID
        """
        self.entity_collection.delete(ids=[entity_id])
        logger.debug(f"Deleted entity vector: {entity_id}")

    # ========== 批量操作 ==========

    def add_experiences_batch(
        self,
        ids: List[str],
        embeddings: List[List[float]],
        metadatas: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """批量添加体验向量。

        Args:
            ids: 体验节点ID列表
            embeddings: 向量列表
            metadatas: 元数据列表（可选）
        """
        if metadatas is None:
            metadatas = [{}] * len(ids)

        self.exp_collection.add(ids=ids, embeddings=embeddings, metadatas=metadatas)
        logger.debug(f"Added {len(ids)} experience vectors")

    def add_entities_batch(
        self,
        ids: List[str],
        embeddings: List[List[float]],
        metadatas: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """批量添加实体向量。

        Args:
            ids: 实体ID列表
            embeddings: 向量列表
            metadatas: 元数据列表（可选）
        """
        if metadatas is None:
            metadatas = [{}] * len(ids)

        self.entity_collection.add(ids=ids, embeddings=embeddings, metadatas=metadatas)
        logger.debug(f"Added {len(ids)} entity vectors")

    # ========== 统计和调试 ==========

    def get_collection_stats(self) -> Dict[str, int]:
        """获取collection统计信息。

        Returns:
            包含各collection向量数量的字典
        """
        return {
            "experience_count": self.exp_collection.count(),
            "entity_count": self.entity_collection.count(),
        }

    def reset_collections(self) -> None:
        """重置所有collection（危险操作，仅用于测试）。

        删除并重新创建两个collection。
        """
        self.client.delete_collection(self.COLLECTION_EXPERIENCE_L0)
        self.client.delete_collection(self.COLLECTION_ENTITIES)

        self.exp_collection = self._get_or_create_collection(self.COLLECTION_EXPERIENCE_L0)
        self.entity_collection = self._get_or_create_collection(self.COLLECTION_ENTITIES)

        logger.warning("All collections have been reset")


# 全局VectorStore实例
vector_store = VectorStore()
