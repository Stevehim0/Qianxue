"""内置心跳管理器 — 在后端进程内运行，无需外部进程。

前端保存心跳配置后立即生效，不需要重启任何服务。
"""

import asyncio
import logging
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)


class HeartbeatManager:
    """管理内置心跳循环的启停。"""

    def __init__(self):
        self._task: Optional[asyncio.Task] = None
        self._enabled: bool = False
        self._interval: int = 10
        self._tick_count: int = 0
        self._brain = None
        self._config_path = Path(__file__).resolve().parent.parent.parent / "heartbeat_config.yaml"

    def set_brain(self, brain) -> None:
        self._brain = brain

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    def load_config(self) -> dict:
        """从 YAML 加载配置，返回配置 dict。"""
        try:
            with open(self._config_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except FileNotFoundError:
            return {"enabled": False, "interval": 10, "backend_url": "http://localhost:8000"}

    def save_config(self, data: dict) -> dict:
        """保存配置到 YAML 文件。"""
        current = {}
        if self._config_path.exists():
            with open(self._config_path, "r", encoding="utf-8") as f:
                current = yaml.safe_load(f) or {}
        for key in ("enabled", "interval", "backend_url"):
            if key in data:
                current[key] = data[key]
        with open(self._config_path, "w", encoding="utf-8") as f:
            yaml.dump(current, f, allow_unicode=True, default_flow_style=False)
        return current

    def start(self):
        """启动心跳循环（幂等）。"""
        if self.is_running:
            return
        cfg = self.load_config()
        self._enabled = cfg.get("enabled", False)
        self._interval = cfg.get("interval", 10)
        if not self._enabled:
            logger.info("Heartbeat disabled in config, not starting")
            return
        self._task = asyncio.create_task(self._run())
        logger.info(f"Heartbeat started: interval={self._interval}s")

    def stop(self):
        """停止心跳循环。"""
        if self._task and not self._task.done():
            self._task.cancel()
            logger.info("Heartbeat stopped")
        self._task = None

    def restart(self):
        """重启心跳循环（配置变更后调用）。"""
        self.stop()
        self.start()

    async def _run(self):
        """心跳主循环。"""
        while True:
            try:
                await self._tick()
            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.error(f"Heartbeat tick failed: {e}")
            await asyncio.sleep(self._interval)

    async def _tick(self):
        """执行一次心跳——直接调用 brain 的主动思考。"""
        self._tick_count += 1

        if self._brain is None:
            logger.debug(f"tick #{self._tick_count}: brain not initialized")
            return

        # 睡眠/困倦期间跳过
        from backend.services.sleep_manager import sleep_manager
        if sleep_manager.should_skip_heartbeat:
            logger.debug(f"tick #{self._tick_count}: sleeping, skipped")
            return

        try:
            await self._brain.proactive_think()
            logger.debug(f"tick #{self._tick_count}: ok")
        except Exception as e:
            logger.error(f"tick #{self._tick_count}: proactive think failed: {e}")

    def get_status(self) -> dict:
        """返回当前心跳状态。"""
        cfg = self.load_config()
        return {
            "running": self.is_running,
            "enabled": cfg.get("enabled", False),
            "interval": cfg.get("interval", 10),
            "backend_url": cfg.get("backend_url", "http://localhost:8000"),
            "tick_count": self._tick_count,
        }


heartbeat_manager = HeartbeatManager()
