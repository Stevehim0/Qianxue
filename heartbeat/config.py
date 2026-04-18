"""心跳服务配置模块。"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)


@dataclass
class HeartbeatConfig:
    """心跳服务配置。"""
    interval: int = 10
    backend_url: str = "http://localhost:8000"


def load_config(config_path: Optional[str] = None) -> HeartbeatConfig:
    """从 YAML 文件加载配置。"""
    if config_path is None:
        config_path = str(Path(__file__).parent.parent / "heartbeat_config.yaml")

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except FileNotFoundError:
        logger.warning(f"Config file not found: {config_path}, using defaults")
        return HeartbeatConfig()

    return HeartbeatConfig(
        interval=data.get("interval", 10),
        backend_url=data.get("backend_url", "http://localhost:8000"),
    )
