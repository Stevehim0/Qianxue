"""发送消息工具 - 包装napcat_client.send_group_message."""

import asyncio
import logging
import re
from typing import Dict, List

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


# 按句末标点和换行拆分，标点保留在前一条末尾
# 拆分标点：，。！？\n
_SPLIT_PUNCTS = re.compile(r'[，。！？\n]+')
# 拆分后要去掉的标点（，。）
_STRIP_PUNCTS = re.compile(r'[，。]+$')

# 匹配 @[12345] 格式转换为 CQ @码
_AT_PATTERN = re.compile(r'@\[(\d+)\]')


def _split_message(text: str) -> List[str]:
    """将长文本按标点拆成多条消息。，。拆分后去掉，！？保留。"""
    text = text.strip()
    if not text:
        return []

    parts: list[str] = []
    last = 0
    for m in _SPLIT_PUNCTS.finditer(text):
        end = m.end()
        seg = text[last:end].strip()
        if seg:
            # ，。结尾的去掉标点
            seg = _STRIP_PUNCTS.sub('', seg)
            if seg:
                parts.append(seg)
        last = end

    # 剩余部分
    tail = text[last:].strip()
    if tail:
        parts.append(tail)

    return parts if parts else [text]


def _convert_at_codes(text: str) -> str:
    """将 AI 输出的 @[QQ号] 格式转换为 QQ CQ码 [CQ:at,qq=QQ号]。"""
    return _AT_PATTERN.sub(r'[CQ:at,qq=\1]', text)


