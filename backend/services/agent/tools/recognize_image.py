"""识图工具 - 包装vision_service.recognize_image."""

import logging
from typing import Dict, Any

from .base import Tool, ToolArgument
from backend.services.vision_service import vision_service


logger = logging.getLogger(__name__)


class RecognizeImageTool(Tool):
    """识图工具

    包装vision_service.recognize_image
    """

    @property
    def name(self) -> str:
        return "recognize_image"

    @property
    def description(self) -> str:
        return "识别图片内容(表情包或普通图片)"

    @property
    def arguments(self) -> list:
        return [
            ToolArgument(
                name="image_url",
                type="string",
                description="图片URL",
                required=True
            ),
            ToolArgument(
                name="is_meme",
                type="boolean",
                description="是否为表情包",
                required=False,
                default=False
            ),
            ToolArgument(
                name="context",
                type="string",
                description="上下文提示",
                required=False,
                default="群聊图片"
            )
        ]

    async def execute(self, **kwargs) -> Dict[str, Any]:
        """
        执行图片识别

        直接复用vision_service.recognize_image (第82-210行)
        """
        image_url = kwargs.get("image_url")
        is_meme = kwargs.get("is_meme", False)
        context = kwargs.get("context", "群聊图片")

        if not image_url:
            return {"success": False, "error": "缺少图片URL"}

        try:
            description = await vision_service.recognize_image(
                image_url=image_url,
                is_meme=is_meme,
                context=context
            )

            return {
                "success": True,
                "description": description,
                "is_meme": is_meme
            }

        except Exception as e:
            logger.error(f"图片识别失败: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
