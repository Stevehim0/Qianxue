"""Discord 消息源 -- 将 Discord 消息转换为 AgentMessage 格式.

接收 Discord 文字频道和私聊的文字消息及语音附件消息，
转为 AgentMessage 进入对话流程。

语音附件自动检测、下载并通过 VoiceService.transcribe() 转写。

Bot 实例不可重用（RISK-02）：每次 connect() 创建新 Bot，disconnect() 销毁。
"""

import asyncio
import io
import logging
from typing import Optional, Callable, Awaitable, Any

try:
    import discord
    from discord.ext import commands
    _DISCORD_AVAILABLE = True
except ImportError:
    discord = None  # type: ignore[assignment]
    commands = None  # type: ignore[assignment]
    _DISCORD_AVAILABLE = False

from backend.config.loader import settings
from backend.services.agent.message import AgentMessage
from backend.services.voice_service import voice_service, VoiceError
from backend.services.voice_player import voice_player

logger = logging.getLogger(__name__)

# Discord 单条消息最大字符数
_DISCORD_MAX_LENGTH = 2000


class DiscordSource:
    """Discord 消息源 -- 将 Discord 消息转换为 AgentMessage.

    职责：
    - 连接/断开 Discord Bot
    - 将 Discord Message 转换为 AgentMessage（含语音转写）
    - 发送消息到 Discord 频道或私聊（含 2000 字符限制分割）
    - 发送语音文件附件
    """

    def __init__(self):
        cfg = settings.discord
        self._token = cfg.token
        self._proxy = cfg.proxy or None
        self._channel_ids = set(cfg.channels)
        self._dm_enabled = cfg.dm_enabled

        self._intents = None
        self._bot: Any = None
        self._task: Optional[asyncio.Task] = None
        self._message_handler: Optional[Callable[[AgentMessage], Awaitable[None]]] = None

    # ------------------------------------------------------------------
    # 消息处理器设置
    # ------------------------------------------------------------------

    def set_message_handler(self, handler: Callable[[AgentMessage], Awaitable[None]]):
        """设置消息处理器（Brain 的入口方法）。"""
        self._message_handler = handler

    # ------------------------------------------------------------------
    # Bot 连接管理
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """连接到 Discord。

        每次连接创建新的 Bot 实例（RISK-02: 不可重用）。
        幂等：已连接时直接返回。
        """
        if not _DISCORD_AVAILABLE:
            raise RuntimeError("discord.py 未安装。请运行: pip install discord.py")

        if self._bot and not self._bot.is_closed():
            logger.info("Discord Bot 已连接，跳过重复连接")
            return

        if not self._token:
            raise ValueError("Discord Bot token 未配置，请在 discord.yaml 或环境变量 QIANXUE_DISCORD__TOKEN 中设置")

        # Gateway Intents (延迟到 connect 时初始化)
        self._intents = discord.Intents.default()
        self._intents.message_content = True
        self._intents.dm_messages = True

        self._bot = commands.Bot(intents=self._intents, command_prefix="!", proxy=self._proxy)
        self._register_handlers()
        self._task = asyncio.create_task(self._bot.start(self._token))
        logger.info("Discord Bot 正在连接...")

    async def disconnect(self) -> None:
        """断开 Discord 连接。"""
        # 先断开语音频道（per 20-02: 语音频道同步断开）
        if voice_player.is_connected():
            await voice_player.disconnect()

        if self._bot and not self._bot.is_closed():
            await self._bot.close()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._bot = None
        self._task = None
        logger.info("Discord Bot 已断开")

    def is_connected(self) -> bool:
        """检查 Bot 是否已连接且就绪。"""
        return self._bot is not None and self._bot.is_ready()

    # ------------------------------------------------------------------
    # Bot 事件处理器注册
    # ------------------------------------------------------------------

    def _register_handlers(self):
        """在当前 Bot 实例上注册事件处理器。"""
        @self._bot.event
        async def on_message(message):
            await self._handle_message(message)

        @self._bot.event
        async def on_ready():
            logger.info(f"Discord Bot 已就绪: {self._bot.user}")
            # 注入 Bot 实例到 VoicePlayer（语音工具需要 Bot 实例才能连接频道）
            voice_player.set_bot(self._bot)

        @self._bot.event
        async def on_disconnect():
            logger.warning("Discord Bot WebSocket 断开连接")

        @self._bot.event
        async def on_voice_state_update(member, before, after):
            """监听语音状态变化 — 检测 bot 被踢出语音频道后自动重连。"""
            # 只关心 bot 自身的状态变化
            if self._bot.user is None or member.id != self._bot.user.id:
                return
            # bot 从语音频道断开，且非主动断开
            if before.channel is not None and after.channel is None and not voice_player._intentional_disconnect:
                channel_id = before.channel.id
                logger.warning(f"Bot 被移出语音频道 {channel_id}，3 秒后尝试重连...")
                voice_player._connected = False
                voice_player._voice_client = None
                await asyncio.sleep(3)
                if not self._bot.is_closed():
                    try:
                        success = await voice_player.connect(str(channel_id))
                        if success:
                            logger.info(f"语音频道 {channel_id} 重连成功")
                        else:
                            logger.warning(f"语音频道 {channel_id} 重连失败")
                    except Exception as e:
                        logger.warning(f"语音频道重连异常: {e}")

        @self._bot.event
        async def on_error(event_name, *args, **kwargs):
            logger.error(f"Discord Bot 事件错误: {event_name}")

    # ------------------------------------------------------------------
    # 消息处理
    # ------------------------------------------------------------------

    async def _handle_message(self, message):
        """处理收到的 Discord 消息。"""
        # 忽略自己的消息
        if message.author == self._bot.user:
            return

        # 过滤：只处理配置的频道和私聊
        if not self._should_process(message):
            return

        # 转换为 AgentMessage
        agent_msg = await self._convert_message(message)
        if agent_msg and self._message_handler:
            await self._message_handler(agent_msg)

    def _should_process(self, message) -> bool:
        """判断是否应处理此消息。

        DMs 始终处理（如果 dm_enabled），频道只处理配置中的频道。
        """
        # 私聊消息
        if message.guild is None:
            return self._dm_enabled
        # 只处理配置中指定的频道
        return message.channel.id in self._channel_ids

    async def _convert_message(self, message) -> Optional[AgentMessage]:
        """将 Discord Message 转换为 AgentMessage。

        字段映射遵循 RESEARCH R-03 映射表。
        """
        is_dm = message.guild is None
        is_mentioned = (self._bot.user in message.mentions) if self._bot.user else False

        # 将原始 <@user_id> 替换为可读的 @名字
        content = message.content
        for mention_user in message.mentions:
            content = content.replace(f"<@{mention_user.id}>", f"@{mention_user.display_name}")
            content = content.replace(f"<@!{mention_user.id}>", f"@{mention_user.display_name}")

        agent_msg = AgentMessage(
            source="discord",
            group_id=f"dm_{message.author.id}" if is_dm else str(message.channel.id),
            user_id=str(message.author.id),
            sender_nickname=message.author.display_name,
            content=content,
            raw_message=f"discord:{message.id}",
            is_mentioned=is_mentioned,
            mentions=[{"id": str(m.id), "name": m.display_name} for m in message.mentions],
            is_private=is_dm,
            timestamp=message.created_at,
            priority=10 if is_mentioned else 0,
        )

        # 检测并处理语音附件（D-07, D-08）
        voice_attachment = self._find_voice_attachment(message)
        if voice_attachment and settings.discord.voice.auto_transcribe:
            if voice_attachment.size <= settings.discord.voice.max_size:
                agent_msg.has_voice = True
                agent_msg.voice_url = voice_attachment.url
                transcription = await self._transcribe_voice(voice_attachment)
                if transcription:
                    agent_msg.voice_transcription = transcription
                    if agent_msg.content.strip():
                        agent_msg.content = f"{agent_msg.content}\n[语音消息转写] {transcription}"
                    else:
                        agent_msg.content = f"[语音消息转写] {transcription}"

        chat_type = "私聊" if is_dm else f"频道channel={message.channel.id}"
        logger.info(f"Discord 消息转换完成: {chat_type}, user={message.author.id}, mentioned={is_mentioned}")
        return agent_msg

    # ------------------------------------------------------------------
    # 语音附件处理
    # ------------------------------------------------------------------

    def _find_voice_attachment(self, message) -> Optional[Any]:
        """检测消息中的语音附件。

        识别规则：
        - .ogg 文件（Discord 语音消息格式）
        - content_type 以 audio/ 开头的附件
        """
        for attachment in message.attachments:
            # Discord 语音消息：.ogg 格式
            if attachment.filename.endswith('.ogg'):
                return attachment
            # 备用检测：content_type 以 audio/ 开头
            if attachment.content_type and attachment.content_type.startswith('audio/'):
                return attachment
        return None

    async def _transcribe_voice(self, attachment) -> Optional[str]:
        """下载语音附件并通过 VoiceService 转写。

        下载到 BytesIO，传入 voice_service.transcribe(bytes)。
        转写失败时记录警告并返回 None（不阻塞消息处理）。
        """
        try:
            buffer = io.BytesIO()
            await attachment.save(buffer)
            audio_bytes = buffer.getvalue()
            return await voice_service.transcribe(audio_bytes)
        except VoiceError as e:
            logger.warning(f"Discord 语音附件转写失败: {e}")
            return None
        except Exception as e:
            logger.error(f"Discord 语音附件处理异常: {e}", exc_info=True)
            return None

    # ------------------------------------------------------------------
    # 消息发送
    # ------------------------------------------------------------------

    async def send_message(self, channel_id: str, text: str, is_private: bool = False) -> bool:
        """发送消息到 Discord 频道或私聊。

        支持 Discord 2000 字符限制的自动分割（按换行符断开）。

        Args:
            channel_id: 频道 ID 或 dm_{user_id} 格式的私聊 ID
            text: 消息文本
            is_private: 是否为私聊

        Returns:
            True 表示发送成功
        """
        if not self._bot or not self._bot.is_ready():
            logger.warning("Discord Bot 未连接，无法发送消息")
            return False

        try:
            # 按 Discord 2000 字符限制分割
            chunks = self._split_message(text)
            for chunk in chunks:
                if is_private:
                    # 从 dm_{user_id} 格式中提取 user_id
                    user_id_str = channel_id
                    if channel_id.startswith("dm_"):
                        user_id_str = channel_id[3:]
                    user_id = int(user_id_str)
                    # 使用 fetch_user（不依赖缓存，解决 RISK-04）
                    user = await self._bot.fetch_user(user_id)
                    if user:
                        await user.send(chunk)
                    else:
                        logger.error(f"Discord 用户不存在: {user_id}")
                        return False
                else:
                    channel = self._bot.get_channel(int(channel_id))
                    if channel:
                        await channel.send(chunk)
                    else:
                        logger.error(f"Discord 频道不存在: {channel_id}")
                        return False
            return True
        except Exception as e:
            logger.error(f"Discord 发送消息失败: {e}", exc_info=True)
            return False

    async def send_voice_file(
        self,
        channel_id: str,
        audio_bytes: bytes,
        filename: str = "voice_reply.mp3",
        is_private: bool = False,
    ) -> bool:
        """发送语音文件到 Discord 频道或私聊。

        用于 Phase 18 send_voice 工具的 Discord 集成。

        Args:
            channel_id: 频道 ID 或 dm_{user_id} 格式
            audio_bytes: 音频数据
            filename: 文件名
            is_private: 是否为私聊

        Returns:
            True 表示发送成功
        """
        if not self._bot or not self._bot.is_ready():
            logger.warning("Discord Bot 未连接，无法发送语音文件")
            return False

        try:
            file = discord.File(io.BytesIO(audio_bytes), filename=filename)  # type: ignore[union-attr]

            if is_private:
                user_id_str = channel_id
                if channel_id.startswith("dm_"):
                    user_id_str = channel_id[3:]
                user_id = int(user_id_str)
                user = await self._bot.fetch_user(user_id)
                if user:
                    await user.send(file=file)
                else:
                    logger.error(f"Discord 用户不存在: {user_id}")
                    return False
            else:
                channel = self._bot.get_channel(int(channel_id))
                if channel:
                    await channel.send(file=file)
                else:
                    logger.error(f"Discord 频道不存在: {channel_id}")
                    return False
            return True
        except Exception as e:
            logger.error(f"Discord 发送语音文件失败: {e}", exc_info=True)
            return False

    # ------------------------------------------------------------------
    # 内部工具方法
    # ------------------------------------------------------------------

    @staticmethod
    def _split_message(text: str, max_length: int = _DISCORD_MAX_LENGTH) -> list[str]:
        """将长消息按换行符分割为 Discord 兼容的片段。

        优先在换行符处断开，避免截断句子。
        """
        if len(text) <= max_length:
            return [text]

        chunks = []
        while text:
            if len(text) <= max_length:
                chunks.append(text)
                break
            # 找最后一个换行符作为分割点
            split_at = text.rfind('\n', 0, max_length)
            if split_at == -1:
                # 没有换行符，硬切
                split_at = max_length
            chunks.append(text[:split_at])
            text = text[split_at:].lstrip('\n')

        return chunks


# 模块级单例（在 main.py 中初始化，Plan 02 负责）
discord_source: Optional[DiscordSource] = None
