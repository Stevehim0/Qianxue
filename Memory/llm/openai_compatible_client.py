"""通用 OpenAI 兼容 LLM 客户端实现模块。

提供基于 /chat/completions 端点的通用客户端，可适配任何 OpenAI 兼容 API。
包括 OpenAI、DeepSeek、通义千问兼容模式、智谱、Moonshot、MiniMax、豆包等。
"""

import requests
from typing import Optional
import logging

from Memory.llm.base import BaseLLMClient
from Memory.llm.utils import parse_json, log_llm_error
from Memory.config.settings import settings

logger = logging.getLogger(__name__)


class OpenAICompatibleClient(BaseLLMClient):
    """通用 OpenAI 兼容 API 客户端。

    通过标准的 /chat/completions 端点调用任何兼容 OpenAI 格式的 LLM 服务。

    Attributes:
        base_url: API 基础 URL
        model: 使用的模型名称
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        **kwargs,
    ):
        if api_key is None:
            api_key = settings.models.llm_api_key
        if base_url is None:
            base_url = settings.models.llm_base_url or ""
        if model is None:
            model = "gpt-3.5-turbo"

        if not api_key:
            logger.warning("LLM_API_KEY 未配置，LLM 调用将失败")

        super().__init__(api_key=api_key or "", **kwargs)
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.provider = "openai_compatible"

    def call(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 1000,
        response_format: str = "json",
    ) -> str:
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        url = f"{self.base_url}/chat/completions"

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=self.timeout)
            response.raise_for_status()
        except requests.HTTPError as e:
            log_llm_error(
                error=e,
                provider=self.provider,
                prompt=prompt,
                response=response.text if hasattr(response, "text") else None,
            )
            raise
        except requests.Timeout as e:
            log_llm_error(error=e, provider=self.provider, prompt=prompt, response=None)
            raise TimeoutError(f"LLM API timeout after {self.timeout}s") from e

        result = response.json()
        content = result["choices"][0]["message"]["content"]

        self.last_response = content
        logger.debug(f"LLM raw response length: {len(content)}")

        if response_format == "json":
            try:
                return parse_json(content)
            except ValueError as e:
                logger.error(f"JSON parsing failed: {content[:500]}")
                log_llm_error(error=e, provider=self.provider, prompt=prompt, response=content)
                raise

        return content
