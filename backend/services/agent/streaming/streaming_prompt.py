"""流式系统 Prompt 构建器.

与完整 prompt_builder 的区别：
- 不需要 JSON 格式要求 — LLM 直接输出自然语言
- 不需要在 prompt 里描述工具 — 工具通过 API tools 参数传入
- 保留身份层和状态 — 复用 prompt_builder._build_identity_section()
- 保留 STM 感知 — 复用现有 STM 数据
- 添加简短引导
"""

import logging
from typing import Optional

from backend.services.core.models import Identity
from backend.services.core.prompt_builder import _build_identity_section

logger = logging.getLogger(__name__)


def build_streaming_prompt(
    identity: Identity,
    is_private: bool = False,
    stm_perception: str = "",
    energy_label: str = "充沛",
    mood_label: str = "平静",
) -> str:
    """构建流式路径的系统 prompt。

    比完整 prompt 更轻量：不包含 JSON 格式要求和工具描述（工具通过 API tools 参数传入）。
    """
    parts = []

    # 1. 身份层（复用 prompt_builder 的函数）
    parts.append(_build_identity_section(identity))

    # 2. 当前状态
    state_parts = []
    if energy_label != "充沛":
        state_parts.append(f"精力：{energy_label}")
    if mood_label != "平静":
        state_parts.append(f"情绪：{mood_label}")
    if state_parts:
        parts.append("# 当前状态\n" + "\n".join(state_parts))

    # 3. 短期记忆感知
    if stm_perception:
        parts.append(stm_perception)

    # 4. 私聊环境提示
    if is_private:
        parts.append(_build_private_hint())

    # 5. 流式引导（替代完整的格式要求）
    parts.append(_build_streaming_guidance())

    return "\n\n".join(parts)


def _build_private_hint() -> str:
    """私聊环境提示。"""
    return """# 当前对话环境

你正在和对方进行一对一私聊，不是群聊。注意：
- 这是一场只有你和对方的私人对话
- 对方发的每条消息都是对你说的，不需要判断是否被@
- 回复应该更自然、更亲近，就像和朋友私聊一样
- 但也不是每句话都要回！对方发"嗯"、"哦"、"好"、"哈哈"这种语气词/回应时，不需要回复，沉默就好"""


def _build_streaming_guidance() -> str:
    """流式引导 — 告诉 LLM 直接输出自然语言，需要工具时调用工具。"""
    return """# 回复方式

直接用自然语言回复。如果需要搜索记忆等操作，调用工具。
- 不要用 JSON 格式，直接输出文字
- 需要使用工具时调用工具，不需要时直接回复
- 不想回复时可以不输出任何内容"""


def build_api_tools(tool_registry) -> list:
    """将 Tool 注册表转为 OpenAI function calling 格式。

    排除流式路径不需要的工具（send_message、send_voice），
    因为发送已由 MessageManager 统一处理。
    """
    EXCLUDED_TOOLS = {"send_message", "send_voice"}
    tools = []

    for name in tool_registry.list_tools():
        if name in EXCLUDED_TOOLS:
            continue

        tool = tool_registry.get(name)
        if not tool:
            continue

        parameters = {
            "type": "object",
            "properties": {},
            "required": [],
        }

        for arg in tool.arguments:
            parameters["properties"][arg.name] = {
                "type": _map_type(arg.type),
                "description": arg.description,
            }
            if arg.default is not None:
                parameters["properties"][arg.name]["default"] = arg.default
            if arg.required:
                parameters["required"].append(arg.name)

        tools.append({
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": parameters,
            }
        })

    return tools


def _map_type(tool_type: str) -> str:
    """将工具参数类型映射到 JSON Schema 类型。"""
    mapping = {
        "string": "string",
        "integer": "integer",
        "boolean": "boolean",
        "array": "array",
        "object": "object",
        "number": "number",
    }
    return mapping.get(tool_type, "string")
