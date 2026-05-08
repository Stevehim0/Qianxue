"""上下文管理模块."""

import logging
import json
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from backend.database.db import get_db
from backend.database.models import (
    ConversationMessage, Group, UserProfile, GlobalContext,
    MentionInfo, GroupMessage
)
from backend.db_config import config_manager
from backend.config.loader import settings
from backend.services.memory_interface import memory_provider


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ContextManager:
    """对话上下文管理器"""

    # 已确认存在的用户/群（启动后首次查 DB，后续跳过检查）
    _known_users: set[str] = set()
    _known_groups: set[str] = set()

    async def add_message(self, group_id: str, user_id: str, role: str, content: str):
        """添加对话消息到上下文"""
        conn = await get_db()

        await conn.execute(
            """
            INSERT INTO conversations (group_id, user_id, role, content)
            VALUES (?, ?, ?, ?)
            """,
            (group_id, user_id, role, content)
        )
        await conn.commit()

        # 检查是否需要清理旧消息
        await self._cleanup_old_messages(conn, group_id, user_id)

        logger.info(f"已添加消息: group={group_id}, user={user_id}, role={role}")

    async def _cleanup_old_messages(self, conn, group_id: str, user_id: str):
        """清理超过窗口大小的旧消息"""
        window_size = config_manager.context_window

        # 获取该用户在该群的消息总数
        cursor = await conn.execute(
            """
            SELECT COUNT(*) FROM conversations
            WHERE group_id = ? AND user_id = ?
            """,
            (group_id, user_id)
        )
        count_result = await cursor.fetchone()
        total_count = count_result[0] if count_result else 0

        # 如果超过窗口大小，删除最旧的消息
        if total_count > window_size:
            # 获取要保留的ID列表（最新的N条）
            cursor = await conn.execute(
                """
                SELECT id FROM conversations
                WHERE group_id = ? AND user_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (group_id, user_id, window_size)
            )
            keep_ids = [row[0] for row in await cursor.fetchall()]

            # 删除不在保留列表中的消息
            if keep_ids:
                placeholders = ",".join(["?"] * len(keep_ids))
                await conn.execute(
                    f"""
                    DELETE FROM conversations
                    WHERE group_id = ? AND user_id = ?
                    AND id NOT IN ({placeholders})
                    """,
                    [group_id, user_id] + keep_ids
                )
                await conn.commit()
                logger.info(f"已清理 {total_count - len(keep_ids)} 条旧消息")

    async def get_context_with_time_filter(
        self,
        group_id: str,
        user_id: str,
        hours_limit: int = 4,
        max_messages: int = 10
    ) -> List[ConversationMessage]:
        """
        获取带时间过滤的对话上下文

        Args:
            group_id: 群聊ID
            user_id: 用户ID
            hours_limit: 时间限制（小时），超过该时间的对话需要更高相关性才会关联
            max_messages: 最大消息数量

        Returns:
            过滤后的对话消息列表
        """
        conn = await get_db()

        time_threshold = datetime.now() - timedelta(hours=hours_limit)

        cursor = await conn.execute(
            """
            SELECT id, group_id, user_id, role, content, timestamp
            FROM conversations
            WHERE group_id = ? AND user_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (group_id, user_id, max_messages)
        )

        rows = await cursor.fetchall()

        messages = []
        for row in rows:
            # 解析时间戳
            msg_time_str = row[5]
            try:
                msg_time = datetime.fromisoformat(msg_time_str)
            except Exception:
                msg_time = datetime.now()

            # 只包含时间阈值内的消息
            if msg_time >= time_threshold:
                messages.append(ConversationMessage(
                    id=row[0],
                    group_id=row[1],
                    user_id=row[2],
                    role=row[3],
                    content=row[4],
                    timestamp=msg_time_str
                ))
            else:
                logger.info(f"跳过旧消息: time={msg_time_str}, threshold={time_threshold}")

        logger.info(f"时间过滤后剩余 {len(messages)} 条消息（最近{hours_limit}小时内）")
        return messages

    async def get_context(self, group_id: str, user_id: str, limit: Optional[int] = None) -> List[ConversationMessage]:
        """获取用户的对话上下文"""
        conn = await get_db()

        window_limit = limit or config_manager.context_window

        cursor = await conn.execute(
            """
            SELECT id, group_id, user_id, role, content, timestamp
            FROM conversations
            WHERE group_id = ? AND user_id = ?
            ORDER BY timestamp ASC
            LIMIT ?
            """,
            (group_id, user_id, window_limit)
        )

        rows = await cursor.fetchall()

        messages = []
        for row in rows:
            messages.append(ConversationMessage(
                id=row[0],
                group_id=row[1],
                user_id=row[2],
                role=row[3],
                content=row[4],
                timestamp=row[5]
            ))

        return messages

    async def get_group_context(self, group_id: str, limit: int = settings.context.group_context_limit) -> List[ConversationMessage]:
        """获取群聊的所有对话上下文（用于查看）"""
        conn = await get_db()

        cursor = await conn.execute(
            """
            SELECT id, group_id, user_id, role, content, timestamp
            FROM conversations
            WHERE group_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (group_id, limit)
        )

        rows = await cursor.fetchall()

        messages = []
        for row in rows:
            messages.append(ConversationMessage(
                id=row[0],
                group_id=row[1],
                user_id=row[2],
                role=row[3],
                content=row[4],
                timestamp=row[5]
            ))

        # 反转顺序，让最新的在后面（便于显示）
        messages.reverse()
        return messages

    async def clear_context(self, group_id: str, user_id: Optional[str] = None):
        """清除对话上下文"""
        conn = await get_db()

        if user_id:
            # 清除指定用户的上下文
            await conn.execute(
                "DELETE FROM conversations WHERE group_id = ? AND user_id = ?",
                (group_id, user_id)
            )
            logger.info(f"已清除用户 {user_id} 在群 {group_id} 的上下文")
        else:
            # 清除整个群的上下文
            await conn.execute(
                "DELETE FROM conversations WHERE group_id = ?",
                (group_id,)
            )
            logger.info(f"已清除群 {group_id} 的所有上下文")

        await conn.commit()

    async def get_global_context(
        self,
        group_id: str,
        user_id: str,
        limit: Optional[int] = None
    ) -> GlobalContext:
        """
        获取全局上下文，结合当前对话和长期记忆

        Args:
            group_id: 群聊ID
            user_id: 用户ID
            limit: 当前对话消息数量限制

        Returns:
            GlobalContext对象
        """
        # 1. 获取当前对话上下文（复用现有逻辑）
        current_messages = await self.get_context(group_id, user_id, limit)

        # 2. 获取用户档案
        user_profile = await memory_provider.get_user_profile(user_id)

        # 3. 检索相关记忆
        relevant_memories = []
        if current_messages:
            # 找到最新的用户消息
            latest_user_message = None
            for msg in reversed(current_messages):
                if msg.role == "user":
                    latest_user_message = msg
                    break

            if latest_user_message:
                recent_content = latest_user_message.content if latest_user_message.content else ""
                logger.info(f"记忆召回查询文本: {recent_content[:100]}...")
            else:
                recent_msg = current_messages[-1]
                recent_content = recent_msg.content if recent_msg and recent_msg.content else ""

            try:
                # 构建上下文传给记忆系统
                recent_history = []
                for msg in current_messages[-10:]:
                    recent_history.append({
                        "role": msg.role,
                        "content": msg.content,
                    })
                recall_context = {
                    "recent_history": recent_history,
                    "ai_state": await memory_provider.get_ai_state(),
                    "current_time": datetime.now().isoformat(),
                }

                relevant_memories = await memory_provider.retrieve_relevant(
                    query=recent_content,
                    user_id=user_id,
                    group_id=group_id,
                    limit=settings.context.memory_recall_limit,
                    context=recall_context,
                )

                for mem in relevant_memories:
                    await memory_provider.update_access_stats(mem.memory.id)

            except Exception as e:
                logger.warning(f"记忆检索失败: {e}")

        # 4. 格式化为LLM可用上下文
        formatted_context = self._format_global_context(
            user_profile=user_profile,
            memories=relevant_memories,
            current_messages=current_messages
        )

        return GlobalContext(
            current_messages=current_messages,
            user_profile=user_profile,
            relevant_memories=relevant_memories,
            formatted_context=formatted_context
        )

    def _format_global_context(
        self,
        user_profile: Optional[UserProfile],
        memories: List,
        current_messages: List[ConversationMessage]
    ) -> str:
        """
        格式化全局上下文为LLM可用格式

        格式示例：
        ```
        用户信息: 姓名: 小明, 职业: 程序员, 兴趣: 编程, 游戏
        相关记忆:
        - 基本信息: 喜欢吃辣
        - 偏好: 不喜欢早起
        --- 以上是关于该用户的长期记忆 ---
        用户: 你好
        AI: 你好！有什么我可以帮你的吗？
        ```
        """
        context_parts = []

        # 1. 用户档案
        if user_profile:
            profile_info = []
            if user_profile.real_name:
                profile_info.append(f"姓名: {user_profile.real_name}")
            if user_profile.nickname:
                profile_info.append(f"昵称: {user_profile.nickname}")
            if user_profile.relationship and user_profile.relationship != "stranger":
                relationship_labels = {
                    "acquaintance": "熟人",
                    "friend": "朋友",
                    "close_friend": "密友",
                    "family": "家人"
                }
                profile_info.append(f"关系: {relationship_labels.get(user_profile.relationship, user_profile.relationship)}")
            if user_profile.location:
                profile_info.append(f"位置: {user_profile.location}")
            if user_profile.occupation:
                profile_info.append(f"职业: {user_profile.occupation}")
            if user_profile.interests:
                profile_info.append(f"兴趣: {', '.join(user_profile.interests)}")

            if profile_info:
                context_parts.append(f"用户信息: {', '.join(profile_info)}")

        # 2. 相关记忆
        if memories:
            memory_parts = []
            type_labels = {
                "basic_info": "基本信息",
                "preference": "偏好",
                "event": "事件",
                "conversation_summary": "摘要"
            }

            for mem in memories:
                type_label = type_labels.get(mem.memory.memory_type, mem.memory.memory_type)
                title = f" [{mem.memory.title}]" if mem.memory.title else ""
                memory_parts.append(f"- {type_label}{title}: {mem.memory.content}")

            if memory_parts:
                context_parts.append("相关记忆:\n" + "\n".join(memory_parts))

        # 3. 分隔线
        if context_parts:
            context_parts.append("--- 以上是关于该用户的长期记忆 ---")

        # 4. 当前对话
        for msg in current_messages:
            role = "用户" if msg.role == "user" else "AI"
            context_parts.append(f"{role}: {msg.content}")

        return "\n".join(context_parts)

    def format_for_llm(self, messages: List[ConversationMessage]) -> List[Dict]:
        """将消息格式化为大模型API格式"""
        formatted = []
        for msg in messages:
            formatted.append({
                "role": msg.role,
                "content": msg.content
            })
        return formatted

    # ==================== 群聊级别上下文管理 ====================

    async def add_group_message(
        self,
        group_id: str,
        user_id: str,
        role: str,
        content: str,
        sender_nickname: Optional[str] = None,
        mentions: Optional[List[Dict]] = None,
        is_directed_at_bot: bool = False
    ):
        """
        添加群聊消息到上下文（包含@信息）

        Args:
            group_id: 群聊ID
            user_id: 发送者用户ID
            role: user/assistant
            content: 消息内容
            sender_nickname: 发送者昵称
            mentions: @信息列表 [{"qq": "123", "name": "张三"}]
            is_directed_at_bot: 是否@机器人
        """
        conn = await get_db()

        # 确保用户存在（首次见才查 DB，后续跳过）
        if user_id not in self._known_users:
            cursor = await conn.execute(
                "SELECT user_id FROM users WHERE user_id = ?",
                (user_id,)
            )
            if not await cursor.fetchone():
                await conn.execute(
                    """
                    INSERT INTO users (user_id, nickname, user_type, message_count)
                    VALUES (?, ?, 'group_member', 1)
                    """,
                    (user_id, sender_nickname or user_id)
                )
                logger.info(f"自动创建用户记录: user_id={user_id}, nickname={sender_nickname}")
            self._known_users.add(user_id)

        # 确保群聊存在（首次见才查 DB）
        if group_id not in self._known_groups:
            cursor = await conn.execute(
                "SELECT group_id FROM groups WHERE group_id = ?",
                (group_id,)
            )
            if not await cursor.fetchone():
                await conn.execute(
                    """
                    INSERT INTO groups (group_id, enabled, auto_reply_enabled)
                    VALUES (?, 1, 1)
                    """,
                    (group_id,)
                )
                logger.info(f"自动创建群聊记录: group_id={group_id}")
            self._known_groups.add(group_id)

        # content 已经包含 @名字（extract_plain_text 已处理），无需重复拼接
        full_content = content

        # 序列化@信息
        mentions_json = json.dumps(mentions) if mentions else None

        logger.info(f"准备存储群聊消息: mentions={mentions}, mentions_json前100字符={mentions_json[:100] if mentions_json else 'None'}")
        logger.info(f"完整消息内容: {full_content[:100]}...")

        await conn.execute(
            """
            INSERT INTO conversations
            (group_id, user_id, role, content, sender_nickname, mentions, is_directed_at_bot)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (group_id, user_id, role, full_content, sender_nickname, mentions_json, 1 if is_directed_at_bot else 0)
        )
        await conn.commit()

        logger.info(f"已添加群聊消息: group={group_id}, user={user_id}, role={role}, nickname={sender_nickname}, mentions_count={len(mentions) if mentions else 0}")

    async def get_group_context(
        self,
        group_id: str,
        limit: int = settings.context.group_context_limit,
        time_window_minutes: int = settings.context.group_context_time_window
    ) -> List[GroupMessage]:
        """
        获取群聊的完整对话上下文（所有用户的发言）

        Args:
            group_id: 群聊ID
            limit: 最大消息数量（默认50条）
            time_window_minutes: 时间窗口（分钟），只返回最近N分钟内的消息

        Returns:
            群聊消息列表
        """
        conn = await get_db()

        # 先尝试获取时间窗口内的消息
        time_threshold = datetime.now() - timedelta(minutes=time_window_minutes)

        cursor = await conn.execute(
            """
            SELECT id, group_id, user_id, role, content, timestamp,
                   sender_nickname, mentions, is_directed_at_bot
            FROM conversations
            WHERE group_id = ? AND timestamp >= ?
            ORDER BY timestamp ASC
            LIMIT ?
            """,
            (group_id, time_threshold.isoformat(), limit)
        )

        rows = await cursor.fetchall()

        # 降级：如果时间窗口内没有消息，获取最近的50条（不限制时间）
        if not rows:
            logger.warning(f"群聊 {group_id} 最近{time_window_minutes}分钟内没有消息，使用最近50条降级")
            cursor = await conn.execute(
                """
                SELECT id, group_id, user_id, role, content, timestamp,
                       sender_nickname, mentions, is_directed_at_bot
                FROM conversations
                WHERE group_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (group_id, limit)
            )
            rows = await cursor.fetchall()
            # 反转顺序为时间正序
            rows = list(reversed(rows))

        messages = []
        for row in rows:
            # 解析@信息
            mentions_data = []
            if row[7]:  # mentions字段
                try:
                    mentions_json = json.loads(row[7])
                    # 兼容两种格式：直接列表 [{"qq": "123", "name": "张三"}] 或 嵌套字典 {"mentions": [...]}
                    if isinstance(mentions_json, list):
                        # 直接是列表格式
                        mentions_data = [MentionInfo(**m) for m in mentions_json]
                    elif isinstance(mentions_json, dict) and 'mentions' in mentions_json:
                        # 嵌套字典格式
                        mentions_data = [MentionInfo(**m) for m in mentions_json['mentions']]
                    logger.info(f"成功解析@信息: {len(mentions_data)}条")
                except Exception as e:
                    logger.warning(f"解析@信息失败: {e}, 原始数据: {row[7][:100] if row[7] else 'None'}")

            messages.append(GroupMessage(
                id=row[0],
                group_id=row[1],
                user_id=row[2],
                role=row[3],
                content=row[4] or "",  # 确保 content 永远不是 None
                timestamp=row[5],
                sender_nickname=row[6] or "未知",
                mentions=mentions_data,
                is_directed_at_bot=bool(row[8])
            ))

        logger.info(f"获取到 {len(messages)} 条群聊上下文（最近{time_window_minutes}分钟，最多{limit}条）")
        return messages

    def format_group_context_for_llm(
        self,
        messages: List[GroupMessage],
        include_mentions: bool = True
    ) -> str:
        """
        格式化群聊上下文供LLM使用

        格式示例：
        [14:30] 张三: 大家好
        [14:31] 李四(@机器人): 你好，机器人
        [14:32] 机器人: 你好李四！

        时间较旧的消息会显示相对时间标注，如：
        [14:30 (23分钟前)] 张三: 大家好
        [昨天 14:30] 张三: 大家好

        Args:
            messages: 群聊消息列表
            include_mentions: 是否包含@信息

        Returns:
            格式化后的文本
        """
        from backend.services.core.time_utils import format_relative_time_for_display

        formatted_lines = []

        # 检测是否需要添加降级提示（第一条消息超过30分钟）
        if messages:
            try:
                first_time = datetime.fromisoformat(messages[0].timestamp)
                if (datetime.now() - first_time).total_seconds() > 1800:
                    formatted_lines.append("[注意: 以下对话来自较早时间]")
            except Exception:
                pass

        # 注意：消息内容中可能包含 [语音消息转写] 或 [图片内容] 标记，
        # 这些标记由消息来源方（如 DiscordSource）在构造消息时添加，
        # context_manager 直接回显，不做额外处理。
        for msg in messages:
            # 使用相对时间格式化
            time_str = format_relative_time_for_display(msg.timestamp)

            # 格式化发送者信息
            if msg.role == "assistant":
                sender = "机器人"
            else:
                sender = msg.sender_nickname or f"用户{msg.user_id[-4:]}"

            # 标记@机器人的消息（content中已包含@文本，这里只额外标记机器人）
            bot_tag = " @机器人" if msg.is_directed_at_bot else ""

            formatted_lines.append(f"[{time_str}] {sender}{bot_tag}: {msg.content}")

        return "\n".join(formatted_lines)


# 全局上下文管理器实例
context_manager = ContextManager()
