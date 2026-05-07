"""Vision服务模块 - 图片识别（支持GIF动图拆帧）."""

import logging
import json
import httpx
import base64
from typing import Optional, List

from backend.db_config import config_manager
from backend.config.loader import settings


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _extract_gif_frames(image_bytes: bytes, max_frames: int = 3) -> Optional[bytes]:
    """尝试从 GIF 提取关键帧并拼接为一张静态图。

    提取首帧、中间帧、末帧，缩小后水平拼接，返回 JPEG bytes。
    如果不是 GIF 或提取失败，返回 None。
    """
    try:
        from PIL import Image
        import io

        img = Image.open(io.BytesIO(image_bytes))
        if not hasattr(img, 'is_animated') or not img.is_animated:
            return None

        frame_count = img.n_frames
        if frame_count <= 1:
            return None

        # 取3帧：首、中、末
        if frame_count <= max_frames:
            indices = list(range(frame_count))
        else:
            mid = frame_count // 2
            indices = [0, mid, frame_count - 1]

        # 每帧缩小到最大 200px 宽
        max_w = 200
        frames = []
        for idx in indices:
            img.seek(idx)
            frame = img.convert('RGB')
            if frame.width > max_w:
                ratio = max_w / frame.width
                frame = frame.resize((max_w, int(frame.height * ratio)), Image.LANCZOS)
            frames.append(frame)

        total_width = sum(f.width for f in frames)
        max_height = max(f.height for f in frames)
        combined = Image.new('RGB', (total_width, max_height))

        x_offset = 0
        for f in frames:
            combined.paste(f, (x_offset, 0))
            x_offset += f.width

        buf = io.BytesIO()
        combined.save(buf, format='JPEG', quality=75)
        logger.info(f"GIF拆帧: {frame_count}帧, 提取{len(indices)}帧拼接, {buf.tell()} bytes")
        return buf.getvalue()

    except ImportError:
        logger.debug("Pillow未安装，跳过GIF拆帧")
        return None
    except Exception as e:
        logger.warning(f"GIF拆帧失败: {e}")
        return None


class VisionService:
    """Vision 服务 - 多模态 VL API"""

    def __init__(self):
        self.config = config_manager.get_vision_config()
        self.client = httpx.AsyncClient(timeout=120.0)

    def reload_config(self):
        self.config = config_manager.get_vision_config()
        logger.info("Vision配置已重新加载")

    async def download_and_convert_to_base64(self, image_url: str) -> Optional[str]:
        """下载图片并转换为base64。GIF 会自动拆帧拼接。"""
        try:
            logger.info(f"正在下载图片: {image_url[:50]}...")

            response = await self.client.get(image_url, timeout=settings.vision.image_download_timeout)
            if response.status_code != 200:
                logger.warning(f"下载图片失败: status={response.status_code}")
                return None

            image_bytes = response.content

            # 尝试 GIF 拆帧
            frames_image = _extract_gif_frames(image_bytes)
            if frames_image:
                base64_data = base64.b64encode(frames_image).decode('utf-8')
                return f"data:image/png;base64,{base64_data}"

            # 普通图片
            base64_data = base64.b64encode(image_bytes).decode('utf-8')
            content_type = response.headers.get('content-type', 'image/jpeg')
            logger.info(f"图片转换成功: {len(base64_data)} 字符")
            return f"data:{content_type};base64,{base64_data}"

        except Exception as e:
            logger.error(f"下载并转换图片失败: {e}")
            return None

    async def recognize_image(
        self,
        image_url: str,
        is_meme: bool = False,
        context: str = "群聊表情包"
    ) -> Optional[str]:
        """识别图片内容，返回描述文本。"""
        if not self.config["enabled"]:
            logger.info("Vision服务未启用")
            return None

        if not self.config["api_key"]:
            logger.warning("Vision API密钥未配置")
            return None

        system_prompt = self._get_meme_prompt() if is_meme else self._get_normal_prompt()

        base64_image = await self.download_and_convert_to_base64(image_url)
        if base64_image:
            user_content = [
                {"type": "image_url", "image_url": {"url": base64_image}},
                {"type": "text", "text": system_prompt}
            ]
            logger.info("使用base64格式调用Vision API")
        else:
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

        for attempt in range(self.config["max_retries"]):
            try:
                response = await self.client.post(
                    f"{self.config['base_url']}/chat/completions",
                    headers=headers,
                    json=data,
                    timeout=self.config["timeout"] * 2
                )

                if response.status_code == 200:
                    result = response.json()

                    try:
                        content = result["choices"][0]["message"]["content"]

                        if isinstance(content, list):
                            text_content = None
                            for item in content:
                                if isinstance(item, dict) and item.get("type") == "text":
                                    text_content = item.get("text")
                                    break
                            description = text_content or str(content[0]) if content else ""
                        elif isinstance(content, str):
                            description = content
                        else:
                            description = str(content)

                        logger.info(f"图片识别成功: {description[:100]}...")
                        return description if description else None
                    except (KeyError, IndexError, TypeError) as e:
                        logger.error(f"解析 API 响应失败: {e}")
                        return None

                else:
                    logger.warning(f"Vision API返回错误: {response.status_code}, body: {response.text[:300]}")
                    if attempt < self.config["max_retries"] - 1:
                        continue

            except Exception as e:
                logger.error(f"Vision API调用失败: {type(e).__name__}: {e}")
                if attempt == 0:
                    return "图片识别失败，请稍后重试"

        logger.warning("Vision API调用失败，已达到最大重试次数")
        return None

    def _get_normal_prompt(self) -> str:
        return "请详细描述这张图片的内容。包括：画面中有什么人/物/场景、文字内容、颜色和构图等视觉细节。用中文回答。"

    def _get_meme_prompt(self) -> str:
        return (
            "这是一个表情包，图片可能是GIF动图的关键帧从左到右拼接（代表动作的先后变化）。"
            "请描述：1. 角色/人物在做什么动作（如点头、摇头、鼓掌、挥手等）2. 表情和情绪"
            "3. 图上有什么文字。不要猜测角色名字或出处，只关注动作和情绪。用中文简短回答。"
        )


vision_service = VisionService()
