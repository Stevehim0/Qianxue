"""心跳服务入口。

用法: python -m heartbeat
"""

import asyncio
import logging
import sys

from heartbeat.config import load_config
from heartbeat.loop import HeartbeatLoop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)

logger = logging.getLogger(__name__)


def main():
    config_path = None
    if len(sys.argv) > 1:
        config_path = sys.argv[1]

    config = load_config(config_path)

    loop = HeartbeatLoop(config)
    logger.info("Starting heartbeat service...")
    asyncio.run(loop.run())


if __name__ == "__main__":
    main()
