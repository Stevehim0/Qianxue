"""统一配置加载器。

从 backend/config/*.yaml 加载配置文件，支持环境变量覆盖。
优先级：环境变量 > YAML 文件 > dataclass 默认值。

环境变量命名规则：QIANXUE_{FILE}__{KEY}（双下划线分隔嵌套）
示例：QIANXUE_SERVER__PORT=9000, QIANXUE_LLM__THINKING_PROVIDER__API_KEY=sk-xxx
"""

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Dataclass 定义
# ---------------------------------------------------------------------------

_DEFAULT_INTERIM_MESSAGES = [
    "嗯...让我想想",
    "等一下哈",
    "我想想...",
    "稍等",
    "让我回忆一下",
    "嗯.....",
    "哈......",
    "啊...",
    "唔...",
    "诶...",
    "呃...",
    "嗯...",
    "等等哈",
    "等下",
]


@dataclass
class LLMProviderConfig:
    api_key: str = ""
    base_url: str = ""
    model: str = ""


@dataclass
class LLMConfig:
    thinking_provider: LLMProviderConfig = field(default_factory=LLMProviderConfig)
    speaking_provider: LLMProviderConfig = field(default_factory=LLMProviderConfig)
    anthropic_max_tokens: int = 1024
    api_timeout: float = 120.0


@dataclass
class ServerConfig:
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "info"
    reload: bool = True
    sse_heartbeat_timeout: float = 1.0


@dataclass
class MemoryConfig:
    service_url: str = "http://localhost:8001"
    provider_connect_timeout: float = 5.0
    provider_read_timeout: float = 60.0
    provider_write_timeout: float = 10.0
    provider_pool_timeout: float = 10.0
    stm_connect_timeout: float = 3.0
    stm_read_timeout: float = 10.0
    stm_write_timeout: float = 5.0
    stm_pool_timeout: float = 5.0
    profile_ensure_url: str = ""
    profile_ensure_timeout: float = 5.0
    profile_turn_threshold: int = 10

    def __post_init__(self):
        if not self.profile_ensure_url:
            self.profile_ensure_url = f"{self.service_url}/api/profile/ensure"


@dataclass
class BrainConfig:
    max_iterations: int = 5
    fast_tools: List[str] = field(default_factory=lambda: ["get_time", "get_context"])
    interim_messages: List[str] = field(default_factory=lambda: list(_DEFAULT_INTERIM_MESSAGES))
    interim_max_length: int = 50
    state_api_url: str = ""
    state_api_timeout: float = 3.0
    context_limit: int = 20
    context_time_window: int = 60
    gap_threshold: int = 600
    proactive_context_limit: int = 10
    proactive_context_time_window: float = 0.5
    proactive_speak_cooldown: int = 120
    proactive_speak_max_per_hour: int = 3
    mention_priority: int = 10
    significant_length: int = 20
    stm_importance_user_mention: float = 0.7
    stm_importance_significant_msg: float = 0.4
    stm_importance_private_chat: float = 0.8


@dataclass
class SleepConfig:
    enabled: bool = False
    wind_down_hour: int = 23
    sleep_hour: int = 0
    wake_hour: int = 8
    awake_energy_value: float = 0.8
    awake_energy_label: str = "充沛"
    tired_energy_value: float = 0.3
    tired_energy_label: str = "困倦"
    check_interval: int = 60


@dataclass
class NapCatConfig:
    http_url: str = "http://localhost:3000"
    timeout: float = 30.0


@dataclass
class AdminConfig:
    qq_id: str = ""
    cooldown_seconds: int = 60


@dataclass
class VisionConfig:
    enabled: bool = True
    provider: str = "qwen"
    model: str = "qwen-vl-max"
    api_key: str = ""
    base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    max_retries: int = 3
    timeout: int = 30
    image_download_timeout: float = 15.0


@dataclass
class ContextConfig:
    group_context_limit: int = 50
    group_context_time_window: int = 30
    memory_recall_limit: int = 5


