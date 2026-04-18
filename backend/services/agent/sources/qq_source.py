"""QQ消息源 - 接收NapCat消息并转换为统一格式."""

import logging
from typing import Optional
from datetime import datetime

from ..message import AgentMessage
from backend.api.napcat import napcat_client
from backend.services.vision_service import vision_service


logger = logging.getLogger(__name__)


class QQSource:
    """QQ消息源

    接收NapCat消息并转换为AgentMessage格式
    自动处理图片识别和@信息提取
    """

    def __init__(self):
        self.vision_service = vision_service

    async def receive_message(self, message_data: dict) -> Optional[AgentMessage]:
        """
        接收NapCat原始消息并转换为AgentMessage

        支持群聊和私聊两种消息类型。

        Args:
            message_data: NapCat原始消息

        Returns:
            AgentMessage或None
        """
        try:
            # 检测消息类型
            message_type = message_data.get("message_type", "group")
            is_private = message_type == "private"

            user_id = str(message_data.get("user_id"))
            raw_message = message_data.get("raw_message", "")
            message_content = message_data.get("message", raw_message)

            # 获取机器人ID
            self_id = message_data.get("self_id")

            # 根据消息类型设置 group_id 和 context
            if is_private:
                group_id = f"private_{user_id}"
            else:
                group_id = str(message_data.get("group_id"))

            # 提取发送者昵称
            sender = message_data.get("sender", {})
            sender_nickname = napcat_client.extract_user_nickname(sender)

            # 检查是否@机器人（私聊默认视为 @）
            if is_private:
                is_mentioned = True
                mentions = []
            else:
                is_mentioned = napcat_client.is_mentioned(message_content, self_id)
                mentions = napcat_client.extract_all_mentions(message_content)

            # 检测图片
            image_url = napcat_client.extract_image_url(message_content)

            # 提取纯文本内容
            text_content = napcat_client.extract_plain_text(message_content)

            # 如果既没有图片也没有文本,跳过
            if not image_url and not text_content.strip():
                logger.info("消息为空,跳过")
                return None

            # 图片识别
            image_description = None
            image_type = "无图片"
            has_image = False

            if image_url:
                has_image = True
                logger.info(f"检测到图片: {image_url}")

                is_meme = self._is_meme_image(message_content)
                image_type = "表情包" if is_meme else "普通图片"

                try:
                    image_description = await self.vision_service.recognize_image(
                        image_url=image_url,
                        is_meme=is_meme,
                        context=image_type
                    )
                    logger.info(f"图片识别成功: {image_description[:50] if image_description else 'None'}...")
                except Exception as e:
                    logger.error(f"图片识别失败: {e}")

            # 构建AgentMessage
            message = AgentMessage(
                source="qq",
                group_id=group_id,
                user_id=user_id,
                sender_nickname=sender_nickname,
                content=text_content,
                raw_message=raw_message,
                is_mentioned=is_mentioned,
                mentions=mentions,
                has_image=has_image,
                image_url=image_url,
                image_type=image_type,
                image_description=image_description,
                priority=10 if is_mentioned else 0,
                is_private=is_private,
                timestamp=datetime.now()
            )

            chat_type = "私聊" if is_private else f"群聊group={group_id}"
            logger.info(f"QQ源消息转换完成: {chat_type}, user={user_id}, mentioned={is_mentioned}")
            return message

        except Exception as e:
            logger.error(f"QQ消息转换失败: {e}", exc_info=True)
            return None

    def _is_meme_image(self, message_content: str | list) -> bool:
        """
        判断是否为表情包图片

        直接复用message_handler.py 第338-357行

        Args:
            message_content: 消息内容

        Returns:
            True表示表情包, False表示普通图片
        """
        import re

        if isinstance(message_content, str):
            # 检查summary字段
            if re.search(r'\[CQ:image,[^\]]*(表情|贴图|sticker|梗|meme)', message_content, re.IGNORECASE):
                return True
        elif isinstance(message_content, list):
            for segment in message_content:
                if isinstance(segment, dict) and segment.get("type") == "image":
                    data = segment.get("data", {})
                    summary = data.get("summary", "")
                    if re.search(r'(表情|贴图|sticker|梗|meme)', summary, re.IGNORECASE):
                        return True
        return False
