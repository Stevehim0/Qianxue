"""大模型API封装模块."""

import httpx
import logging
from typing import List, Dict, Optional
from abc import ABC, abstractmethod


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class LLMProvider(ABC):
    """大模型API提供者基类"""

    def __init__(self, api_key: str, base_url: str, model: str):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.client = httpx.AsyncClient(timeout=120.0)

    @abstractmethod
    async def chat(self, messages: List[Dict], system_prompt: Optional[str] = None) -> str:
        """发送聊天请求"""
        pass

    @abstractmethod
    async def test_connection(self) -> bool:
        """测试API连接"""
        pass

    async def close(self):
        """关闭HTTP客户端"""
        await self.client.aclose()


class OpenAIProvider(LLMProvider):
    """OpenAI API提供者"""

    async def chat(self, messages: List[Dict], system_prompt: Optional[str] = None) -> str:
        """使用OpenAI API进行聊天"""
        # 添加系统提示词
        if system_prompt:
            messages = [{"role": "system", "content": system_prompt}] + messages

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        data = {
            "model": self.model,
            "messages": messages
        }

        try:
            response = await self.client.post(
                f"{self.base_url}/chat/completions",
                json=data,
                headers=headers
            )
            response.raise_for_status()
            result = response.json()
            return result["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"OpenAI API调用失败: {e}")
            raise

    async def test_connection(self) -> bool:
        """测试OpenAI API连接"""
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            data = {
                "model": self.model,
                "messages": [{"role": "user", "content": "Hi"}],
                "max_tokens": 10
            }
            response = await self.client.post(
                f"{self.base_url}/chat/completions",
                json=data,
                headers=headers
            )
            return response.status_code == 200
        except Exception as e:
            logger.error(f"OpenAI API连接测试失败: {e}")
            return False


class AnthropicProvider(LLMProvider):
    """Anthropic Claude API提供者"""

    async def chat(self, messages: List[Dict], system_prompt: Optional[str] = None) -> str:
        """使用Anthropic Claude API进行聊天"""
        headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01"
        }

        # 转换消息格式为Claude格式
        claude_messages = []
        for msg in messages:
            if msg["role"] == "user":
                claude_messages.append({"role": "user", "content": msg["content"]})
            elif msg["role"] == "assistant":
                claude_messages.append({"role": "assistant", "content": msg["content"]})

        data = {
            "model": self.model,
            "max_tokens": 1024,
            "messages": claude_messages
        }

        # 添加系统提示词
        if system_prompt:
            data["system"] = system_prompt

        try:
            response = await self.client.post(
                f"{self.base_url}/v1/messages",
                json=data,
                headers=headers
            )
            response.raise_for_status()
            result = response.json()
            return result["content"][0]["text"]
        except Exception as e:
            logger.error(f"Anthropic API调用失败: {e}")
            raise

    async def test_connection(self) -> bool:
        """测试Anthropic API连接"""
        try:
            headers = {
                "x-api-key": self.api_key,
                "Content-Type": "application/json",
                "anthropic-version": "2023-06-01"
            }
            data = {
                "model": self.model,
                "max_tokens": 10,
                "messages": [{"role": "user", "content": "Hi"}]
            }
            response = await self.client.post(
                f"{self.base_url}/v1/messages",
                json=data,
                headers=headers
            )
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Anthropic API连接测试失败: {e}")
            return False