@dataclass
class Settings:
    llm: LLMConfig = field(default_factory=LLMConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    brain: BrainConfig = field(default_factory=BrainConfig)
    sleep: SleepConfig = field(default_factory=SleepConfig)
    napcat: NapCatConfig = field(default_factory=NapCatConfig)
    admin: AdminConfig = field(default_factory=AdminConfig)
    vision: VisionConfig = field(default_factory=VisionConfig)
    context: ContextConfig = field(default_factory=ContextConfig)


# ---------------------------------------------------------------------------
# ConfigLoader
# ---------------------------------------------------------------------------

class ConfigLoader:
    ENV_PREFIX = "QIANXUE_"

    def __init__(self, config_dir: Optional[str] = None):
        if config_dir is None:
            config_dir = str(Path(__file__).parent)
        self._config_dir = Path(config_dir)
        self._raw: Dict[str, Any] = {}

    def load(self) -> Settings:
        self._raw = {}
        self._load_yaml_files()

        if not self._raw:
            self._try_legacy_config()

        self._apply_env_overrides()
        return self._build_settings()

    def _load_yaml_files(self):
        if not self._config_dir.exists():
            logger.warning(f"Config directory not found: {self._config_dir}")
            return

        for yaml_file in sorted(self._config_dir.glob("*.yaml")):
            if yaml_file.name.endswith(".example.yaml"):
                continue
            name = yaml_file.stem
            try:
                with open(yaml_file, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                self._raw[name] = data
                logger.info(f"Loaded config: {yaml_file.name}")
            except Exception as e:
                logger.warning(f"Failed to load {yaml_file.name}: {e}")
                self._raw[name] = {}

    def _try_legacy_config(self):
        legacy_path = Path(__file__).parent.parent / "llm_config.yaml"
        if not legacy_path.exists():
            return
        try:
            with open(legacy_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            self._raw["llm"] = {
                "thinking_provider": data.get("thinking_provider", {}),
                "speaking_provider": data.get("speaking_provider", {}),
            }
            self._raw["brain"] = {"brain": {"max_iterations": data.get("brain", {}).get("max_iterations", 5)}}
            self._raw["napcat"] = {"napcat": {"http_url": data.get("napcat", {}).get("http_url", "http://localhost:3000")}}
            self._raw["memory"] = {"memory": {"service_url": data.get("memory", {}).get("service_url", "http://localhost:8001")}}
            self._raw["admin"] = {"admin": {"qq_id": data.get("admin", {}).get("qq_id", "")}}
            logger.info("Loaded legacy llm_config.yaml")
        except Exception as e:
            logger.warning(f"Failed to load legacy config: {e}")

    def _apply_env_overrides(self):
        # 向后兼容：MEMORY_SERVICE_URL
        mem_url = os.getenv("MEMORY_SERVICE_URL")
        if mem_url:
            self._raw.setdefault("memory", {}).setdefault("memory", {})["service_url"] = mem_url

        prefix = self.ENV_PREFIX
        for key, value in os.environ.items():
            if not key.startswith(prefix):
                continue
            config_path = key[len(prefix):].lower().split("__")
            self._set_nested(self._raw, config_path, self._parse_env_value(value))

    @staticmethod
    def _set_nested(d: dict, keys: list, value):
        for k in keys[:-1]:
            d = d.setdefault(k, {})
        d[keys[-1]] = value

    @staticmethod
    def _parse_env_value(value: str) -> Any:
        if value.lower() in ("true", "yes", "1"):
            return True
        if value.lower() in ("false", "no", "0"):
            return False
        try:
            return int(value)
        except ValueError:
            pass
        try:
            return float(value)
        except ValueError:
            pass
        return value

    # ---- Build methods ----

    def _build_settings(self) -> Settings:
        mem = self._build_memory()
        return Settings(
            llm=self._build_llm(),
            server=self._build_server(),
            memory=mem,
            brain=self._build_brain(mem.service_url),
            sleep=self._build_sleep(),
            napcat=self._build_napcat(),
            admin=self._build_admin(),
            vision=self._build_vision(),
            context=self._build_context(),
        )

    def _build_llm(self) -> LLMConfig:
        r = self._raw.get("llm", {})
        tp = r.get("thinking_provider", {})
        sp = r.get("speaking_provider", {})
        return LLMConfig(
            thinking_provider=LLMProviderConfig(
                api_key=tp.get("api_key", ""),
                base_url=tp.get("base_url", ""),
                model=tp.get("model", ""),
            ),
            speaking_provider=LLMProviderConfig(
                api_key=sp.get("api_key", ""),
                base_url=sp.get("base_url", ""),
                model=sp.get("model", ""),
            ),
            anthropic_max_tokens=r.get("anthropic", {}).get("max_tokens", 1024),
            api_timeout=r.get("api_timeout", 120.0),
        )

    def _build_server(self) -> ServerConfig:
        r = self._raw.get("server", {})
        sse = r.get("sse", {})
        return ServerConfig(
            host=r.get("host", "0.0.0.0"),
            port=r.get("port", 8000),
            log_level=r.get("log_level", "info"),
            reload=r.get("reload", True),
            sse_heartbeat_timeout=sse.get("heartbeat_timeout", 1.0),
        )

    def _build_memory(self) -> MemoryConfig:
        r = self._raw.get("memory", {})
        pt = r.get("provider_timeout", {})
        st = r.get("stm_timeout", {})
        prof = r.get("profile", {})
        return MemoryConfig(
            service_url=r.get("service_url", "http://localhost:8001"),
            provider_connect_timeout=pt.get("connect", 5.0),
            provider_read_timeout=pt.get("read", 60.0),
            provider_write_timeout=pt.get("write", 10.0),
            provider_pool_timeout=pt.get("pool", 10.0),
            stm_connect_timeout=st.get("connect", 3.0),
            stm_read_timeout=st.get("read", 10.0),
            stm_write_timeout=st.get("write", 5.0),
            stm_pool_timeout=st.get("pool", 5.0),
            profile_ensure_url=prof.get("ensure_url", ""),
            profile_ensure_timeout=prof.get("ensure_timeout", 5.0),
            profile_turn_threshold=prof.get("turn_threshold", 10),
        )

    def _build_brain(self, memory_service_url: str = "") -> BrainConfig:
        r = self._raw.get("brain", {})
        interim = r.get("interim", {})
        sa = r.get("state_api", {})
        ctx = r.get("context", {})
        pro = r.get("proactive", {})
        msg = r.get("message", {})
        stm = r.get("stm_importance", {})
        default_state_url = f"{memory_service_url}/api/state" if memory_service_url else "http://localhost:8001/api/state"
        return BrainConfig(
            max_iterations=r.get("max_iterations", 5),
            fast_tools=r.get("fast_tools", ["get_time", "get_context"]),
            interim_messages=r.get("interim_messages", list(_DEFAULT_INTERIM_MESSAGES)),
            interim_max_length=interim.get("max_length", 50),
            state_api_url=sa.get("url", default_state_url),
            state_api_timeout=sa.get("timeout", 3.0),
            context_limit=ctx.get("limit", 20),
            context_time_window=ctx.get("time_window", 60),
            gap_threshold=ctx.get("gap_threshold", 600),
            proactive_context_limit=pro.get("context_limit", 10),
            proactive_context_time_window=pro.get("context_time_window", 0.5),
            proactive_speak_cooldown=pro.get("speak_cooldown", 120),
            proactive_speak_max_per_hour=pro.get("speak_max_per_hour", 3),
            mention_priority=msg.get("mention_priority", 10),
            significant_length=msg.get("significant_length", 20),
            stm_importance_user_mention=stm.get("user_mention", 0.7),
            stm_importance_significant_msg=stm.get("significant_msg", 0.4),
            stm_importance_private_chat=stm.get("private_chat", 0.8),
        )

    def _build_sleep(self) -> SleepConfig:
        r = self._raw.get("sleep", {})
        en = r.get("energy", {})
        return SleepConfig(
            enabled=r.get("enabled", False),
            wind_down_hour=r.get("wind_down_hour", 23),
            sleep_hour=r.get("sleep_hour", 0),
            wake_hour=r.get("wake_hour", 8),
            awake_energy_value=en.get("awake_value", 0.8),
            awake_energy_label=en.get("awake_label", "充沛"),
            tired_energy_value=en.get("tired_value", 0.3),
            tired_energy_label=en.get("tired_label", "困倦"),
            check_interval=r.get("check_interval", 60),
        )

    def _build_napcat(self) -> NapCatConfig:
        r = self._raw.get("napcat", {})
        return NapCatConfig(
            http_url=r.get("http_url", "http://localhost:3000"),
            timeout=r.get("timeout", 30.0),
        )

    def _build_admin(self) -> AdminConfig:
        r = self._raw.get("admin", {})
        ntf = r.get("notification", {})
        return AdminConfig(
            qq_id=str(r.get("qq_id", "") or "").strip(),
            cooldown_seconds=ntf.get("cooldown_seconds", 60),
        )

    def _build_vision(self) -> VisionConfig:
        r = self._raw.get("vision", {})
        img = r.get("image_download", {})
        return VisionConfig(
            enabled=r.get("enabled", True),
            provider=r.get("provider", "qwen"),
            model=r.get("model", "qwen-vl-max"),
            api_key=r.get("api_key", ""),
            base_url=r.get("base_url", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
            max_retries=r.get("max_retries", 3),
            timeout=r.get("timeout", 30),
            image_download_timeout=img.get("timeout", 15.0),
        )

    def _build_context(self) -> ContextConfig:
        r = self._raw.get("context", {})
        gc = r.get("group_context", {})
        mr = r.get("memory_recall", {})
        return ContextConfig(
            group_context_limit=gc.get("limit", 50),
            group_context_time_window=gc.get("time_window", 30),
            memory_recall_limit=mr.get("limit", 5),
        )


def load_settings(config_dir: Optional[str] = None) -> Settings:
    return ConfigLoader(config_dir).load()


settings: Settings = load_settings()
