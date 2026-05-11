"""本地电脑消息源 — 构造 AgentMessage 的工厂函数."""

from backend.services.agent.message import AgentMessage


def build_computer_message(content: str, user_id: str = "host_user") -> AgentMessage:
    """构造来自本地电脑聊天的 AgentMessage.

    - source="computer": 标识本地聊天
    - group_id="computer_home": 固定会话 ID
    - is_mentioned=True: 本地聊天默认就是跟千雪说话
    - priority=10: 等同 @消息，跳过 debounce 立即处理
    """
    return AgentMessage(
        source="computer",
        group_id="computer_home",
        user_id=user_id,
        sender_nickname="主人",
        content=content,
        is_mentioned=True,
        priority=10,
    )
