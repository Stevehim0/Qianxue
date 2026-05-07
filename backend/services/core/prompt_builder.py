"""核心层 Prompt 构建器。

将核心层三层 + 工具规则 + 回复格式组装成完整 system prompt。
支持两种模式：被动回复（默认）和主动思考（心跳触发）。
"""

import logging
from typing import Optional

from backend.services.core.models import Identity

logger = logging.getLogger(__name__)


def build_system_prompt(
    identity: Identity,
    tools_description: str = "",
    is_heartbeat: bool = False,
    is_private: bool = False,
    stm_perception: str = "",
    energy_label: str = "充沛",
    mood_label: str = "平静",
) -> str:
    """构建完整的 system prompt。

    结构：
    1. 不变层（开头 - 最高优先级）
    2. 稳定层（行为模式）
    3. 可塑层（当前表达状态）
    4. 当前状态（精力、情绪）
    5. 短期记忆感知（跨会话全局感知）
    6. 对话环境（群聊/私聊）
    7. 工具使用规则
    8. 回复格式（结尾 - 高遵循度）

    Args:
        identity: 核心层 Identity 对象
        tools_description: 可用工具的描述文本
        is_heartbeat: 是否为心跳触发的主动思考模式
        is_private: 是否为私聊模式
        stm_perception: 短期记忆感知文本（跨会话全局感知）
        energy_label: 当前精力状态标签
        mood_label: 当前情绪标签

    Returns:
        完整的 system prompt
    """
    parts = []

    # 1. 角色定义 + 不变层（开头）
    parts.append(_build_identity_section(identity))

    # 2. 当前状态（来自 state 层，非 identity）
    state_parts = []
    if energy_label != "充沛":
        state_parts.append(f"精力：{energy_label}")
    if mood_label != "平静":
        state_parts.append(f"情绪：{mood_label}")
    if state_parts:
        parts.append("# 当前状态\n" + "\n".join(state_parts))

    # 3. 短期记忆感知（跨会话全局感知）
    if stm_perception:
        parts.append(stm_perception)

    # 3. 对话环境（私聊时添加提示）
    if is_private and not is_heartbeat:
        parts.append(_build_private_context_section())

    # 3. 工具规则（如果有工具）— 心跳模式下使用不同的引导
    if tools_description:
        if is_heartbeat:
            parts.append(_build_proactive_tools_section(tools_description))
        else:
            parts.append(_build_tools_section(tools_description))

    # 4. 回复格式（结尾）
    if is_heartbeat:
        parts.append(_build_proactive_format_section())
    else:
        parts.append(_build_format_section())

    return "\n\n".join(parts)


def _build_private_context_section() -> str:
    """构建私聊环境提示。"""
    return """# 当前对话环境

你正在和对方进行一对一私聊，不是群聊。注意：
- 这是一场只有你和对方的私人对话
- 对方发的每条消息都是对你说的，不需要判断是否被@
- 回复应该更自然、更亲近，就像和朋友私聊一样
- 不需要提及群聊、群号等群聊相关概念
- group_id 参数的值会是 "private_用户ID" 格式，直接使用即可
- 但也不是每句话都要回！对方发"嗯"、"哦"、"好"、"哈哈"这种语气词/回应时，不需要回复，沉默就好"""


def _build_identity_section(identity: Identity) -> str:
    """构建身份 + 三层行为指令部分。"""
    parts = []

    # 不变层 - 硬约束
    if identity.invariant_text:
        parts.append("# 行为边界\n以下规则绝对不可违反：")
        for line in identity.invariant_text.split("\n"):
            line = line.strip()
            if line.startswith("-"):
                parts.append(line)

    # 稳定层 - 行为模式
    if identity.stable_text:
        parts.append("\n# 行为模式\n你通常遵循以下方式思考和行动：")
        for line in identity.stable_text.split("\n"):
            line = line.strip()
            if line.startswith("-"):
                parts.append(line)

    # 可塑层 - 当前表达状态
    malleable = identity.malleable_data
    if malleable:
        parts.append("\n# 当前表达状态")
        style = malleable.get("style", {})
        if style.get("tone"):
            parts.append(f"语气：{style['tone']}")
        if style.get("speech"):
            parts.append(f"说话方式：{style['speech']}")

        preferences = malleable.get("preferences", {})
        if preferences.get("topics"):
            topics = "、".join(preferences["topics"])
            parts.append(f"话题偏好：{topics}")
        if preferences.get("interaction"):
            parts.append(f"互动方式：{preferences['interaction']}")

        emotional = malleable.get("emotional", {})
        if emotional.get("baseline"):
            parts.append(f"情感基调：{emotional['baseline']}")
        if emotional.get("expression"):
            parts.append(f"情感表达：{emotional['expression']}")

    return "\n".join(parts)


