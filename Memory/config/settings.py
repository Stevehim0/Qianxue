"""记忆系统的全局配置模块。

本模块使用 dataclasses 提供集中化的配置管理。
配置可以从环境变量加载，并提供类型安全的访问方式。
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# 包根目录（Memory/）
_PACKAGE_DIR = Path(__file__).parent.parent

# 从 Memory 目录下的 .env 文件加载环境变量
_dotenv_path = _PACKAGE_DIR / ".env"
load_dotenv(_dotenv_path)


@dataclass
class DatabaseConfig:
    """数据库配置。"""

    db_path: Path = _PACKAGE_DIR / "data" / "memory.db"  # SQLite 数据库文件路径
    chroma_persist_dir: Path = _PACKAGE_DIR / "data" / "chroma"  # ChromaDB 持久化目录


@dataclass
class ModelsConfig:
    """模型配置。"""

    embedding_model: str = "BAAI/bge-base-zh"  # Embedding 模型名称
    llm_provider: str = field(
        default_factory=lambda: os.getenv("LLM_PROVIDER", "qianwen")
    )  # LLM 提供商（qianwen/deepseek/openai_compatible）
    llm_api_key: Optional[str] = field(
        default_factory=lambda: os.getenv("LLM_API_KEY")
    )  # LLM API 密钥
    llm_base_url: Optional[str] = field(
        default_factory=lambda: os.getenv("LLM_BASE_URL")
    )  # LLM API 基础 URL
    llm_model: Optional[str] = field(
        default_factory=lambda: os.getenv("LLM_MODEL")
    )  # LLM 模型名称（openai_compatible 时使用）
    allow_mock_models: bool = field(
        default_factory=lambda: os.getenv("ALLOW_MOCK_MODELS", "false").lower() == "true"
    )  # 是否允许使用Mock模型（仅用于测试，默认false）


@dataclass
class DecayConfig:
    """记忆衰减参数配置。"""

    lambda_L0: float = 0.1  # L0 记忆的衰减率（每小时）
    lambda_L3: float = 0.01  # L3 记忆的衰减率（每小时）
    alpha: float = 0.5  # 情感影响因子
    beta: float = 0.8  # 重复增强因子


@dataclass
class ScheduleConfig:
    """作息时间配置。"""

    enabled: bool = False  # 是否启用巩固和休眠调度
    sleep_time: str = "02:00"  # 入睡时间
    wake_time: str = "08:00"  # 起床时间
    timezone: str = "Asia/Shanghai"  # 时区


@dataclass
class RecallConfig:
    """召回系统配置。"""

    default_top_k: int = 10  # 默认召回的 top-k 数量
    similarity_threshold: float = 0.7  # 相似度阈值
    max_hop_depth: int = 3  # 激活扩散的最大跳数


@dataclass
class WriterConfig:
    """写入层配置。

    Attributes:
        entity_similarity_threshold: 实体识别预筛相似度阈值（0-1）
        - 阈值越高，预筛越严格，进入prompt的实体越少
        - 阈值越低，预筛越宽松，进入prompt的实体越多
        - 第一版默认值0.5，后续可根据实际数据调整
    """

    entity_similarity_threshold: float = 0.5

    def __post_init__(self):
        """配置验证。"""
        if not 0 <= self.entity_similarity_threshold <= 1:
            raise ValueError(
                f"entity_similarity_threshold must be between 0 and 1, "
                f"got {self.entity_similarity_threshold}"
            )


@dataclass
class ConsolidationConfig:
    """巩固层配置。

    Attributes:
        batch_size: 每批最多处理节点数
        max_workers: ThreadPoolExecutor工作线程数，None使用默认
        similarity_threshold: 隐性边发现相似度阈值（0-1）
        min_importance_for_l1l2: L1/L2提取最小重要度（0-1]
        property_upgrade_threshold: 属性升级最小共享次数
        dormancy_threshold: 休眠阈值，边权重低于此值标记为休眠（0-1）
    """

    batch_size: int = 20
    max_workers: Optional[int] = None
    similarity_threshold: float = 0.7
    min_importance_for_l1l2: float = 0.5
    property_upgrade_threshold: int = 5
    dormancy_threshold: float = 0.05

    def __post_init__(self):
        """配置验证。"""
        if not 0 <= self.similarity_threshold <= 1:
            raise ValueError(
                f"similarity_threshold must be between 0 and 1, " f"got {self.similarity_threshold}"
            )
        if not 0 < self.min_importance_for_l1l2 <= 1:
            raise ValueError(
                f"min_importance_for_l1l2 must be between 0 (exclusive) and 1 (inclusive), "
                f"got {self.min_importance_for_l1l2}"
            )
        if self.property_upgrade_threshold < 1:
            raise ValueError(
                f"property_upgrade_threshold must be >= 1, "
                f"got {self.property_upgrade_threshold}"
            )
        if not 0 <= self.dormancy_threshold <= 1:
            raise ValueError(
                f"dormancy_threshold must be between 0 and 1, " f"got {self.dormancy_threshold}"
            )


@dataclass
class DreamConfig:
    """梦境模块配置

    Attributes:
        reorganize_batch_size: 记忆重组任务批量大小（D-03）
        emotion_batch_size: 情感加工任务批量大小（D-03）
        distort_batch_size: 记忆扭曲任务批量大小（D-03）
        simulate_batch_size: 模拟推演任务批量大小（D-03）
        important_ratio: 重要记忆比例（D-02: 40%）
        random_ratio: 随机记忆比例（D-02: 60%）
        task_timeout_seconds: 任务级超时（D-08: 30分钟）
        memory_timeout_seconds: 单个记忆超时（D-14: 5分钟）
        dream_confidence: 梦境节点置信度（D-09: 0.3）
        dream_importance_multiplier: 梦境节点重要性系数（D-09: 0.5）
        allow_l3_modification: L3永远不可改（D-15: False）
        audit_log_path: 审计日志路径（D-20）
    """

    # 每个任务处理的记忆数量 (D-03)
    reorganize_batch_size: int = 20
    emotion_batch_size: int = 20
    distort_batch_size: int = 20
    simulate_batch_size: int = 20

    # 分层采样比例 (D-02)
    important_ratio: float = 0.4  # 重要记忆比例 (40%)
    random_ratio: float = 0.6  # 随机记忆比例 (60%)

    # 超时控制 (D-08, D-14)
    task_timeout_seconds: int = 1800  # 任务级超时 (30分钟)
    memory_timeout_seconds: int = 300  # 单个记忆超时 (5分钟)

    # 梦境节点标记 (D-09)
    dream_confidence: float = 0.3  # 梦境节点置信度
    dream_importance_multiplier: float = 0.5  # 梦境节点重要性系数

    # 扭曲保护 (D-15)
    allow_l3_modification: bool = False  # L3永远不可改 (铁律)

    # 日志配置 (D-20)
    audit_log_path: str = str(_PACKAGE_DIR / "logs" / "dream_audit.log")

    # 可塑层演化配置
    backend_url: str = "http://localhost:8000"  # 主系统地址（用于获取/更新核心层）

    def __post_init__(self):
        """验证配置参数"""
        # 批量大小必须 > 0
        for field in [
            "reorganize_batch_size",
            "emotion_batch_size",
            "distort_batch_size",
            "simulate_batch_size",
        ]:
            value = getattr(self, field)
            if value <= 0:
                raise ValueError(f"{field} must be > 0, got {value}")

        # 采样比例总和必须为 1.0
        if not abs(self.important_ratio + self.random_ratio - 1.0) < 0.01:
            raise ValueError(
                f"Sampling ratios must sum to 1.0, "
                f"got {self.important_ratio + self.random_ratio}"
            )

        # 超时必须 >= 60秒
        if self.task_timeout_seconds < 60:
            raise ValueError(f"task_timeout_seconds must be >= 60, got {self.task_timeout_seconds}")
        if self.memory_timeout_seconds < 60:
            raise ValueError(
                f"memory_timeout_seconds must be >= 60, got {self.memory_timeout_seconds}"
            )

        # 置信度和重要性系数范围 [0, 1]
        if not 0 <= self.dream_confidence <= 1:
            raise ValueError(
                f"dream_confidence must be between 0 and 1, got {self.dream_confidence}"
            )
        if not 0 <= self.dream_importance_multiplier <= 1:
            raise ValueError(
                f"dream_importance_multiplier must be between 0 and 1, "
                f"got {self.dream_importance_multiplier}"
            )


@dataclass
class StmConfig:
    """短期记忆（Short-Term Memory）配置。

    管理跨会话全局感知的事件记录、压缩和清理。
    """

    retention_hours: float = 6.0           # 事件保留时长（小时）
    compression_threshold: int = 40        # 触发压缩的事件数阈值
    compression_batch_size: int = 20       # 每批压缩的事件数
    max_perception_events: int = 30        # 感知区块最大事件数
    cleanup_interval_minutes: float = 30.0 # 清理间隔（分钟）


@dataclass
class BufferConfig:
    """缓冲写入配置。

    Attributes:
        initial_threshold: 首次触发话题判断的消息数（默认30）
        threshold_step: 每次未找到边界后增加的步长（默认30）
        max_threshold: 最大阈值上限（默认150）
        timeout_minutes: 无新消息时强制写入的超时时间（分钟，默认10）
        check_interval_seconds: 后台超时检查器的轮询间隔（秒，默认30）
    """

    initial_threshold: int = 30
    threshold_step: int = 30
    max_threshold: int = 150
    timeout_minutes: float = 10.0
    check_interval_seconds: float = 30.0

    def __post_init__(self):
        if self.initial_threshold < 5:
            raise ValueError(f"initial_threshold must be >= 5, got {self.initial_threshold}")
        if self.threshold_step < 5:
            raise ValueError(f"threshold_step must be >= 5, got {self.threshold_step}")
        if self.timeout_minutes < 0.5:
            raise ValueError(f"timeout_minutes must be >= 0.5, got {self.timeout_minutes}")


@dataclass
class Settings:
    """全局设置容器。

    Attributes:
        database: 数据库配置
        models: 模型配置
        decay: 衰减参数配置
        schedule: 作息时间配置
        recall: 召回系统配置
        writer: 写入层配置
        consolidation: 巩固层配置
        dream: 梦境模块配置
        buffer: 缓冲写入配置
    """

    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    models: ModelsConfig = field(default_factory=ModelsConfig)
    decay: DecayConfig = field(default_factory=DecayConfig)
    schedule: ScheduleConfig = field(default_factory=ScheduleConfig)
    recall: RecallConfig = field(default_factory=RecallConfig)
    writer: WriterConfig = field(default_factory=WriterConfig)
    consolidation: ConsolidationConfig = field(default_factory=ConsolidationConfig)
    dream: DreamConfig = field(default_factory=DreamConfig)
    buffer: BufferConfig = field(default_factory=BufferConfig)
    stm: StmConfig = field(default_factory=StmConfig)

    def get_summary(self) -> dict:
        """获取所有设置的摘要。

        Returns:
            包含所有配置值的字典
        """
        return {
            "database": {
                "db_path": str(self.database.db_path),
                "chroma_persist_dir": str(self.database.chroma_persist_dir),
            },
            "models": {
                "embedding_model": self.models.embedding_model,
                "llm_provider": self.models.llm_provider,
                "llm_api_key": "***" if self.models.llm_api_key else None,
                "llm_base_url": self.models.llm_base_url,
                "llm_model": self.models.llm_model,
            },
            "decay": {
                "lambda_L0": self.decay.lambda_L0,
                "lambda_L3": self.decay.lambda_L3,
                "alpha": self.decay.alpha,
                "beta": self.decay.beta,
            },
            "schedule": {
                "enabled": self.schedule.enabled,
                "sleep_time": self.schedule.sleep_time,
                "wake_time": self.schedule.wake_time,
                "timezone": self.schedule.timezone,
            },
            "recall": {
                "default_top_k": self.recall.default_top_k,
                "similarity_threshold": self.recall.similarity_threshold,
                "max_hop_depth": self.recall.max_hop_depth,
            },
            "writer": {
                "entity_similarity_threshold": self.writer.entity_similarity_threshold,
            },
            "consolidation": {
                "batch_size": self.consolidation.batch_size,
                "max_workers": self.consolidation.max_workers,
                "similarity_threshold": self.consolidation.similarity_threshold,
                "min_importance_for_l1l2": self.consolidation.min_importance_for_l1l2,
                "property_upgrade_threshold": self.consolidation.property_upgrade_threshold,
                "dormancy_threshold": self.consolidation.dormancy_threshold,
            },
            "dream": {
                "reorganize_batch_size": self.dream.reorganize_batch_size,
                "emotion_batch_size": self.dream.emotion_batch_size,
                "distort_batch_size": self.dream.distort_batch_size,
                "simulate_batch_size": self.dream.simulate_batch_size,
                "important_ratio": self.dream.important_ratio,
                "random_ratio": self.dream.random_ratio,
                "task_timeout_seconds": self.dream.task_timeout_seconds,
                "memory_timeout_seconds": self.dream.memory_timeout_seconds,
                "dream_confidence": self.dream.dream_confidence,
                "dream_importance_multiplier": self.dream.dream_importance_multiplier,
                "allow_l3_modification": self.dream.allow_l3_modification,
                "audit_log_path": self.dream.audit_log_path,
            },
            "buffer": {
                "initial_threshold": self.buffer.initial_threshold,
                "threshold_step": self.buffer.threshold_step,
                "max_threshold": self.buffer.max_threshold,
                "timeout_minutes": self.buffer.timeout_minutes,
                "check_interval_seconds": self.buffer.check_interval_seconds,
            },
            "stm": {
                "retention_hours": self.stm.retention_hours,
                "compression_threshold": self.stm.compression_threshold,
                "compression_batch_size": self.stm.compression_batch_size,
                "max_perception_events": self.stm.max_perception_events,
                "cleanup_interval_minutes": self.stm.cleanup_interval_minutes,
            },
        }


# 全局设置实例
settings = Settings()
