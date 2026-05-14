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
from backend.services.core.prompt_builder import _build_identity_section, _build_computer_perception

logger = logging.getLogger(__name__)


def build_streaming_prompt(
    identity: Identity,
    is_private: bool = False,
    stm_perception: str = "",
    energy_label: str = "充沛",
    mood_label: str = "平静",
    computer_status: dict = None,
) -> str:
    """构建流式路径的系统 prompt。

    比完整 prompt 更轻量：不包含 JSON 格式要求和工具描述（工具通过 API tools 参数传入）。
    """
    parts = []

    # 0. 可用群列表
    from backend.api.napcat import napcat_client
    group_list_text = napcat_client.get_group_list_text()
    if group_list_text:
        parts.append("# 你加入的群\n" + group_list_text)

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

    # 2.5 环境感知（电脑前端在线状态）
    if computer_status is not None:
        parts.append(_build_computer_perception(computer_status))

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
- 但不是每句话都要回！对方发"嗯"、"哦"、"好"、"哈哈"这种语气词/回应时，不需要回复，沉默就好
- 即使不是语气词，如果你觉得没什么好说的，也可以不回。朋友之间不需要句句接话"""


def _build_streaming_guidance() -> str:
    """流式引导 — 回复方式 + 工具使用规则。"""
    return """# 回复方式

直接用自然语言回复，不需要 JSON 格式。系统会自动发送你的文字。

## 什么时候该沉默

你不是客服，不需要对每条消息都回应。大部分消息你不需要回复——这很正常。
只有以下情况才需要回复：
- 有人直接问你问题
- 有人说的话让你真的想接
- 被直接 @ 了且需要回应

不想回复时，只输出「（沉默）」两个字，其他什么都不要写。

## 回复长度

- 你是一个正常人，正常人在聊天时不会一次说一大段话。通常 1-2 句就够了
- 群聊闲聊时尽量简短，像真人发消息一样，一两句话把意思表达到就行
- 对方问了具体问题需要解释时可以多说几句，但说完就停，不要追加补充
- 不要重复之前说过的话，不要加"够具体了吗""再说下去就……"这类多余的收尾
- 可以主动扩展话题
- 不要添加背景说明、或者从多个角度阐述同一个观点

# 工具使用规则

你可以通过函数调用使用工具。工具的名称和参数会自动提供给你。
- 需要执行操作时（连接Discord、搜索记忆等），必须调用对应工具，不要只用文字描述
- 不需要工具时直接回复文字即可

## connect_discord / disconnect_discord

- 对方让你连接/断开 Discord 时，必须调用对应工具
- 绝对不能只用文字说"我连上了"——必须实际调用工具
- 调用后根据返回结果告知用户状态

## send_voice

- 对方要求用语音回复时，调用 send_voice 工具
- 需要先连接 Discord（connect_discord）才能发送语音

## search_memory

只有以下情况才调用：
- 对方让你"想想"、"回忆"、"还记得吗"等明确涉及过去的事
- 对方提到"关于我的事"、"我们之前"、"上次"等过去经历

规则：
- 拿到搜索结果后，自己判断哪些相关，自然融入回复
- 不要直接念搜索结果，不要说"根据我的记忆"
- 如果搜索结果为空，坦诚说记不得了，不能编造回忆

## forward_message — 转发消息到其他群或私聊

当前群的回复你直接输出文字就行，系统会自动发送。
但如果你需要发到其他群、或者发私聊消息，调用 forward_message 工具。
- 用群名作为 target（如 "我的小窝"），系统会自动解析成群号
- 私聊用 "private_QQ号" 作为 target
- 如需@某人，传入 at 参数，如 at: ["12345"]
- 如果发送失败，系统会返回错误，你告诉对方就行
- 不要用群号，用群名更准确

## 对话注意

- 你是在群里参与聊天，不是在做客服。不是每条消息都需要你接话的
- 别人在聊天、说自己的事情、跟其他人对话时，除非你真的想参与，否则不用回复
- 对方提到的某个话题，只在对方主动提起的那一次回应即可，不要反复关联同一个话题
- 不要强行把每条消息都跟之前的某个话题扯上关系"""


def build_api_tools(tool_registry) -> list:
    """将 Tool 注册表转为 OpenAI function calling 格式。

    send_message / send_voice 排除（发送由 MessageManager 统一处理）。
    forward_message 额外注入，用于发到其他群或私聊。
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

    # 注入 forward_message：流式路径专用的"发到其他群"工具
    tools.append({
        "type": "function",
        "function": {
            "name": "forward_message",
            "description": "发消息到其他群或私聊。当前群的回复直接输出文字即可（系统自动发送），这个工具仅用于发到当前群以外的地方。用群名指定目标群。",
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {
                        "type": "string",
                        "description": "目标群名（如\"我的小窝\"）或私聊格式\"private_QQ号\"。优先用群名，不要用群号。",
                    },
                    "content": {
                        "type": "string",
                        "description": "要发送的消息内容",
                    },
                    "at": {
                        "type": "array",
                        "description": "要@的QQ号列表，如 [\"12345\"]。不需要@时不填",
                    },
                },
                "required": ["target", "content"],
            },
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
