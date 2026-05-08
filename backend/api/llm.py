"""大模型API封装模块."""

import httpx
import json
import logging
from backend.config import settings
from typing import AsyncGenerator, List, Dict, Optional
from abc import ABC, abstractmethod


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class LLMProvider(ABC):
    """大模型API提供者基类"""

    def __init__(self, api_key: str, base_url: str, model: str):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.client = httpx.AsyncClient(timeout=settings.llm.api_timeout)

    @abstractmethod
    async def chat(self, messages: List[Dict], system_prompt: Optional[str] = None) -> str:
        """发送聊天请求"""
        pass

    @abstractmethod
    async def test_connection(self) -> bool:
        """测试API连接"""
        pass

    async def stream_chat(
        self,
        messages: List[Dict],
        system_prompt: Optional[str] = None,
        tools: Optional[List[Dict]] = None,
    ) -> AsyncGenerator[Dict, None]:
        """流式聊天 — 默认 fallback 到非流式。

        子类可覆盖此方法以提供真正的流式支持。
        Yield 结构化事件：
            {"type": "content", "delta": "token"}
            {"type": "tool_call_delta", "delta": [...]}
            {"type": "done", "reason": "tool_calls" | None}
        """
        response = await self.chat(messages, system_prompt)
        yield {"type": "content", "delta": response}
        yield {"type": "done", "reason": None}

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
            "max_tokens": settings.llm.anthropic_max_tokens,
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

    async def stream_chat(
        self,
        messages: List[Dict],
        system_prompt: Optional[str] = None,
        tools: Optional[List[Dict]] = None,
    ) -> AsyncGenerator[Dict, None]:
        """DeepSeek 流式聊天 — OpenAI 兼容 SSE 格式."""
        if system_prompt:
            messages = [{"role": "system", "content": system_prompt}] + messages

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        data: Dict = {
            "model": self.model,
            "messages": messages,
            "stream": True,
        }
        if tools:
            data["tools"] = tools

        tool_calls_accum: Dict[int, Dict] = {}

        try:
            async with self.client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                json=data,
                headers=headers,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    payload = line[6:].strip()
                    if payload == "[DONE]":
                        reason = "tool_calls" if tool_calls_accum else None
                        yield {"type": "done", "reason": reason}
                        return

                    try:
                        chunk = json.loads(payload)
                    except json.JSONDecodeError:
                        continue

                    choices = chunk.get("choices", [])
                    if not choices:
                        continue

                    delta = choices[0].get("delta", {})
                    finish_reason = choices[0].get("finish_reason")

                    # 文字内容
                    content = delta.get("content")
                    if content:
                        yield {"type": "content", "delta": content}

                    # 工具调用片段
                    tc_deltas = delta.get("tool_calls")
                    if tc_deltas:
                        for tc in tc_deltas:
                            idx = tc.get("index", 0)
                            if idx not in tool_calls_accum:
                                tool_calls_accum[idx] = {
                                    "id": tc.get("id", ""),
                                    "type": "function",
                                    "function": {"name": "", "arguments": ""},
                                }
                            entry = tool_calls_accum[idx]
                            if tc.get("id"):
                                entry["id"] = tc["id"]
                            fn = tc.get("function", {})
                            if fn.get("name"):
                                entry["function"]["name"] += fn["name"]
                            if fn.get("arguments"):
                                entry["function"]["arguments"] += fn["arguments"]

                        yield {
                            "type": "tool_call_delta",
                            "delta": [tool_calls_accum[i] for i in sorted(tool_calls_accum)],
                        }

                    # finish_reason 兜底
                    if finish_reason == "tool_calls":
                        yield {"type": "done", "reason": "tool_calls"}
                        return
                    elif finish_reason in ("stop", "length"):
                        yield {"type": "done", "reason": "tool_calls" if tool_calls_accum else None}
                        return

            # 流结束但没收到 [DONE]
            reason = "tool_calls" if tool_calls_accum else None
            yield {"type": "done", "reason": reason}

        except Exception as e:
            logger.error(f"DeepSeek 流式调用失败: {e}")
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

    管理思考模型（thinking_provider），用于推理和回复生成。
    同时保留旧的单模型 active_provider 接口用于向后兼容。
    """

    def __init__(self):
        self._providers: Dict[str, LLMProvider] = {}
        self._current_provider_name: Optional[str] = None
        self._thinking_provider: Optional[LLMProvider] = None

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
        self._current_provider_name = name
        logger.info(f"已设置思考模型: {name}")

    def set_thinking_provider_direct(self, provider: LLMProvider):
        """直接设置思考模型提供者（不从 _providers 字典查找）"""
        self._thinking_provider = provider
        self._current_provider_name = "thinking"
        logger.info("已直接设置思考模型提供者")

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
            if self._current_provider_name and self._current_provider_name in self._providers:
                provider = self._providers[self._current_provider_name]
            else:
                raise ValueError("未设置思考模型提供者")
        return await provider.chat(messages, system_prompt)

    async def stream_chat(
        self,
        messages: List[Dict],
        system_prompt: Optional[str] = None,
        tools: Optional[List[Dict]] = None,
    ) -> AsyncGenerator[Dict, None]:
        """使用思考模型进行流式推理"""
        provider = self._thinking_provider
        if not provider:
            if self._current_provider_name and self._current_provider_name in self._providers:
                provider = self._providers[self._current_provider_name]
            else:
                raise ValueError("未设置思考模型提供者")
        async for event in provider.stream_chat(messages, system_prompt, tools):
            yield event

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

    def get_model_config(self) -> Dict:
        """获取当前模型配置摘要"""
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
        }

    async def close_all(self):
        """关闭所有API提供者"""
        for provider in self._providers.values():
            await provider.close()
        self._providers.clear()
        self._current_provider_name = None
        self._thinking_provider = None


# 全局大模型管理器实例
llm_manager = LLMManager()
