"""LLM客户端工厂模块。

提供工厂模式创建不同提供商的LLM客户端，统一接口便于切换。
"""

from typing import Optional

from Memory.llm.base import BaseLLMClient
from Memory.llm.qianwen_client import QianwenClient
from Memory.llm.deepseek_client import DeepSeekClient
from Memory.llm.openai_compatible_client import OpenAICompatibleClient


class LLMFactory:
    """LLM客户端工厂类。

    提供统一的接口创建不同提供商的LLM客户端，支持自动选择。

    Examples:
        >>> # 自动选择（默认千问）
        >>> client = LLMFactory.create_client()
        >>>
        >>> # 指定千问
        >>> client = LLMFactory.create_client(provider="qianwen")
        >>>
        >>> # 指定DeepSeek
        >>> client = LLMFactory.create_client(provider="deepseek")
        >>>
        >>> # 通用 OpenAI 兼容（需传 base_url 和 model）
        >>> client = LLMFactory.create_client(provider="openai_compatible",
        ...     base_url="https://api.openai.com/v1", model="gpt-4o")
    """

    # 支持的客户端类型
    _clients = {
        "qianwen": QianwenClient,
        "deepseek": DeepSeekClient,
        "openai_compatible": OpenAICompatibleClient,
    }

    @classmethod
    def create_client(cls, provider: str = "auto", **kwargs) -> BaseLLMClient:
        """创建LLM客户端实例。

        Args:
            provider: 提供商名称
                - "auto": 自动选择（默认千问）
                - "qianwen": 千问客户端
                - "deepseek": DeepSeek客户端
            **kwargs: 传递给客户端构造函数的参数

        Returns:
            LLM客户端实例

        Raises:
            ValueError: 未知提供商名称

        Examples:
            >>> client = LLMFactory.create_client()
            >>> response = client.call("你好")
        """
        # 自动选择逻辑
        if provider == "auto":
            # 默认使用千问
            provider = "qianwen"

        # 获取客户端类
        client_class = cls._clients.get(provider)
        if not client_class:
            raise ValueError(
                f"Unknown LLM provider: {provider}. "
                f"Supported providers: {list(cls._clients.keys())}"
            )

        # 创建客户端实例
        return client_class(**kwargs)

    @classmethod
    def get_supported_providers(cls) -> list[str]:
        """获取支持的提供商列表。

        Returns:
            提供商名称列表

        Examples:
            >>> LLMFactory.get_supported_providers()
            ['qianwen', 'deepseek']
        """
        return list(cls._clients.keys())
