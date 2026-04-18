"""发送消息工具 - 包装napcat_client.send_group_message."""

import asyncio
import logging
from typing import Dict, Any

from .base import Tool, ToolArgument
from backend.api.napcat import napcat_client
from backend.services.context_manager import context_manager
from backend.services.core.valve_filter import ValveFilter
from backend.services.core.loader import identity_loader

import backend.services.memory_interface as mem_mod


logger = logging.getLogger(__name__)

# 阀门过滤器（延迟初始化）
_valve_filter: ValveFilter | None = None


def _get_valve_filter() -> ValveFilter:
    """获取阀门过滤器单例。"""
    global _valve_filter
    if _valve_filter is None:
        _valve_filter = ValveFilter(identity_loader.identity)
    return _valve_filter


class SendMessageTool(Tool):
    """发送消息工具

    直接发送消息到群聊，不调用 LLM（思考模型已生成完整回复）
    """

    MAX_MESSAGE_LENGTH = 20  # 单条消息最大字数

    @property
    def name(self) -> str:
        return "send_message"

    @property
    def description(self) -> str:
        return (
            "发送消息到QQ群聊。"
            f"单条消息不能超过{self.MAX_MESSAGE_LENGTH}字，超出会被截断。"
            "长内容请分多次调用。"
        )

    @property
    def arguments(self) -> list:
        return [
            ToolArgument(
                name="group_id",
                type="string",
                description="群聊ID",
                required=True
            ),
            ToolArgument(
                name="content",
                type="string",
                description="要发送的消息内容",
                required=True
            )
        ]

    async def execute(self, **kwargs) -> Dict[str, Any]:
        """
        执行发送消息 - 直接发送，不调用 LLM

        支持群聊和私聊两种模式，通过 group_id 前缀 "private_" 区分。

        Args:
            group_id: 群聊ID（或 private_{user_id} 格式的私聊ID）
            content: 要发送的消息内容

        Returns:
            执行结果
        """
        group_id = kwargs.get("group_id")
        content = kwargs.get("content")

        if not group_id or not content:
            return {"success": False, "error": "缺少必要参数"}

        # 判断是否为私聊
        is_private = group_id.startswith("private_")

        # 截断过长消息
        truncated = False
        original_length = len(content)
        if original_length > self.MAX_MESSAGE_LENGTH:
            truncated = True
            content = content[:self.MAX_MESSAGE_LENGTH]
            logger.warning(
                f"消息被截断: {original_length} → {self.MAX_MESSAGE_LENGTH} 字"
            )

        try:
            # 阀门过滤：检查是否违反不变层底线
            filter_result = _get_valve_filter().check(content)
            if not filter_result.passed:
                logger.warning(f"消息被阀门拦截: {filter_result.reason}")
                return {"success": False, "error": f"消息被过滤: {filter_result.reason}"}

            # 直接发送
            reply = content

            # 发送到 NapCat（区分群聊/私聊）
            if is_private:
                target_user_id = int(group_id.replace("private_", ""))
                success = await napcat_client.send_private_message(target_user_id, reply)
            else:
                success = await napcat_client.send_group_message(int(group_id), reply)

            if success:
                # 将AI回复添加到上下文
                await context_manager.add_group_message(
                    group_id=group_id,
                    user_id=str(napcat_client.self_id),
                    role="assistant",
                    content=reply,
                    sender_nickname="机器人",
                    mentions=[],
                    is_directed_at_bot=False
                )

                # AI回复也送入记忆系统缓冲（fire-and-forget）
                try:
                    source_type = "qq_private" if is_private else "qq_group"
                    asyncio.create_task(
                        mem_mod.memory_provider.extract_and_store(
                            group_id=group_id,
                            user_id=str(napcat_client.self_id),
                            content=reply,
                            role="assistant",
                            speaker="Iris",
                            source_type=source_type,
                        )
                    )
                except Exception:
                    pass

                # STM: 记录 AI 回复事件
                try:
                    from backend.services.stm_client import stm_client
                    asyncio.create_task(stm_client.record_event(
                        event_type="ai_reply",
                        source_type=source_type,
                        group_id=group_id,
                        summary=f"你回复了: {reply[:60]}",
                        importance=0.6,
                    ))
                except Exception:
                    pass

                chat_type = "私聊" if is_private else "群聊"
                logger.info(f"{chat_type}回复发送成功: {reply[:50]}...")
                result = {
                    "success": True,
                    "message": reply,
                    "group_id": group_id,
                }
                if truncated:
                    result["truncated"] = True
                    result["original_length"] = original_length
                    result["max_length"] = self.MAX_MESSAGE_LENGTH
                    result["hint"] = (
                        f"消息超过{self.MAX_MESSAGE_LENGTH}字被截断，"
                        "剩余内容请再调一次 send_message 发送"
                    )
                return result
            else:
                return {"success": False, "error": "回复发送失败"}

        except Exception as e:
            logger.error(f"发送消息失败: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