class SendMessageTool(Tool):
    """发送消息工具

    直接发送消息到群聊，不调用 LLM（思考模型已生成完整回复）
    长文本自动拆成多条小句发送，模拟真人打字节奏。
    支持 QQ 和 Discord 双路由。
    """

    @property
    def name(self) -> str:
        return "send_message"

    @property
    def description(self) -> str:
        return ("发送消息到群聊或私聊。直接写完整回复即可，系统会自动拆成小句发送。支持QQ和Discord。"
                "你可以发到任何QQ群，只要把群号作为 group_id 传入即可（如 group_id: \"123456789\"）。"
                "也可以发私聊消息，group_id 格式为 \"private_QQ号\"。"
                "群聊中如需@某人，传入 at 参数（QQ号数组），对方会收到提醒。")

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
                description="要发送的消息内容（完整文本，无需手动拆分）",
                required=True
            ),
            ToolArgument(
                name="at",
                type="array",
                description="要@的QQ号列表，如 [\"12345\"] 或 [\"12345\",\"67890\"]。不需要@时不要填",
                required=False
            )
        ]

    async def _send_to_discord(self, group_id: str, chunks: list[str]) -> tuple[bool, list[str]]:
        """Send message chunks to Discord. Returns (success, sent_chunks)."""
        from backend.services.agent.sources.discord_source import discord_source

        if discord_source is None or not discord_source.is_connected():
            return False, []

        is_private = group_id.startswith("dm_")
        sent_chunks = []
        for chunk in chunks:
            success = await discord_source.send_message(
                channel_id=group_id,
                text=chunk,
                is_private=is_private
            )
            if success:
                sent_chunks.append(chunk)
            else:
                break
            if len(chunks) > 1 and chunk != chunks[-1]:
                await asyncio.sleep(0.3)
        return len(sent_chunks) > 0, sent_chunks

    async def execute(self, **kwargs) -> Dict:
        group_id = kwargs.get("group_id")
        content = kwargs.get("content")
        at_list = kwargs.get("at") or []

        if not group_id or not content:
            return {"success": False, "error": "缺少必要参数"}

        is_private = group_id.startswith("private_")
        is_computer = group_id == "computer_home"

        # 构建 @ 前缀（QQ 群聊才生效）
        at_prefix = ""
        if at_list and not is_computer and not is_private:
            at_prefix = "".join(f"[CQ:at,qq={qq}] " for qq in at_list)

        # 阀门过滤
        filter_result = _get_valve_filter().check(content)
        if not filter_result.passed:
            logger.warning(f"消息被阀门拦截: {filter_result.reason}")
            return {"success": False, "error": f"消息被过滤: {filter_result.reason}"}

        # 自动拆分，并在第一条消息前加上 @ 前缀
        chunks = _split_message(content)
        # QQ 群聊路由下将 @[QQ号] 转为 CQ @码
        if not is_computer and not is_private:
            chunks = [_convert_at_codes(c) for c in chunks]
            if at_prefix and chunks:
                chunks[0] = at_prefix + chunks[0]
        sent_chunks: list[str] = []

        # 本地电脑路由
        if is_computer:
            try:
                from backend.routes.computer_routes import send_to_computer
                for chunk in chunks:
                    await send_to_computer(chunk)
                    sent_chunks.append(chunk)
                full_reply = "".join(sent_chunks)

                # 上下文存储
                await context_manager.add_group_message(
                    group_id=group_id,
                    user_id="robot",
                    role="assistant",
                    content=full_reply,
                    sender_nickname="机器人",
                    mentions=[],
                    is_directed_at_bot=False
                )

                # 记忆系统
                try:
                    asyncio.create_task(
                        mem_mod.memory_provider.extract_and_store(
                            group_id=group_id,
                            user_id="robot",
                            content=full_reply,
                            role="assistant",
                            speaker="千雪",
                            source_type="computer_chat",
                        )
                    )
                except Exception:
                    pass

                # STM
                try:
                    from backend.services.stm_client import stm_client
                    asyncio.create_task(stm_client.record_event(
                        event_type="ai_reply",
                        source_type="computer_chat",
                        group_id=group_id,
                        summary=f"你回复了: {full_reply[:60]}",
                        importance=0.6,
                    ))
                except Exception:
                    pass

                logger.info(f"电脑聊天回复发送成功: {full_reply[:50]}...")
                return {"success": True, "message": full_reply, "group_id": group_id}

            except Exception as e:
                logger.error(f"电脑聊天回复发送失败: {e}", exc_info=True)
                return {"success": False, "error": str(e)}

        # Discord 路由判断
        is_discord = False
        if group_id.startswith("dm_"):
            is_discord = True
        else:
            try:
                ctx_msgs = context_manager.get_recent_messages(group_id, limit=1)
                if ctx_msgs:
                    last_msg = ctx_msgs[-1]
                    is_discord = getattr(last_msg, 'source', '') == 'discord'
            except Exception:
                pass

        try:
            # Discord 路由
            if is_discord:
                success, sent_chunks = await self._send_to_discord(group_id, chunks)
                if not success:
                    return {"success": False, "error": "Discord 消息发送失败"}

                full_reply = "".join(sent_chunks)
                # 上下文存储
                await context_manager.add_group_message(
                    group_id=group_id,
                    user_id="robot",
                    role="assistant",
                    content=full_reply,
                    sender_nickname="机器人",
                    mentions=[],
                    is_directed_at_bot=False
                )

                # 记忆系统
                try:
                    source_type = "discord_private" if group_id.startswith("dm_") else "discord_channel"
                    asyncio.create_task(
                        mem_mod.memory_provider.extract_and_store(
                            group_id=group_id,
                            user_id="robot",
                            content=full_reply,
                            role="assistant",
                            speaker="千雪",
                            source_type=source_type,
                        )
                    )
                except Exception:
                    pass

                # STM
                try:
                    from backend.services.stm_client import stm_client
                    asyncio.create_task(stm_client.record_event(
                        event_type="ai_reply",
                        source_type="discord_private" if group_id.startswith("dm_") else "discord_channel",
                        group_id=group_id,
                        summary=f"你回复了: {full_reply[:60]}",
                        importance=0.6,
                    ))
                except Exception:
                    pass

                chat_type = "Discord私聊" if group_id.startswith("dm_") else "Discord频道"
                logger.info(f"{chat_type}回复发送成功: {full_reply[:50]}...")
                return {"success": True, "message": full_reply, "group_id": group_id}

            # QQ 路由（原有逻辑）
            for chunk in chunks:
                if is_private:
                    target_user_id = int(group_id.replace("private_", ""))
                    success = await napcat_client.send_private_message(target_user_id, chunk)
                else:
                    success = await napcat_client.send_group_message(int(group_id), chunk)

                if success:
                    sent_chunks.append(chunk)
                else:
                    logger.warning(f"消息片段发送失败: {chunk[:30]}")
                    break

                # 多条消息之间稍微间隔，模拟打字
                if len(chunks) > 1 and chunk != chunks[-1]:
                    await asyncio.sleep(0.3)

            if not sent_chunks:
                return {"success": False, "error": "回复发送失败"}

            # 上下文只存完整消息（不存碎片）
            full_reply = "".join(sent_chunks)
            await context_manager.add_group_message(
                group_id=group_id,
                user_id=str(napcat_client.self_id),
                role="assistant",
                content=full_reply,
                sender_nickname="机器人",
                mentions=[],
                is_directed_at_bot=False
            )

            # 记忆系统
            try:
                source_type = "qq_private" if is_private else "qq_group"
                asyncio.create_task(
                    mem_mod.memory_provider.extract_and_store(
                        group_id=group_id,
                        user_id=str(napcat_client.self_id),
                        content=full_reply,
                        role="assistant",
                        speaker="千雪",
                        source_type=source_type,
                    )
                )
            except Exception:
                pass

            # STM
            try:
                from backend.services.stm_client import stm_client
                asyncio.create_task(stm_client.record_event(
                    event_type="ai_reply",
                    source_type="qq_private" if is_private else "qq_group",
                    group_id=group_id,
                    summary=f"你回复了: {full_reply[:60]}",
                    importance=0.6,
                ))
            except Exception:
                pass

            chat_type = "私聊" if is_private else "群聊"
            logger.info(f"{chat_type}回复发送成功: {full_reply[:50]}... ({len(sent_chunks)}条)")
            return {"success": True, "message": full_reply, "group_id": group_id}

        except Exception as e:
            logger.error(f"发送消息失败: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
