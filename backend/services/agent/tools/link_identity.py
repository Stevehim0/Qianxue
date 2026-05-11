"""统一身份关联工具 — 让千雪自己建立跨渠道身份映射.

此工具是 fire-and-forget，不阻塞对话流程。
千雪在对话中发现某人是同一个人，或对方主动说了自己的其他平台身份时调用。
"""

import asyncio
import logging
from typing import Dict, Any

from .base import Tool, ToolArgument

logger = logging.getLogger(__name__)


class LinkIdentityTool(Tool):
    """统一身份关联工具."""

    @property
    def name(self) -> str:
        return "link_identity"

    @property
    def description(self) -> str:
        return (
            "把不同平台上的用户身份关联为同一个人。"
            "当你发现 QQ 群里的某人和 Discord 上的某人是同一个人，"
            "或者对方主动告诉你'我的 QQ 号是 xxx'之类的话时，使用此工具记录关联。"
            "identity_name 是你认识TA的名字，platform 是来源平台（qq/discord/computer），"
            "platform_id 是该平台上的用户 ID，platform_nickname 是该平台上的昵称。"
        )

    @property
    def arguments(self) -> list:
        return [
            ToolArgument(
                name="identity_name",
                type="string",
                description="你认识的这个人叫什么名字（统一身份名）",
                required=True,
            ),
            ToolArgument(
                name="platform",
                type="string",
                description="平台: qq / discord / computer",
                required=True,
            ),
            ToolArgument(
                name="platform_id",
                type="string",
                description="该平台上的用户 ID（自动注入，无需手动填写）",
                required=True,
            ),
            ToolArgument(
                name="platform_nickname",
                type="string",
                description="该平台上的昵称",
                required=False,
            ),
            ToolArgument(
                name="reason",
                type="string",
                description="为什么建立这个关联（如：对方说自己的QQ号是xxx）",
                required=False,
            ),
        ]

    async def execute(self, **kwargs) -> Dict[str, Any]:
        """执行身份关联（fire-and-forget，不阻塞对话）."""
        identity_name = kwargs.get("identity_name", "")
        platform = kwargs.get("platform", "")
        platform_id = kwargs.get("platform_id", "")
        platform_nickname = kwargs.get("platform_nickname", "")
        reason = kwargs.get("reason", "")

        if not identity_name or not platform or not platform_id:
            return {"success": False, "error": "缺少必要参数"}

        # fire-and-forget: 后台执行，立即返回
        asyncio.create_task(self._do_link(
            identity_name, platform, platform_id, platform_nickname, reason
        ))

        return {"success": True, "message": f"已记录: {platform} 上的 {platform_nickname or platform_id} 是 {identity_name}"}

    async def _do_link(self, identity_name, platform, platform_id, platform_nickname, reason):
        """后台执行身份关联."""
        try:
            from backend.services.identity_service import identity_service
            await identity_service.link_identity(
                identity_name=identity_name,
                platform=platform,
                platform_id=platform_id,
                platform_nickname=platform_nickname,
                reason=reason,
            )
        except Exception as e:
            logger.error(f"身份关联后台任务失败: {e}")
