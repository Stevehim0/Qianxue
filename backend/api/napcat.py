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
        # 群名映射 {群名: group_id_str, group_id_str: 群名}
        self._group_name_map: Dict[str, str] = {}
        self._group_id_map: Dict[str, str] = {}

    async def refresh_group_map(self):
        """从 NapCat 拉取群列表，更新群名映射。"""
        groups = await self.get_group_list()
        if not groups:
            return
        self._group_name_map.clear()
        self._group_id_map.clear()
        for g in groups:
            gid = str(g.get("group_id", ""))
            name = g.get("group_name", "")
            if gid and name:
                self._group_name_map[name] = gid
                self._group_id_map[gid] = name
        logger.info(f"群名映射已更新: {len(self._group_name_map)} 个群")

    def resolve_group_id(self, name_or_id: str) -> Optional[str]:
        """群名或群号 → 群号。支持群名、群号、private_ 前缀。"""
        if name_or_id.startswith("private_") or name_or_id.startswith("dm_"):
            return name_or_id
        if name_or_id in self._group_name_map:
            return self._group_name_map[name_or_id]
        # 可能本身就是群号
        if name_or_id.isdigit():
            return name_or_id
        return None

    def get_group_name(self, group_id: str) -> Optional[str]:
        """群号 → 群名。"""
        return self._group_id_map.get(group_id)

    def get_group_list_text(self) -> str:
        """返回群列表的简短文本，用于 AI prompt。"""
        if not self._group_name_map:
            return ""
        lines = []
        for name, gid in self._group_name_map.items():
            lines.append(f"- {name}")
        return "\n".join(lines)

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

    async def get_msg(self, message_id: int) -> Optional[Dict]:
        """通过消息ID获取原始消息内容（OneBot get_msg API）"""
        if not self.http_url:
            return None
        try:
            response = await self.client.post(
                f"{self.http_url}/get_msg",
                json={"message_id": message_id}
            )
            response.raise_for_status()
            result = response.json()
            if result.get("status") == "ok":
                return result.get("data")
            return None
        except Exception as e:
            logger.error(f"获取消息失败: {e}")
            return None

    def extract_reply_id(self, message: list | str) -> Optional[int]:
        """提取回复消息的ID。支持 array 格式和 CQ 码字符串格式。"""
        if isinstance(message, list):
            for segment in message:
                if isinstance(segment, dict) and segment.get("type") == "reply":
                    msg_id = segment.get("data", {}).get("id")
                    if msg_id:
                        try:
                            return int(msg_id)
                        except (ValueError, TypeError):
                            return None
        elif isinstance(message, str):
            import re
            match = re.search(r'\[CQ:reply,id=(\d+)\]', message)
            if match:
                try:
                    return int(match.group(1))
                except ValueError:
                    return None
        return None

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
        """提取纯文本，将@转为可读格式，去除其他CQ码"""
        if isinstance(message, str):
            import re
            # 先把 [CQ:at,qq=xxx,name=yyy] 转为 @yyy
            text = re.sub(r'\[CQ:at,qq=\d+,name=([^\]]+)\]', r'@\1', message)
            text = re.sub(r'\[CQ:at,qq=(\d+)\]', lambda m: f'@用户{m.group(1)[-4:]}', text)
            # 移除其余CQ码
            return re.sub(r'\[CQ:.*?\]', '', text)

        if isinstance(message, list):
            text_parts = []
            for segment in message:
                if isinstance(segment, dict):
                    seg_type = segment.get("type")
                    if seg_type == "text":
                        text_parts.append(segment.get("data", {}).get("text", ""))
                    elif seg_type == "at":
                        data = segment.get("data", {})
                        name = data.get("name") or f"用户{str(data.get('qq', ''))[-4:]}"
                        text_parts.append(f"@{name}")
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
