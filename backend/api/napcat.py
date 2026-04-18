"""NapCat/OneBot客户端模块."""

import httpx
import logging
import asyncio
from typing import Optional, Callable, Dict, List
from backend.config import settings
from backend.database.models import NapCatMessage, MessageSegment


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class NapCatClient:
    """NapCat/OneBot客户端"""

    def __init__(self, http_url: Optional[str] = None):
        self.http_url = http_url  # NapCat HTTP API地址，如 http://localhost:3000
        self.client = httpx.AsyncClient(timeout=settings.napcat.timeout)
        self._message_callback: Optional[Callable] = None
        self._connected = False
        self.self_id: Optional[int] = None

    async def send_group_message(self, group_id: int, message: str) -> bool:
        """发送群消息"""
        if not self.http_url:
            logger.warning("未配置NapCat HTTP地址，无法发送消息")
            return False

        try:
            logger.info(f"正在发送消息到群 {group_id}...")
            logger.info(f"NapCat API地址: {self.http_url}/send_group_msg")

            response = await self.client.post(
                f"{self.http_url}/send_group_msg",
                json={
                    "group_id": group_id,
                    "message": message
                }
            )

            logger.info(f"NapCat响应状态码: {response.status_code}")

            response.raise_for_status()
            result = response.json()

            logger.info(f"NapCat响应内容: {result}")

            if result.get("status") == "ok":
                logger.info(f"已发送消息到群 {group_id}: {message[:50]}...")
                return True
            else:
                logger.error(f"发送消息失败: {result}")
                return False
        except Exception as e:
            logger.error(f"发送群消息异常: {e}")
            logger.error(f"请检查NapCat的HTTP API端口配置，默认端口可能是3000、3001或6099")
            return False

    async def send_private_message(self, user_id: int, message: str) -> bool:
        """发送私聊消息"""
        if not self.http_url:
            logger.warning("未配置NapCat HTTP地址，无法发送消息")
            return False

        try:
            response = await self.client.post(
                f"{self.http_url}/send_private_msg",
                json={
                    "user_id": user_id,
                    "message": message
                }
            )
            response.raise_for_status()
            result = response.json()

            if result.get("status") == "ok":
                logger.info(f"已发送私聊消息给 {user_id}: {message[:50]}...")
                return True
            else:
                logger.error(f"发送私聊消息失败: {result}")
                return False
        except Exception as e:
            logger.error(f"发送私聊消息异常: {e}")
            return False

    async def get_group_info(self, group_id: int) -> Optional[Dict]:
        """获取群信息"""
        if not self.http_url:
            return None

        try:
            response = await self.client.post(
                f"{self.http_url}/get_group_info",
                json={"group_id": group_id}
            )
            response.raise_for_status()
            result = response.json()
            if result.get("status") == "ok":
                return result.get("data")
            return None
        except Exception as e:
            logger.error(f"获取群信息失败: {e}")
            return None

    async def get_friend_list(self) -> Optional[List[Dict]]:
        """获取好友列表"""
        if not self.http_url:
            return None

        try:
            response = await self.client.post(
                f"{self.http_url}/get_friend_list"
            )
            response.raise_for_status()
            result = response.json()
            if result.get("status") == "ok":
                return result.get("data")
            return None
        except Exception as e:
            logger.error(f"获取好友列表失败: {e}")
            return None

    async def get_group_list(self) -> Optional[List[Dict]]:
        """获取群列表"""
        if not self.http_url:
            return None

        try:
            response = await self.client.post(
                f"{self.http_url}/get_group_list"
            )
            response.raise_for_status()
            result = response.json()
            if result.get("status") == "ok":
                return result.get("data")
            return None
        except Exception as e:
            logger.error(f"获取群列表失败: {e}")
            return None

    def parse_message(self, message_data: Dict) -> Optional[NapCatMessage]:
        """解析OneBot消息"""
        try:
            return NapCatMessage(**message_data)
        except Exception as e:
            logger.error(f"解析消息失败: {e}, 数据: {message_data}")
            return None

    def extract_text_content(self, message: List[MessageSegment] | str | list) -> str:
        """从消息中提取纯文本内容"""
        if isinstance(message, str):
            return message

        if isinstance(message, list):
            text_parts = []
            for segment in message:
                if isinstance(segment, dict):
                    if segment.get("type") == "text":
                        text_parts.append(segment.get("data", {}).get("text", ""))
                elif isinstance(segment, str):
                    text_parts.append(segment)
            return "".join(text_parts)

        return ""

    def extract_plain_text(self, message: List[MessageSegment] | str | list) -> str:
        """提取纯文本，去除CQ码"""
        if isinstance(message, str):
            # 移除CQ码
            import re
            return re.sub(r'\[CQ:.*?\]', '', message)

        if isinstance(message, list):
            text_parts = []
            for segment in message:
                if isinstance(segment, dict):
                    if segment.get("type") == "text":
                        text_parts.append(segment.get("data", {}).get("text", ""))
                elif isinstance(segment, str):
                    import re
                    text_parts.append(re.sub(r'\[CQ:.*?\]', '', segment))
            return "".join(text_parts)

        return ""

    def is_mentioned(self, message: List[MessageSegment] | str | list, self_id: int) -> bool:
        """检查消息中是否@机器人"""
        if isinstance(message, str):
            return f"[CQ:at,qq={self_id}]" in message

        if isinstance(message, list):
            for segment in message:
                if isinstance(segment, dict):
                    if segment.get("type") == "at":
                        qq = segment.get("data", {}).get("qq")
                        if qq and (qq == str(self_id) or qq == self_id):
                            return True

        return False

    def extract_all_mentions(self, message: List[MessageSegment] | str | list) -> List[Dict]:
        """
        提取消息中的所有@信息（谁@了谁）

        Args:
            message: 消息内容

        Returns:
            提取的@信息列表 [{"qq": "123", "name": "张三"}, ...]
        """
        from backend.database.models import MentionInfo
        mentions = []

        if isinstance(message, str):
            logger.info(f"extract_all_mentions: 输入是字符串类型: {message[:100]}...")
            import re

            # 方法1: 解析CQ码 [CQ:at,qq=123,name=张三]
            matches = re.findall(r'\[CQ:at,qq=(\d+),name=([^\]]+)\]', message)
            logger.info(f"方法1匹配结果: {len(matches)}条")
            for qq, name in matches:
                mentions.append({"qq": qq, "name": name})

            # 方法2: 解析CQ码 [CQ:at,qq=123]（无name字段）
            # 使用更简单的方法：先找到所有[CQ:at,qq=xxx]，然后排除有name字段的
            at_matches = re.findall(r'\[CQ:at,qq=(\d+)\]', message)
            logger.info(f"方法2匹配结果: {len(at_matches)}条")
            for qq in at_matches:
                # 检查是否已经在上面添加过（避免重复）
                if not any(m["qq"] == qq for m in mentions):
                    mentions.append({"qq": qq, "name": f"用户{qq[-4:]}"})

            logger.info(f"提取到的@信息: {mentions}")

        elif isinstance(message, list):
            logger.info(f"extract_all_mentions: 输入是列表类型，共{len(message)}个segment")
            for segment in message:
                if isinstance(segment, dict):
                    seg_type = segment.get("type")
                    logger.info(f"  segment type: {seg_type}")
                    if seg_type == "at":
                        data = segment.get("data", {})
                        qq = data.get("qq")
                        name = data.get("name")
                        logger.info(f"  发现@segment: qq={qq}, name={name}")
                        if qq:
                            mentions.append({
                                "qq": str(qq),
                                "name": name if name else f"用户{str(qq)[-4:]}"
                            })

            logger.info(f"提取到的@信息: {mentions}")

        logger.info(f"最终提取结果: {len(mentions)}条@信息")
        return mentions

    def has_mentions_to_others(self, message: List[MessageSegment] | str | list, self_id: int) -> bool:
        """
        检查消息中是否有@其他人（不包括机器人）

        Args:
            message: 消息内容
            self_id: 机器人自己的ID

        Returns:
            True表示@了其他人
        """
        mentions = self.extract_all_mentions(message)
        if not mentions:
            return False
        # 检查是否有@机器人以外的人
        return any(m["qq"] != str(self_id) for m in mentions)

    def extract_image_url(self, message: List[MessageSegment] | str | list) -> Optional[str]:
        """提取第一张图片的 URL"""
        if isinstance(message, list):
            for segment in message:
                if isinstance(segment, dict):
                    if segment.get("type") == "image":
                        data = segment.get("data", {})
                        # 优先使用 url，其次使用 file
                        return data.get("url") or data.get("file")
        elif isinstance(message, str):
            # 解析 CQ 码
            import re
            match = re.search(r'\[CQ:image,[^\]]*url=([^\],]+)', message)
            if match:
                return match.group(1)
        return None

    def extract_all_images(self, message: List[MessageSegment] | str | list) -> List[str]:
        """提取所有图片 URL"""
        images = []
        if isinstance(message, list):
            for segment in message:
                if isinstance(segment, dict):
                    if segment.get("type") == "image":
                        data = segment.get("data", {})
                        url = data.get("url") or data.get("file")
                        if url:
                            images.append(url)
        elif isinstance(message, str):
            import re
            matches = re.findall(r'\[CQ:image,[^\]]*url=([^\],]+)', message)
            images.extend(matches)
        return images

    def extract_user_nickname(self, sender: Optional[Dict]) -> str:
        """提取发送者昵称"""
        if not sender:
            return "Unknown"

        # 优先使用card（群昵称），其次是nickname（昵称），最后user_id
        card = sender.get("card")
        nickname = sender.get("nickname")
        user_id = sender.get("user_id")

        if card:
            return card
        if nickname:
            return nickname
        return str(user_id) if user_id else "Unknown"

    async def close(self):
        """关闭HTTP客户端"""
        await self.client.aclose()


# 全局NapCat客户端实例
napcat_client = NapCatClient()
