"""LLM客户端服务模块。

提供统一的LLM调用接口，支持千问和DeepSeek两个提供商。

主要组件:
- BaseLLMClient: LLM客户端抽象基类
- LLMFactory: 工厂类，用于创建不同提供商的客户端
- QianwenClient: 千问API客户端实现
- DeepSeekClient: DeepSeek API客户端实现
- parse_json: JSON解析工具函数（处理markdown包裹）
- with_retry: 指数退避重试装饰器
- setup_error_logger: 错误日志记录器配置
- log_llm_error: LLM错误详情记录

使用示例:
    >>> from Memory.llm import LLMFactory
    >>>
    >>> # 创建千问客户端（默认）
    >>> client = LLMFactory.create_client()
    >>> response = client.call("你好", temperature=0.3)
    >>>
    >>> # 创建DeepSeek客户端
    >>> client = LLMFactory.create_client(provider="deepseek")
    >>> response = client.call("Hello")
"""

# 基类和工厂
from Memory.llm.base import BaseLLMClient
from Memory.llm.factory import LLMFactory

# 具体客户端实现
from Memory.llm.qianwen_client import QianwenClient
from Memory.llm.deepseek_client import DeepSeekClient

# 工具函数
from Memory.llm.utils import parse_json, with_retry, setup_error_logger, log_llm_error

__all__ = [
    # 基类和工厂
    "BaseLLMClient",
    "LLMFactory",
    # 具体客户端
    "QianwenClient",
    "DeepSeekClient",
    # 工具函数
    "parse_json",
    "with_retry",
    "setup_error_logger",
    "log_llm_error",
]
