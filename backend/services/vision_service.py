"""Vision服务模块 - 通义千问VL图片识别."""

import logging
import json
import httpx
import base64
from typing import Optional, List

from backend.db_config import config_manager
from backend.config.loader import settings


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class VisionService:
    """Vision 服务 - 通义千问 VL API"""

    def __init__(self):
        """初始化Vision服务"""
        self.config = config_manager.get_vision_config()
        self.client = httpx.AsyncClient(timeout=settings.vision.timeout)

    def reload_config(self):
        """重新加载配置"""
        self.config = config_manager.get_vision_config()
        logger.info("Vision配置已重新加载")

    async def download_and_convert_to_base64(self, image_url: str) -> Optional[str]:
        """
        下载图片并转换为base64格式

        Args:
            image_url: QQ图片URL

        Returns:
            base64编码的图片数据（带data:image前缀），失败返回None
        """
        try:
            logger.info(f"正在下载图片: {image_url[:50]}...")

            # 下载图片
            response = await self.client.get(image_url, timeout=settings.vision.image_download_timeout)
            if response.status_code != 200:
                logger.warning(f"下载图片失败: status={response.status_code}")
                return None

            # 获取图片数据
            image_bytes = response.content

            # 转换为base64
            base64_data = base64.b64encode(image_bytes).decode('utf-8')

            # 检测图片类型
            content_type = response.headers.get('content-type', 'image/jpeg')

            # 返回data URL格式
            result = f"data:{content_type};base64,{base64_data}"
            logger.info(f"图片转换成功: {len(base64_data)} 字符")
            return result

        except Exception as e:
            logger.error(f"下载并转换图片失败: {e}")
            return None

    async def recognize_image(
        self,
        image_url: str,
        is_meme: bool = False,
        context: str = "群聊表情包"
    ) -> Optional[str]:
        """
        识别图片内容

        Args:
            image_url: 图片URL
            is_meme: 是否为表情包
            context: 上下文提示

        Returns:
            图片描述文本，失败返回None
        """
        if not self.config["enabled"]:
            logger.info("Vision服务未启用")
            return None

        # 检查API密钥
        if not self.config["api_key"]:
            logger.warning("Vision API密钥未配置")
            return None

        # 根据是否为表情包选择不同的prompt
        if is_meme:
            system_prompt = self._get_meme_prompt()
        else:
            system_prompt = self._get_normal_prompt()

        # 尝试将URL转换为base64（解决QQ图片URL访问限制问题）
        base64_image = await self.download_and_convert_to_base64(image_url)
        if base64_image:
            # 使用OpenAI兼容的image_url格式
            user_content = [
                {"type": "image_url", "image_url": {"url": base64_image}},
                {"type": "text", "text": system_prompt}
            ]
            logger.info("使用base64格式调用Vision API（OpenAI兼容格式）")
        else:
            # 降级：直接使用URL
            logger.warning("无法转换为base64，尝试直接使用URL")
            user_content = [
                {"type": "image_url", "image_url": {"url": image_url}},
                {"type": "text", "text": system_prompt}
            ]

        headers = {
            "Authorization": f"Bearer {self.config['api_key']}",
            "Content-Type": "application/json"
        }

        data = {
            "model": self.config["model"],
            "messages": [
                {"role": "user", "content": user_content}
            ]
        }

        # 重试机制
        for attempt in range(self.config["max_retries"]):
            try:
                response = await self.client.post(
                    f"{self.config['base_url']}/chat/completions",
                    headers=headers,
                    json=data,
                    timeout=self.config["timeout"]
                )

                if response.status_code == 200:
                    result = response.json()

                    # ===== 调试日志：输出完整API响应 =====
                    logger.info("="*60)
                    logger.info("【Vision API 完整响应】")
                    logger.info(f"完整响应JSON: {json.dumps(result, ensure_ascii=False, indent=2)}")
                    logger.info("="*60)

                    # 安全提取 content - 处理不同的 API 响应格式
                    try:
                        content = result["choices"][0]["message"]["content"]

                        # 处理不同的 content 格式
                        if isinstance(content, list):
                            # 格式1: content 是列表 [{type: "text", text: "..."}]
                            if len(content) > 0:
                                # 查找 text 类型的内容
                                text_content = None
                                for item in content:
                                    if isinstance(item, dict) and item.get("type") == "text":
                                        text_content = item.get("text")
                                        break
                                if text_content:
                                    description = text_content
                                else:
                                    # 如果没找到 text 类型，直接取第一个元素
                                    description = str(content[0])
                            else:
                                description = ""
                        elif isinstance(content, str):
                            # 格式2: content 是字符串
                            description = content
                        else:
                            # 其他格式，转字符串
                            description = str(content)

                        logger.info(f"图片识别成功: {description[:100]}...")
                        logger.info(f"提取的描述内容: {description}")
                        logger.info(f"描述长度: {len(description)} 字符")
                        return description if description else None
                    except (KeyError, IndexError, TypeError) as e:
                        logger.error(f"解析 API 响应失败: {e}")
                        logger.error(f"响应结构: {result}")
                        return None

                else:
                    logger.warning(f"Vision API返回错误: {response.status_code}")
                    if attempt < self.config["max_retries"] - 1:
                        continue

            except Exception as e:
                logger.error(f"Vision API调用失败: {e}")
                if attempt == 0:
                    return "图片识别失败，请稍后重试"

        logger.warning("Vision API调用失败，已达到最大重试次数")
        return None

    def _get_normal_prompt(self) -> str:
        """普通图片识别的Prompt"""
        return """请分析这张图片，用简体中文描述：
1. 图片表达了什么情绪？（开心/无奈/调侃/愤怒等）
2. 适合用在什么场景？
3. 如果有必要回复，应该怎么回复？

请用1-2句话简洁描述。
"""

    def _get_meme_prompt(self) -> str:
        """表情包识别的Prompt"""
        return """这是一个表情包（表情梗图），请重点分析：
1. 它表达了什么情绪或态度？（无奈/调侃/讽刺/自嘲/开心等）
2. 幽默点或梗在哪里？
3. 适合怎么回复？（回表情包/简短文字/不需要回复）

请用简短格式总结：[情绪] - [回复建议]
例如：
"无奈 - 可以回复'太真实了'或无奈表情包"
"调侃 - 可以顺着梗回复"
"""

vision_service = VisionService()