"""LLM工厂测试。

测试 Memory.llm.factory 模块的 LLMFactory 类：
- create_client(): 创建不同提供商的客户端
- get_supported_providers(): 获取支持的提供商列表
- 参数传递: kwargs正确传递给客户端
- 错误处理: 未知提供商抛出ValueError
"""

import pytest
from unittest.mock import patch

from Memory.llm.factory import LLMFactory
from Memory.llm.qianwen_client import QianwenClient
from Memory.llm.deepseek_client import DeepSeekClient
from Memory.llm.base import BaseLLMClient


class TestLLMFactoryCreateClient:
    """测试 LLMFactory.create_client 方法。"""

    def test_create_qianwen_client(self, tmp_log_dir, monkeypatch):
        """测试创建千问客户端。"""
        # Mock日志目录
        monkeypatch.setattr("Memory.llm.utils.Path", lambda p: tmp_log_dir.parent / p)

        client = LLMFactory.create_client(provider="qianwen", api_key="test-key")

        assert isinstance(client, QianwenClient)
        assert client.provider == "qianwen"
        assert client.api_key == "test-key"

    def test_create_deepseek_client(self, tmp_log_dir, monkeypatch):
        """测试创建DeepSeek客户端。"""
        # Mock日志目录
        monkeypatch.setattr("Memory.llm.utils.Path", lambda p: tmp_log_dir.parent / p)

        client = LLMFactory.create_client(provider="deepseek", api_key="test-key")

        assert isinstance(client, DeepSeekClient)
        assert client.provider == "deepseek"
        assert client.api_key == "test-key"

    def test_create_auto_provider_default_qianwen(self, tmp_log_dir, monkeypatch):
        """测试auto提供商默认创建千问客户端。"""
        # Mock日志目录
        monkeypatch.setattr("Memory.llm.utils.Path", lambda p: tmp_log_dir.parent / p)

        client = LLMFactory.create_client(provider="auto", api_key="test-key")

        assert isinstance(client, QianwenClient)
        assert client.provider == "qianwen"

    def test_create_no_provider_default_qianwen(self, tmp_log_dir, monkeypatch):
        """测试不指定provider时默认创建千问客户端。"""
        # Mock日志目录
        monkeypatch.setattr("Memory.llm.utils.Path", lambda p: tmp_log_dir.parent / p)

        client = LLMFactory.create_client(api_key="test-key")

        assert isinstance(client, QianwenClient)
        assert client.provider == "qianwen"

    def test_create_invalid_provider_raises_error(self, tmp_log_dir, monkeypatch):
        """测试创建未知提供商抛出ValueError。"""
        # Mock日志目录
        monkeypatch.setattr("Memory.llm.utils.Path", lambda p: tmp_log_dir.parent / p)

        with pytest.raises(ValueError, match="Unknown LLM provider: invalid"):
            LLMFactory.create_client(provider="invalid", api_key="test-key")

    def test_create_client_case_sensitive(self, tmp_log_dir, monkeypatch):
        """测试provider名称区分大小写。"""
        # Mock日志目录
        monkeypatch.setattr("Memory.llm.utils.Path", lambda p: tmp_log_dir.parent / p)

        with pytest.raises(ValueError, match="Unknown LLM provider: Qianwen"):
            LLMFactory.create_client(provider="Qianwen", api_key="test-key")