class DeepSeekProvider(LLMProvider):
    """DeepSeek API提供者（兼容OpenAI API格式）"""

    async def chat(self, messages: List[Dict], system_prompt: Optional[str] = None) -> str:
        """使用DeepSeek API进行聊天"""
        if system_prompt:
            messages = [{"role": "system", "content": system_prompt}] + messages

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        data = {
            "model": self.model,
            "messages": messages
        }

        try:
            response = await self.client.post(
                f"{self.base_url}/chat/completions",
                json=data,
                headers=headers
            )
            response.raise_for_status()
            result = response.json()
            return result["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"DeepSeek API调用失败: {e}")
            raise

    async def test_connection(self) -> bool:
        """测试DeepSeek API连接"""
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            data = {
                "model": self.model,
                "messages": [{"role": "user", "content": "Hi"}],
                "max_tokens": 10
            }
            response = await self.client.post(
                f"{self.base_url}/chat/completions",
                json=data,
                headers=headers
            )
            return response.status_code == 200
        except Exception as e:
            logger.error(f"DeepSeek API连接测试失败: {e}")
            return False


class QwenProvider(LLMProvider):
    """通义千问API提供者（兼容OpenAI API格式）"""

    async def chat(self, messages: List[Dict], system_prompt: Optional[str] = None) -> str:
        """使用通义千问API进行聊天"""
        if system_prompt:
            messages = [{"role": "system", "content": system_prompt}] + messages

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        data = {
            "model": self.model,
            "messages": messages
        }

        try:
            response = await self.client.post(
                f"{self.base_url}/chat/completions",
                json=data,
                headers=headers
            )
            response.raise_for_status()
            result = response.json()
            return result["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"通义千问 API调用失败: {e}")
            raise

    async def test_connection(self) -> bool:
        """测试通义千问 API连接"""
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            data = {
                "model": self.model,
                "messages": [{"role": "user", "content": "Hi"}],
                "max_tokens": 10
            }
            response = await self.client.post(
                f"{self.base_url}/chat/completions",
                json=data,
                headers=headers
            )
            return response.status_code == 200
        except Exception as e:
            logger.error(f"通义千问 API连接测试失败: {e}")
            return False


class LLMManager:
    """大模型管理器

    支持双模型配置：
    - thinking_provider: 思考模型，用于推理和工具决策
    - speaking_provider: 说话模型，用于生成自然语言回复

    同时保留旧的单模型 active_provider 接口用于向后兼容。
    """

    def __init__(self):
        self._providers: Dict[str, LLMProvider] = {}
        self._current_provider_name: Optional[str] = None
        # 双模型支持
        self._thinking_provider: Optional[LLMProvider] = None
        self._speaking_provider: Optional[LLMProvider] = None

    def add_provider(self, name: str, provider: LLMProvider):
        """添加API提供者"""
        self._providers[name] = provider
        logger.info(f"已添加API提供者: {name}")

    def set_current_provider(self, name: str):
        """设置当前使用的API提供者（向后兼容，同时设为 thinking provider）"""
        if name not in self._providers:
            raise ValueError(f"API提供者 '{name}' 不存在")
        self._current_provider_name = name
        self._thinking_provider = self._providers[name]
        logger.info(f"已切换到API提供者: {name}")

    def set_thinking_provider(self, name: str):
        """设置思考模型提供者"""
        if name not in self._providers:
            raise ValueError(f"API提供者 '{name}' 不存在")
        self._thinking_provider = self._providers[name]
        self._current_provider_name = name  # 向后兼容
        logger.info(f"已设置思考模型: {name}")

    def set_speaking_provider(self, name: str):
        """设置说话模型提供者"""
        if name not in self._providers:
            raise ValueError(f"API提供者 '{name}' 不存在")
        self._speaking_provider = self._providers[name]
        logger.info(f"已设置说话模型: {name}")

    def set_thinking_provider_direct(self, provider: LLMProvider):
        """直接设置思考模型提供者（不从 _providers 字典查找）"""
        self._thinking_provider = provider
        self._current_provider_name = "thinking"
        logger.info("已直接设置思考模型提供者")

    def set_speaking_provider_direct(self, provider: LLMProvider):
        """直接设置说话模型提供者（不从 _providers 字典查找）"""
        self._speaking_provider = provider
        logger.info("已直接设置说话模型提供者")

    def remove_provider(self, name: str):
        """移除API提供者"""
        if name in self._providers:
            provider = self._providers.pop(name)
            import asyncio
            asyncio.create_task(provider.close())
            if self._current_provider_name == name:
                self._current_provider_name = None
            logger.info(f"已移除API提供者: {name}")

    async def chat(self, messages: List[Dict], system_prompt: Optional[str] = None) -> str:
        """使用当前API提供者进行聊天（向后兼容，默认使用 thinking provider）"""
        return await self.thinking_chat(messages, system_prompt)

    async def thinking_chat(self, messages: List[Dict], system_prompt: Optional[str] = None) -> str:
        """使用思考模型进行推理"""
        provider = self._thinking_provider
        if not provider:
            # 回退到旧的单模型模式
            if self._current_provider_name and self._current_provider_name in self._providers:
                provider = self._providers[self._current_provider_name]
            else:
                raise ValueError("未设置思考模型提供者")
        return await provider.chat(messages, system_prompt)

    async def speaking_chat(self, messages: List[Dict], system_prompt: Optional[str] = None) -> str:
        """使用说话模型生成自然语言回复"""
        provider = self._speaking_provider
        if not provider:
            # 回退到 thinking provider
            logger.warning("说话模型未配置，回退到思考模型")
            return await self.thinking_chat(messages, system_prompt)
        return await provider.chat(messages, system_prompt)

    async def test_provider(self, name: str) -> bool:
        """测试指定的API提供者"""
        if name not in self._providers:
            return False
        provider = self._providers[name]
        return await provider.test_connection()

    def list_providers(self) -> List[str]:
        """列出所有API提供者"""
        return list(self._providers.keys())

    def get_current_provider(self) -> Optional[str]:
        """获取当前API提供者名称"""
        return self._current_provider_name

    def get_thinking_provider(self) -> Optional[LLMProvider]:
        """获取思考模型提供者"""
        return self._thinking_provider

    def get_speaking_provider(self) -> Optional[LLMProvider]:
        """获取说话模型提供者"""
        return self._speaking_provider

    def get_model_config(self) -> Dict:
        """获取当前双模型配置摘要"""
        def _provider_info(p: Optional[LLMProvider]) -> Optional[Dict]:
            if not p:
                return None
            return {
                "base_url": p.base_url,
                "model": p.model,
                "api_key": p.api_key[:8] + "..." if p.api_key and len(p.api_key) > 8 else "***"
            }
        return {
            "thinking_provider": _provider_info(self._thinking_provider),
            "speaking_provider": _provider_info(self._speaking_provider),
        }

    async def close_all(self):
        """关闭所有API提供者"""
        for provider in self._providers.values():
            await provider.close()
        self._providers.clear()
        self._current_provider_name = None
        self._thinking_provider = None
        self._speaking_provider = None


# 全局大模型管理器实例
llm_manager = LLMManager()
