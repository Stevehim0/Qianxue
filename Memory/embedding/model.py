"""Embedding模型服务模块。

本模块提供基于bge-base-zh模型的文本向量化服务。
使用sentence-transformers库加载模型，支持单条和批量文本转换。

参考：Memory/技术选型文档.md §三 Embedding模型使用
"""

import logging
import os
from pathlib import Path
from typing import Optional

import numpy as np

try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    logger.warning("sentence-transformers not available, will use mock service")

from Memory.config.settings import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Embedding向量生成服务。

    提供文本转向量的功能，基于bge-base-zh模型生成768维向量。
    使用懒加载模式，首次调用时自动下载模型（约400MB）。

    Attributes:
        model_name: Embedding模型名称（默认BAAI/bge-base-zh）
        _model: 私有模型实例（懒加载）

    Example:
        >>> service = EmbeddingService()
        >>> vector = service.encode("测试文本")
        >>> print(vector.shape)  # (768,)
    """

    def __init__(self, model_name: Optional[str] = None):
        """初始化EmbeddingService。

        Args:
            model_name: 模型名称，默认从settings.models.embedding_model读取
        """
        self.model_name = model_name or settings.models.embedding_model
        self._model: Optional[SentenceTransformer] = None

    @property
    def model(self):
        """懒加载模型实例。

        首次访问时加载模型，如果本地缓存不存在则自动下载。
        模型加载失败时的行为取决于allow_mock_models配置：
        - False（默认）: 抛出异常，不允许使用Mock
        - True（测试模式）: 回退到Mock服务

        Returns:
            SentenceTransformer模型实例或Mock服务（仅测试模式）

        Raises:
            RuntimeError: 模型加载失败且不允许使用Mock时抛出异常
        """
        if self._model is None:
            try:
                # 设置使用国内镜像
                if not os.getenv('HF_ENDPOINT'):
                    os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'

                logger.info(f"Loading embedding model: {self.model_name}")
                logger.info(f"Using mirror: {os.environ.get('HF_ENDPOINT', 'default')}")

                if not SENTENCE_TRANSFORMERS_AVAILABLE:
                    raise ImportError("sentence-transformers not installed")

                self._model = SentenceTransformer(self.model_name)
                logger.info(f"Embedding model loaded successfully: {self.model_name}")

            except Exception as e:
                # 检查是否允许使用Mock模型
                if settings.models.allow_mock_models:
                    logger.warning(f"Failed to load real embedding model: {e}")
                    logger.warning("ALLOW_MOCK_MODELS=True - falling back to Mock embedding service")
                    logger.warning("Mock models should ONLY be used for testing!")
                    # 创建Mock服务
                    self._model = self._create_mock_service()
                else:
                    # 不允许使用Mock，抛出异常
                    error_msg = (
                        f"Failed to load embedding model '{self.model_name}': {e}\n"
                        f"To use Mock models for testing, set ALLOW_MOCK_MODELS=true in environment or .env file\n"
                        f"Mock models should NEVER be used in production!"
                    )
                    logger.error(error_msg)
                    raise RuntimeError(error_msg) from e

        return self._model

    def _create_mock_service(self):
        """创建Mock Embedding服务。

        Returns:
            Mock服务对象
        """
        class MockModel:
            """Mock模型，模拟SentenceTransformer接口。"""

            def __init__(self):
                self.dimension = 768

            def encode(self, text, normalize_embeddings=True, show_progress_bar=False):
                """生成Mock向量。

                Args:
                    text: 输入文本或文本列表
                    normalize_embeddings: 是否归一化向量（Mock中总是归一化）
                    show_progress_bar: 是否显示进度条（Mock中忽略此参数）

                Returns:
                    归一化的768维向量
                """
                import numpy as np

                # 处理批量输入
                if isinstance(text, list):
                    # 批量处理
                    vectors = []
                    for t in text:
                        # 基于文本长度生成确定的随机向量
                        np.random.seed(len(t) % 1000)
                        vector = np.random.randn(self.dimension).astype(np.float32)
                        # 归一化
                        vector = vector / np.linalg.norm(vector)
                        vectors.append(vector)
                    return np.array(vectors, dtype=np.float32)
                else:
                    # 单条处理
                    # 基于文本长度生成确定的随机向量
                    np.random.seed(len(text) % 1000)
                    vector = np.random.randn(self.dimension).astype(np.float32)
                    # 归一化
                    vector = vector / np.linalg.norm(vector)
                    return vector

        logger.warning("Using Mock embedding service - vectors are random but dimensionally correct")
        return MockModel()

    def encode(self, text: str) -> np.ndarray:
        """将单条文本转换为向量。

        Args:
            text: 输入文本字符串

        Returns:
            768维numpy数组，dtype=np.float32

        Example:
            >>> service = EmbeddingService()
            >>> vector = service.encode("测试文本")
            >>> print(vector.shape)  # (768,)
            >>> print(vector.dtype)  # float32
        """
        embedding = self.model.encode(
            text,
            normalize_embeddings=True,  # 归一化，cosine相似度 = dot product
            show_progress_bar=False,
        )
        return embedding.astype(np.float32)

    def encode_batch(self, texts: list[str]) -> np.ndarray:
        """批量将文本转换为向量。

        Args:
            texts: 输入文本列表

        Returns:
            (N, 768)维numpy数组，N为texts长度，dtype=np.float32

        Example:
            >>> service = EmbeddingService()
            >>> vectors = service.encode_batch(["文本1", "文本2", "文本3"])
            >>> print(vectors.shape)  # (3, 768)
            >>> print(vectors.dtype)  # float32
        """
        embeddings = self.model.encode(
            texts, normalize_embeddings=True, batch_size=32, show_progress_bar=True  # 根据硬件调整
        )
        return embeddings.astype(np.float32)


# 全局EmbeddingService实例
embedding_service = EmbeddingService()