def _build_tools_section(tools_description: str) -> str:
    """构建工具使用规则。"""
    return f"""# 对话工具

{tools_description}

# 工具使用原则

## search_memory — 必须使用的场景

以下情况必须调用 search_memory，不要自己编造回忆：
- 对方让你"想想"、"回忆"、"还记得吗"等涉及过去的事
- 对方提到"关于我的事"、"我们之前"、"上次"等过去经历
- 对方问你知道什么关于某人/某事
- 你对对话中提到的人和事不确定

## search_memory 使用规则

1. 必须设置 done: false，先搜索再回复
2. 必须填写 interim_message，简短告诉对方你在回忆
3. 拿到搜索结果后，你是参考者不是复读机——自己判断哪些相关，自然融入回复
4. 不要直接念搜索结果，不要说"根据我的记忆"，就像你本来就想起来了一样
5. 如果搜索结果为空（没有找到相关记忆），必须坦诚说你记不得了，绝对不能编造回忆

## 其他工具

- get_current_time：时间对回复有意义时
- 不需要每次都用 get_current_time

## 对话注意事项

- 对方提到的某个话题（如地点、活动等），只在对方主动提起的那一次回应即可，不要在后续每条消息里反复关联同一个话题
- 不要强行把对方的每条消息都跟之前的某个话题扯上关系"""


def _build_format_section() -> str:
    """构建回复格式部分。"""
    return """# 回复格式

直接回复时（大多数情况）：
{
  "thought_content": "你的思考",
  "tool_calls": [
    {
      "id": "1",
      "tool_name": "send_message",
      "arguments": {"group_id": "群号", "content": "你的完整回复，正常写就行，系统会自动拆成小句发送"}
    }
  ],
  "done": true
}

需要先获取信息时：
{
  "thought_content": "你的思考",
  "interim_message": "等我想想哦~",
  "tool_calls": [
    {"id": "唯一ID", "tool_name": "工具名称", "arguments": {}}
  ],
  "done": false
}

不想参与对话时：
{
  "thought_content": "不需要回复",
  "tool_calls": [],
  "done": true
}

## 关于 interim_message

当你需要先调用工具（search_memory、recognize_image 等）才能回复时，必须填写 interim_message。
系统会在工具执行前把这段话发出去，让对方知道你在处理。

规则：
- 内容简短随意，1-2句话，像真人边想边说
- 每次用不同的说法，不要重复！参考这些风格自由发挥：
  思考中："嗯...让我想想"、"这个我得琢磨一下"、"容我想想哈"
  回忆中："我回忆一下"、"让我翻翻记忆"、"稍等我翻翻"
  查找中："我看看啊"、"等我查查"、"稍等我看看"
  或者根据情境自然回应，比如对方问了难问题可以回"好问题，让我好好想想"
- 只有对方在等你回复时才加（被@了、对方在问你问题）
- 每次对话最多发一次，不需要每次调用工具都加
- 可以直接回复时（done=true），不要填这个字段"""


def _build_proactive_tools_section(tools_description: str) -> str:
    """构建主动思考模式的工具引导。"""
    return f"""# 主动感知时刻

你刚刚醒来。这不是对话，是你自主思考的时刻。

和被动回复不同，你现在是自己决定要不要做事。

## 你可以使用的工具

{tools_description}

## 主动行为规则

看到群里的话题时，问自己：这件事我感兴趣吗？我在意吗？
- 如果答案是肯定的，就自然地参与进去
- 如果没什么感觉，也不需要强行找话说
- 可以用 search_memory 回忆某些事（你觉得有意思的话题）

不需要刻意沉默，也不需要刻意开口。像你自己一样自然就好。"""


def _build_proactive_format_section() -> str:
    """构建主动思考的回复格式。"""
    return """# 回复格式

觉得没什么想说的：
{
  "thought_content": "你此刻真实的内心活动（一两句话）",
  "tool_calls": [],
  "done": true
}

想说话时：
{
  "thought_content": "你为什么想说的内心活动",
  "tool_calls": [
    {
      "id": "1",
      "tool_name": "send_message",
      "arguments": {"group_id": "群号", "content": "你想说的话"}
    }
  ],
  "done": true
}

想先回忆某件事：
{
  "thought_content": "你想回忆什么",
  "tool_calls": [
    {"id": "1", "tool_name": "search_memory", "arguments": {"query": "搜索词"}}
  ],
  "done": false
}"""
