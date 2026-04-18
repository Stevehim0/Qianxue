"""心跳服务主循环。

每 N 秒向 backend 发一个心跳信号。
不传任何数据，不传群号，不传上下文——只是"叮"一声。
主系统自己决定要查什么、要不要说话。
"""

import asyncio
import logging
from datetime import datetime

import httpx

from heartbeat.config import HeartbeatConfig

logger = logging.getLogger(__name__)


class HeartbeatLoop:
    """心跳主循环。"""

    def __init__(self, config: HeartbeatConfig):
        self.config = config
        self._tick_count = 0

    async def run(self):
        """启动心跳循环。"""
        logger.info(
            f"Heartbeat started: interval={self.config.interval}s, "
            f"backend={self.config.backend_url}"
        )

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(connect=3.0, read=5.0, write=3.0, pool=3.0)
        ) as client:
            while True:
                try:
                    await self._tick(client)
                except Exception as e:
                    logger.error(f"Heartbeat tick failed: {e}")

                await asyncio.sleep(self.config.interval)

    async def _tick(self, client: httpx.AsyncClient):
        """执行一次心跳——只发一个空的 POST，不传任何业务数据。"""
        self._tick_count += 1

        try:
            resp = await client.post(
                f"{self.config.backend_url}/api/heartbeat",
            )

            if resp.status_code == 200:
                logger.debug(f"tick #{self._tick_count}: ok")
            else:
                logger.warning(
                    f"tick #{self._tick_count}: {resp.status_code} {resp.text[:80]}"
                )
        except httpx.ConnectError:
            logger.debug(f"tick #{self._tick_count}: backend unreachable")
        except httpx.TimeoutException:
            logger.debug(f"tick #{self._tick_count}: timeout")
        except Exception as e:
            logger.error(f"tick #{self._tick_count}: {e}")
