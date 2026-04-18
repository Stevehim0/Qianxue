#!/usr/bin/env python
"""Mock Embedding服务，用于在没有模型时测试系统。

生成768维随机向量模拟真实embedding。
"""

import logging
import numpy as np
from typing import List

logger = logging.getLogger(__name__)


class MockEmbeddingService:
    """Mock Embedding服务，用于测试。

    生成768维随机向量，与真实模型维度相同。
    """

    def __init__(self):
        """初始化Mock服务。"""
        self.model_name = "MockEmbeddingService"
        self.dimension = 768  # bge-base-zh的向量维度
        logger.info("Using Mock Embedding Service (for testing only)")

    def encode(self, text: str) -> np.ndarray:
        """生成Mock向量。

        Args:
            text: 输入文本（忽略内容，生成固定模式向量）

        Returns:
            768维numpy数组，dtype=np.float32
        """
        # 基于文本长度生成确定的随机向量
        np.random.seed(len(text) % 1000)  # 使用文本长度作为种子
        vector = np.random.randn(self.dimension).astype(np.float32)
        # 归一化
        vector = vector / np.linalg.norm(vector)
        return vector

    def encode_batch(self, texts: List[str]) -> np.ndarray:
        """批量生成Mock向量。

        Args:
            texts: 文本列表

        Returns:
            (N, 768)维numpy数组
        """
        return np.array([self.encode(text) for text in texts], dtype=np.float32)


def get_embedding_service():
    """获取Embedding服务（自动选择Mock或真实服务）。

    Returns:
        EmbeddingService实例
    """
    import os

    # 检查是否强制使用Mock
    if os.getenv('USE_MOCK_EMBEDDING', '1').strip() == '1':
        logger.info("USE_MOCK_EMBEDDING=1, using Mock service")
        return MockEmbeddingService()

    # 尝试使用真实服务
    try:
        # 设置镜像
        os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'

        from Memory.embedding.model import EmbeddingService
        service = EmbeddingService()

        # 测试加载
        _ = service.model
        logger.info("Real embedding service loaded successfully")
        return service

    except Exception as e:
        logger.warning(f"Failed to load real embedding service: {e}")
        logger.info("Falling back to Mock embedding service")
        return MockEmbeddingService()


# 便捷函数
def encode_text(text: str) -> np.ndarray:
    """便捷函数：编码单条文本。"""
    service = get_embedding_service()
    return service.encode(text)


def encode_texts(texts: List[str]) -> np.ndarray:
    """便捷函数：编码多条文本。"""
    service = get_embedding_service()
    return service.encode_batch(texts)


if __name__ == "__main__":
    print("=== Mock Embedding Service Test ===")

    # 测试Mock服务
    mock_service = MockEmbeddingService()

    test_texts = ["测试文本1", "测试文本2很长很长", "短文本"]

    print("测试单条编码:")
    for text in test_texts:
        vector = mock_service.encode(text)
        print(f"  '{text}' -> shape: {vector.shape}, norm: {np.linalg.norm(vector):.4f}")

    print("\n测试批量编码:")
    vectors = mock_service.encode_batch(test_texts)
    print(f"  Batch shape: {vectors.shape}")

    print("\n=== Test Complete ===")
