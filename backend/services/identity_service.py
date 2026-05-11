"""统一身份服务 — 跨渠道身份映射.

把同一个人在不同平台（QQ、Discord、本地）的身份关联起来，
让千雪知道 "QQ 上的氿栢" 和 "Discord 上的 Steve" 是同一个人。
"""

import logging
from typing import Optional

from backend.database.db import get_db

logger = logging.getLogger(__name__)


class IdentityService:
    """统一身份管理."""

    # 内存缓存: (platform, platform_id) -> canonical_name
    # link_identity 时自动更新，格式化上下文时同步读取
    _cache: dict[tuple[str, str], str] = {}

    async def load_cache(self):
        """启动时从数据库加载缓存."""
        try:
            conn = await get_db()
            cursor = await conn.execute(
                """
                SELECT ia.platform, ia.platform_id, ui.canonical_name
                FROM identity_aliases ia
                JOIN unified_identities ui ON ia.identity_id = ui.id
                """
            )
            rows = await cursor.fetchall()
            self._cache = {(row[0], row[1]): row[2] for row in rows}
            logger.info(f"身份缓存已加载: {len(self._cache)} 条映射")
        except Exception as e:
            logger.warning(f"身份缓存加载失败: {e}")

    def resolve_cached(self, platform: str, platform_id: str) -> Optional[str]:
        """同步查缓存，返回千雪认识的名字。找不到返回 None."""
        return self._cache.get((platform, platform_id))

    async def initialize_tables(self):
        """建表（在 Database.initialize_tables 的迁移中调用）."""
        conn = await get_db()
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS unified_identities (
                id TEXT PRIMARY KEY,
                canonical_name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS identity_aliases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                identity_id TEXT NOT NULL,
                platform TEXT NOT NULL,
                platform_id TEXT NOT NULL,
                platform_nickname TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (identity_id) REFERENCES unified_identities(id),
                UNIQUE(platform, platform_id)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_aliases_platform
            ON identity_aliases(platform, platform_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_aliases_identity
            ON identity_aliases(identity_id)
        """)
        await conn.commit()
        logger.info("身份表已初始化")

    def _make_identity_id(self, name: str) -> str:
        """从名字生成统一身份 ID."""
        return f"person_{name}"

    async def resolve_name(self, platform: str, platform_id: str) -> Optional[str]:
        """根据平台 ID 查找千雪认识的名字。找不到返回 None."""
        try:
            conn = await get_db()
            cursor = await conn.execute(
                """
                SELECT ui.canonical_name
                FROM identity_aliases ia
                JOIN unified_identities ui ON ia.identity_id = ui.id
                WHERE ia.platform = ? AND ia.platform_id = ?
                """,
                (platform, platform_id),
            )
            row = await cursor.fetchone()
            return row[0] if row else None
        except Exception as e:
            logger.debug(f"身份查询失败: {e}")
            return None

    async def resolve_name_or_fallback(self, platform: str, platform_id: str, fallback: str = "") -> str:
        """查找名字，找不到就用 fallback."""
        name = await self.resolve_name(platform, platform_id)
        return name or fallback

    async def get_all_aliases(self, canonical_name: str) -> list[dict]:
        """获取某个统一身份的所有平台别名."""
        identity_id = self._make_identity_id(canonical_name)
        try:
            conn = await get_db()
            cursor = await conn.execute(
                """
                SELECT platform, platform_id, platform_nickname
                FROM identity_aliases
                WHERE identity_id = ?
                """,
                (identity_id,),
            )
            return [
                {"platform": row[0], "platform_id": row[1], "nickname": row[2]}
                for row in await cursor.fetchall()
            ]
        except Exception:
            return []

    async def link_identity(
        self,
        identity_name: str,
        platform: str,
        platform_id: str,
        platform_nickname: str = "",
        reason: str = "",
    ) -> bool:
        """建立身份关联。如果统一身份不存在则创建。

        Args:
            identity_name: 千雪认识的名字（统一身份名）
            platform: 平台标识 (qq / discord / computer)
            platform_id: 该平台上的用户 ID
            platform_nickname: 该平台上的昵称
            reason: 建立关联的原因（日志用）
        """
        try:
            conn = await get_db()
            identity_id = self._make_identity_id(identity_name)

            # 确保统一身份存在
            cursor = await conn.execute(
                "SELECT id FROM unified_identities WHERE id = ?",
                (identity_id,),
            )
            if not await cursor.fetchone():
                await conn.execute(
                    "INSERT OR IGNORE INTO unified_identities (id, canonical_name) VALUES (?, ?)",
                    (identity_id, identity_name),
                )
                logger.info(f"创建统一身份: {identity_name}")

            # 检查这个 platform_id 是否已经被别人占用了
            cursor = await conn.execute(
                "SELECT identity_id FROM identity_aliases WHERE platform = ? AND platform_id = ?",
                (platform, platform_id),
            )
            existing = await cursor.fetchone()
            if existing:
                if existing[0] == identity_id:
                    # 已经是同一个人，更新昵称即可
                    await conn.execute(
                        "UPDATE identity_aliases SET platform_nickname = ? WHERE platform = ? AND platform_id = ?",
                        (platform_nickname, platform, platform_id),
                    )
                    logger.info(f"更新别名昵称: {platform}:{platform_id} -> {platform_nickname}")
                else:
                    # 这个平台 ID 已经绑到另一个人了，换绑
                    await conn.execute(
                        "UPDATE identity_aliases SET identity_id = ?, platform_nickname = ? WHERE platform = ? AND platform_id = ?",
                        (identity_id, platform_nickname, platform, platform_id),
                    )
                    logger.info(f"换绑: {platform}:{platform_id} 从 {existing[0]} 改为 {identity_id} ({reason})")
            else:
                # 新关联
                await conn.execute(
                    "INSERT INTO identity_aliases (identity_id, platform, platform_id, platform_nickname) VALUES (?, ?, ?, ?)",
                    (identity_id, platform, platform_id, platform_nickname),
                )
                logger.info(f"建立关联: {platform}:{platform_id}({platform_nickname}) = {identity_name} ({reason})")

            await conn.commit()
            # 更新内存缓存
            self._cache[(platform, platform_id)] = identity_name
            return True

        except Exception as e:
            logger.error(f"身份关联失败: {e}")
            return False

    async def get_identity_brief(self, canonical_name: str) -> str:
        """获取一个人的身份简介（供 brain 了解）。"""
        aliases = await self.get_all_aliases(canonical_name)
        if not aliases:
            return ""

        parts = []
        for a in aliases:
            nick = f"({a['nickname']})" if a["nickname"] else ""
            parts.append(f"{a['platform']}:{nick}")
        return f"{canonical_name} 的其他身份: {', '.join(parts)}"


identity_service = IdentityService()
