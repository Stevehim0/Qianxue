"""配置管理模块."""

import json
import logging
from dataclasses import asdict, fields
from typing import Optional, Dict
from backend.database.db import get_db
from backend.database.models import ApiConfig, SystemPromptConfig
from backend.config.loader import settings


# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ConfigManager:
    """配置管理器

    配置项说明:
        api_config          - LLM API 配置（模型、密钥、接口地址等）
        system_prompt       - 系统提示词（全局 + 按群聊自定义）
        context_window      - 上下文窗口大小（发给 LLM 的最近对话轮数，默认 10）
        debounce_seconds    - 消息合并等待秒数（收到消息后等多久确认对方说完了，默认 6）
        vision              - 图片识别配置（模型、API Key 等）
        settings_sections   - 各 YAML section 的 DB 覆盖值（brain, sleep, memory 等）
    """

    def __init__(self):
        self._api_config: Optional[ApiConfig] = None
        self._system_prompt_config: Optional[SystemPromptConfig] = None
        self._context_window: int = settings.context.group_context_limit
        self._debounce_seconds: int = 10
        self._vision_config: Optional[Dict] = None
        self._voice_config: Optional[Dict] = None
        # 通用 section 覆盖值: section_name -> dict
        self._section_overrides: Dict[str, Dict] = {}

    async def load_configs(self):
        """从数据库加载配置"""
        conn = await get_db()

        # 加载API配置
        cursor = await conn.execute(
            "SELECT value FROM configs WHERE key = ?",
            ("api_config",)
        )
        row = await cursor.fetchone()
        if row:
            try:
                self._api_config = ApiConfig(**json.loads(row[0]))
            except Exception as e:
                logger.error(f"加载API配置失败: {e}")
                self._api_config = ApiConfig()
        else:
            self._api_config = ApiConfig()

        # 加载系统提示词配置
        cursor = await conn.execute(
            "SELECT value FROM configs WHERE key = ?",
            ("system_prompt",)
        )
        row = await cursor.fetchone()
        if row:
            try:
                self._system_prompt_config = SystemPromptConfig(**json.loads(row[0]))
            except Exception as e:
                logger.error(f"加载系统提示词配置失败: {e}")
                self._system_prompt_config = SystemPromptConfig()
        else:
            self._system_prompt_config = SystemPromptConfig()

        # 加载上下文窗口大小
        cursor = await conn.execute(
            "SELECT value FROM configs WHERE key = ?",
            ("context_window",)
        )
        row = await cursor.fetchone()
        if row:
            try:
                self._context_window = int(row[0])
            except Exception as e:
                logger.error(f"加载上下文窗口配置失败: {e}")
                self._context_window = 10

        # 加载 debounce 等待秒数
        cursor = await conn.execute(
            "SELECT value FROM configs WHERE key = ?",
            ("debounce_seconds",)
        )
        row = await cursor.fetchone()
        if row:
            try:
                self._debounce_seconds = int(row[0])
            except Exception as e:
                logger.error(f"加载debounce配置失败: {e}")
                self._debounce_seconds = 10

        # 加载Vision配置（数据库覆盖YAML默认值）
        cursor = await conn.execute(
            "SELECT value FROM configs WHERE key = ?",
            ("vision",)
        )
        row = await cursor.fetchone()
        if row:
            try:
                self._vision_config = json.loads(row[0])
            except Exception as e:
                logger.error(f"加载Vision配置失败: {e}")

        # 加载Voice配置（数据库覆盖YAML默认值）
        cursor = await conn.execute(
            "SELECT value FROM configs WHERE key = ?",
            ("voice",)
        )
        row = await cursor.fetchone()
        if row:
            try:
                self._voice_config = json.loads(row[0])
            except Exception as e:
                logger.error(f"加载Voice配置失败: {e}")

        # 加载通用 settings section 覆盖值
        for section in settings.section_names():
            db_key = f"settings_{section}"
            cursor = await conn.execute(
                "SELECT value FROM configs WHERE key = ?", (db_key,)
            )
            row = await cursor.fetchone()
            if row:
                try:
                    override = json.loads(row[0])
                    if isinstance(override, dict):
                        self._section_overrides[section] = override
                        settings.update_section(section, override)
                except Exception as e:
                    logger.error(f"加载 settings/{section} 失败: {e}")

    async def save_api_config(self, config: ApiConfig):
        """保存API配置"""
        conn = await get_db()
        await conn.execute(
            "UPDATE configs SET value = ?, updated_at = CURRENT_TIMESTAMP WHERE key = ?",
            (config.model_dump_json(), "api_config")
        )
        await conn.commit()
        self._api_config = config

    async def save_system_prompt_config(self, config: SystemPromptConfig):
        """保存系统提示词配置"""
        conn = await get_db()
        await conn.execute(
            "UPDATE configs SET value = ?, updated_at = CURRENT_TIMESTAMP WHERE key = ?",
            (config.model_dump_json(), "system_prompt")
        )
        await conn.commit()
        self._system_prompt_config = config

    async def save_context_window(self, size: int):
        """保存上下文窗口大小"""
        conn = await get_db()
        await conn.execute(
            "UPDATE configs SET value = ?, updated_at = CURRENT_TIMESTAMP WHERE key = ?",
            (str(size), "context_window")
        )
        await conn.commit()
        self._context_window = size

    @property
    def api_config(self) -> ApiConfig:
        """获取API配置"""
        if self._api_config is None:
            self._api_config = ApiConfig()
        return self._api_config

    @property
    def system_prompt_config(self) -> SystemPromptConfig:
        """获取系统提示词配置"""
        if self._system_prompt_config is None:
            self._system_prompt_config = SystemPromptConfig()
        return self._system_prompt_config

    @property
    def context_window(self) -> int:
        """获取上下文窗口大小"""
        return self._context_window

    @property
    def debounce_seconds(self) -> int:
        """获取消息 debounce 等待秒数"""
        return self._debounce_seconds

    def get_current_api(self) -> Optional[Dict[str, str]]:
        """获取当前使用的API配置"""
        if not self.api_config.current_api:
            return None
        return self.api_config.apis.get(self.api_config.current_api)

    def get_system_prompt(self, group_id: Optional[str] = None) -> str:
        """获取系统提示词"""
        if group_id and str(group_id) in self._system_prompt_config.group_system_prompts:
            return self._system_prompt_config.group_system_prompts[str(group_id)]
        return self._system_prompt_config.global_system_prompt

    async def save_vision_config(self, config: Dict[str, any]):
        """保存Vision配置"""
        conn = await get_db()
        await conn.execute(
            """
            INSERT OR REPLACE INTO configs (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            """,
            ("vision", json.dumps(config))
        )
        await conn.commit()

    def get_vision_config(self) -> Dict[str, any]:
        """获取Vision配置（数据库覆盖 > YAML 默认值）"""
        base = {
            "enabled": settings.vision.enabled,
            "provider": settings.vision.provider,
            "model": settings.vision.model,
            "api_key": settings.vision.api_key,
            "base_url": settings.vision.base_url,
            "max_retries": settings.vision.max_retries,
            "timeout": settings.vision.timeout,
        }
        if self._vision_config:
            base.update(self._vision_config)
        return base

    def get_voice_config(self) -> Dict[str, any]:
        """获取Voice配置（数据库覆盖 > YAML 默认值）"""
        base = {
            "funasr_websocket_url": settings.voice.funasr_websocket_url,
            "funasr_timeout": settings.voice.funasr_timeout,
            "tts_default_voice": settings.voice.tts_default_voice,
            "tts_timeout": settings.voice.tts_timeout,
            "tts_rate": settings.voice.tts_rate,
            "tts_volume": settings.voice.tts_volume,
            "audio_target_sample_rate": settings.voice.audio_target_sample_rate,
            "audio_target_channels": settings.voice.audio_target_channels,
        }
        if self._voice_config:
            base.update(self._voice_config)
        return base

    def get_all_settings(self) -> Dict[str, Dict]:
        """返回所有 settings section 的当前值（含 DB 覆盖）。"""
        result = {}
        for section in settings.section_names():
            dc = getattr(settings, section)
            result[section] = asdict(dc)
        return result

    async def save_settings_section(self, section: str, data: Dict) -> bool:
        """保存指定 section 的配置到 DB 并热更新内存。"""
        if section not in settings.section_names():
            return False

        # 热更新内存
        settings.update_section(section, data)

        # 合并已有覆盖值
        existing = self._section_overrides.get(section, {})
        existing.update(data)
        self._section_overrides[section] = existing

        # 写入 DB
        conn = await get_db()
        db_key = f"settings_{section}"
        await conn.execute(
            "INSERT OR REPLACE INTO configs (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
            (db_key, json.dumps(existing)),
        )
        await conn.commit()
        return True


# 全局配置管理器实例
config_manager = ConfigManager()