class TestLLMFactoryParameterPassing:
    """测试参数传递。"""

    def test_pass_api_key_to_qianwen(self, tmp_log_dir, monkeypatch):
        """测试传递api_key给千问客户端。"""
        # Mock日志目录
        monkeypatch.setattr("Memory.llm.utils.Path", lambda p: tmp_log_dir.parent / p)

        client = LLMFactory.create_client(provider="qianwen", api_key="custom-api-key")

        assert client.api_key == "custom-api-key"

    def test_pass_api_key_to_deepseek(self, tmp_log_dir, monkeypatch):
        """测试传递api_key给DeepSeek客户端。"""
        # Mock日志目录
        monkeypatch.setattr("Memory.llm.utils.Path", lambda p: tmp_log_dir.parent / p)

        client = LLMFactory.create_client(provider="deepseek", api_key="custom-api-key")

        assert client.api_key == "custom-api-key"

    def test_pass_timeout_to_qianwen(self, tmp_log_dir, monkeypatch):
        """测试传递timeout给千问客户端。"""
        # Mock日志目录
        monkeypatch.setattr("Memory.llm.utils.Path", lambda p: tmp_log_dir.parent / p)

        client = LLMFactory.create_client(provider="qianwen", api_key="test-key", timeout=60)

        assert client.timeout == 60

    def test_pass_timeout_to_deepseek(self, tmp_log_dir, monkeypatch):
        """测试传递timeout给DeepSeek客户端。"""
        # Mock日志目录
        monkeypatch.setattr("Memory.llm.utils.Path", lambda p: tmp_log_dir.parent / p)

        client = LLMFactory.create_client(provider="deepseek", api_key="test-key", timeout=45)

        assert client.timeout == 45

    def test_pass_multiple_parameters(self, tmp_log_dir, monkeypatch):
        """测试传递多个参数。"""
        # Mock日志目录
        monkeypatch.setattr("Memory.llm.utils.Path", lambda p: tmp_log_dir.parent / p)

        client = LLMFactory.create_client(
            provider="qianwen", api_key="test-key", timeout=90, custom_param="custom_value"
        )

        assert client.api_key == "test-key"
        assert client.timeout == 90
        # custom_param会被kwargs接收，但BaseLLMClient不使用它


class TestLLMFactoryGetSupportedProviders:
    """测试 LLMFactory.get_supported_providers 方法。"""

    def test_get_supported_providers(self):
        """测试获取支持的提供商列表。"""
        providers = LLMFactory.get_supported_providers()

        assert isinstance(providers, list)
        assert "qianwen" in providers
        assert "deepseek" in providers
        assert len(providers) == 2

    def test_providers_are_strings(self):
        """测试提供商名称是字符串。"""
        providers = LLMFactory.get_supported_providers()

        for provider in providers:
            assert isinstance(provider, str)

    def test_providers_lowercase(self):
        """测试提供商名称是小写。"""
        providers = LLMFactory.get_supported_providers()

        for provider in providers:
            assert provider.islower()


class TestLLMFactoryCaching:
    """测试客户端缓存行为。"""

    def test_multiple_calls_create_different_instances(self, tmp_log_dir, monkeypatch):
        """测试多次调用创建不同的客户端实例（无缓存）。"""
        # Mock日志目录
        monkeypatch.setattr("Memory.llm.utils.Path", lambda p: tmp_log_dir.parent / p)

        client1 = LLMFactory.create_client(provider="qianwen", api_key="test-key")
        client2 = LLMFactory.create_client(provider="qianwen", api_key="test-key")

        # 应该是不同的实例
        assert client1 is not client2
        assert client1.api_key == client2.api_key


class TestLLMFactoryIntegration:
    """集成测试。"""

    def test_create_and_use_qianwen_client(self, tmp_log_dir, monkeypatch):
        """测试创建并使用千问客户端。"""
        # Mock日志目录
        monkeypatch.setattr("Memory.llm.utils.Path", lambda p: tmp_log_dir.parent / p)

        client = LLMFactory.create_client(provider="qianwen", api_key="test-key")

        # 验证客户端是BaseLLMClient的实例
        assert isinstance(client, BaseLLMClient)

        # 验证客户端有call方法
        assert hasattr(client, "call")
        assert callable(client.call)

    def test_create_and_use_deepseek_client(self, tmp_log_dir, monkeypatch):
        """测试创建并使用DeepSeek客户端。"""
        # Mock日志目录
        monkeypatch.setattr("Memory.llm.utils.Path", lambda p: tmp_log_dir.parent / p)

        client = LLMFactory.create_client(provider="deepseek", api_key="test-key")

        # 验证客户端是BaseLLMClient的实例
        assert isinstance(client, BaseLLMClient)

        # 验证客户端有call方法
        assert hasattr(client, "call")
        assert callable(client.call)

    def test_create_all_supported_providers(self, tmp_log_dir, monkeypatch):
        """测试创建所有支持的提供商。"""
        # Mock日志目录
        monkeypatch.setattr("Memory.llm.utils.Path", lambda p: tmp_log_dir.parent / p)

        providers = LLMFactory.get_supported_providers()

        for provider in providers:
            client = LLMFactory.create_client(provider=provider, api_key="test-key")
            assert isinstance(client, BaseLLMClient)
            assert client.provider == provider
