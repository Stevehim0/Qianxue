"""千雪屏幕感知客户端 — 本地截屏 + 发送到后端识别.

用法:
    # 手动模式：按 Ctrl+Shift+S 截屏发送
    python screen_capture_agent.py

    # 自动模式：每 10 秒自动截屏
    python screen_capture_agent.py --auto --interval 10

    # 指定后端地址
    python screen_capture_agent.py --host http://localhost:5002

依赖:
    pip install mss pillow httpx keyboard
"""

import argparse
import base64
import io
import json
import logging
import sys
import time
from pathlib import Path

try:
    import mss
    import mss.tools
except ImportError:
    print("请安装 mss: pip install mss")
    sys.exit(1)

try:
    from PIL import Image
except ImportError:
    print("请安装 Pillow: pip install Pillow")
    sys.exit(1)

try:
    import httpx
except ImportError:
    print("请安装 httpx: pip install httpx")
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("screen_agent")


class ScreenCaptureAgent:
    def __init__(self, host: str = "http://localhost:8000", quality: int = 70, max_width: int = 1280):
        self.host = host.rstrip("/")
        self.quality = quality
        self.max_width = max_width
        self.client = httpx.Client(timeout=60.0)

    def capture_screen(self, monitor: int = 0) -> bytes:
        """截取屏幕，返回压缩后的 JPEG bytes."""
        with mss.mss() as sct:
            if monitor >= len(sct.monitors):
                monitor = 0
            shot = sct.grab(sct.monitors[monitor])

            img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")

            # 缩放到合理尺寸
            if img.width > self.max_width:
                ratio = self.max_width / img.width
                new_size = (self.max_width, int(img.height * ratio))
                img = img.resize(new_size, Image.LANCZOS)

            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=self.quality)
            return buf.getvalue()

    def send_frame(self, image_bytes: bytes, trigger: str = "manual") -> dict:
        """发送截图到后端."""
        b64 = base64.b64encode(image_bytes).decode("utf-8")

        try:
            resp = self.client.post(
                f"{self.host}/api/screen/perceive",
                json={
                    "image_base64": b64,
                    "trigger": trigger,
                    "metadata": self._get_metadata(),
                },
            )
            if resp.status_code == 200:
                return resp.json()
            else:
                logger.error(f"后端返回 {resp.status_code}: {resp.text[:200]}")
                return {"success": False, "message": f"HTTP {resp.status_code}"}
        except httpx.ConnectError:
            logger.error(f"无法连接后端 {self.host}，请确认千雪后端正在运行")
            return {"success": False, "message": "连接失败"}
        except Exception as e:
            logger.error(f"发送失败: {e}")
            return {"success": False, "message": str(e)}

    def _get_metadata(self) -> dict:
        """收集客户端元数据."""
        meta = {}
        try:
            # 尝试获取活动窗口标题（Windows only）
            import ctypes
            buf = ctypes.create_unicode_buffer(256)
            ctypes.windll.user32.GetWindowTextW(
                ctypes.windll.user32.GetForegroundWindow(), buf, 256
            )
            meta["window_title"] = buf.value or ""
        except Exception:
            pass
        return meta

    def check_health(self) -> bool:
        """检查后端是否可用."""
        try:
            resp = self.client.get(f"{self.host}/health", timeout=5.0)
            return resp.status_code == 200
        except Exception:
            return False


def run_manual_mode(agent: ScreenCaptureAgent):
    """手动模式：键盘快捷键触发截屏."""
    try:
        import keyboard
    except ImportError:
        print("手动模式需要 keyboard 库: pip install keyboard")
        print("或者用自动模式: python screen_capture_agent.py --auto")
        sys.exit(1)

    print(f"千雪屏幕感知客户端已启动")
    print(f"后端: {agent.host}")
    print(f"按 Ctrl+Shift+S 截屏发送给千雪")
    print(f"按 Ctrl+Shift+Q 退出")
    print()

    def on_capture():
        logger.info("截屏中...")
        t0 = time.time()
        img_bytes = agent.capture_screen()
        result = agent.send_frame(img_bytes, trigger="manual")
        elapsed = time.time() - t0
        if result.get("success"):
            desc = result.get("description", "")
            logger.info(f"识别完成 ({elapsed:.1f}s): {desc[:80]}")
        else:
            logger.warning(f"识别失败 ({elapsed:.1f}s): {result.get('message', '')}")

    keyboard.add_hotkey("ctrl+shift+s", on_capture)
    keyboard.wait("ctrl+shift+q")
    print("已退出")


def run_auto_mode(agent: ScreenCaptureAgent, interval: int = 10):
    """自动模式：定时截屏."""
    print(f"千雪屏幕感知客户端（自动模式）")
    print(f"后端: {agent.host}")
    print(f"截屏间隔: {interval}秒")
    print(f"按 Ctrl+C 退出")
    print()

    try:
        while True:
            t0 = time.time()
            img_bytes = agent.capture_screen()
            size_kb = len(img_bytes) / 1024
            logger.info(f"截屏 {size_kb:.0f}KB，发送中...")
            result = agent.send_frame(img_bytes, trigger="interval")
            elapsed = time.time() - t0

            if result.get("success"):
                desc = result.get("description", "")
                msg = result.get("message", "")
                if "跳过" in msg:
                    logger.info(f"[{elapsed:.1f}s] 内容未变化，跳过")
                else:
                    logger.info(f"[{elapsed:.1f}s] {desc[:80]}")
            else:
                logger.warning(f"[{elapsed:.1f}s] 失败: {result.get('message', '')}")

            # 等待间隔（扣除处理时间）
            wait = max(1, interval - elapsed)
            time.sleep(wait)

    except KeyboardInterrupt:
        print("\n已退出")


def main():
    parser = argparse.ArgumentParser(description="千雪屏幕感知客户端")
    parser.add_argument("--host", default="http://localhost:8000", help="千雪后端地址")
    parser.add_argument("--auto", action="store_true", help="自动定时截屏模式")
    parser.add_argument("--interval", type=int, default=10, help="自动模式截屏间隔（秒）")
    parser.add_argument("--quality", type=int, default=70, help="JPEG 质量 (1-100)")
    parser.add_argument("--max-width", type=int, default=1280, help="截图最大宽度")
    args = parser.parse_args()

    agent = ScreenCaptureAgent(
        host=args.host,
        quality=args.quality,
        max_width=args.max_width,
    )

    # 检查后端
    if not agent.check_health():
        logger.error(f"后端 {args.host} 不可用，请先启动千雪后端")
        sys.exit(1)

    logger.info(f"后端连接正常: {args.host}")

    if args.auto:
        run_auto_mode(agent, interval=args.interval)
    else:
        run_manual_mode(agent)


if __name__ == "__main__":
    main()
