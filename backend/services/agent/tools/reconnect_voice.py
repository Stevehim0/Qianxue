"""连接语音频道工具 -- AI 主动加入 Discord 语音频道."""

import asyncio
import logging
from typing import Dict

from .base import Tool

logger = logging.getLogger(__name__)


class ReconnectVoiceTool(Tool):
    """AI 通过此工具加入或重连 Discord 语音频道。"""

    @property
    def name(self) -> str:
        return "connect_voice"

    @property
    def description(self) -> str:
        return (
            "加入 Discord 语音频道，开始收听和说话。无需任何参数。"
            "当需要与对方语音对话时调用（如对方在语音频道等你）。"
        )

    @property
    def arguments(self) -> list:
        return []

    async def execute(self, **kwargs) -> Dict:
        from backend.services.agent.sources.discord_source import discord_source
        from backend.services.voice_player import voice_player
        from backend.config.loader import settings

        if discord_source is None:
            return {"success": False, "message": "Discord 模块未初始化"}

        # 如果 Bot 本身没连，先连 Discord
        if not discord_source.is_connected():
            try:
                await discord_source.connect()
                for _ in range(15):
                    if discord_source.is_connected():
                        break
                    await asyncio.sleep(1)
                if not discord_source.is_connected():
                    return {"success": False, "message": "Discord 连接失败，无法加入语音频道。"}
            except Exception as e:
                return {"success": False, "message": f"Discord 连接失败: {e}"}

        channel_id = kwargs.get("channel_id") or settings.discord.voice_channel_id
        if not channel_id:
            return {"success": False, "message": "请提供 channel_id 参数（语音频道 ID）"}

        # 已在同一频道则跳过
        if voice_player.is_connected():
            current = None
            if voice_player._voice_client and hasattr(voice_player._voice_client, 'channel') and voice_player._voice_client.channel:
                current = str(voice_player._voice_client.channel.id)
            if current == str(channel_id):
                return {"success": True, "message": f"已在语音频道 {channel_id} 中。"}

        # 先断开旧连接
        if voice_player.is_connected():
            try:
                await voice_player.disconnect()
            except Exception:
                pass
            await asyncio.sleep(1)

        # 连接新频道
        try:
            success = await voice_player.connect(str(channel_id))
            if success:
                return {"success": True, "message": f"已加入语音频道 {channel_id}，可以听到对方说话了。"}
            else:
                return {"success": False, "message": "加入语音频道失败，可能是网络问题。"}
        except Exception as e:
            logger.error(f"语音连接失败: {e}")
            return {"success": False, "message": f"语音连接失败: {e}"}
