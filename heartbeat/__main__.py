"""心跳服务入口（已废弃 — 心跳已集成到后端进程内）。

心跳循环现在由 backend/services/heartbeat_manager.py 管理，
随 Backend API 进程一起启动，无需单独运行。

保留此文件仅为向后兼容。如需配置心跳，请使用 Web 界面的"心跳服务"设置。
"""

import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)

logger = logging.getLogger(__name__)


def main():
    logger.warning(
        "心跳服务已集成到后端进程内，无需单独运行。"
        "请通过 Web 界面配置心跳，或重启 Backend API 进程。"
    )


if __name__ == "__main__":
    main()
