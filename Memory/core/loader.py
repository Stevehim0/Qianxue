"""核心层加载器模块。

DEPRECATED: 本模块已废弃。核心层数据现通过 Backend HTTP API (GET /api/core/identity) 获取。
参见 Memory/api/memory_api.py load_core()。

本模块提供核心层人设的加载功能，从identity.md文件读取AI的人格DNA。
"""

import logging
from pathlib import Path
from typing import Optional

from Memory.core.models import Identity
from Memory.core.parser import IdentityParser

logger = logging.getLogger(__name__)


class IdentityLoader:
    """核心层人设加载器。

    从identity.md文件加载核心层人设文本。

    Examples:
        >>> loader = IdentityLoader()
        >>> identity = loader.load()
        >>> print(identity.invariant_text)
    """

    DEFAULT_IDENTITY_PATH = Path(__file__).parent.parent / "core_text" / "identity.md"

    def __init__(self, identity_path: Optional[Path] = None):
        """初始化加载器。

        Args:
            identity_path: 人设文件路径，None则使用默认路径
        """
        self.identity_path = identity_path or self.DEFAULT_IDENTITY_PATH

    def load(self) -> Identity:
        """加载核心层人设。

        Returns:
            Identity对象，包含三层结构文本和锚点

        Raises:
            FileNotFoundError: 人设文件不存在
            ValueError: 文件格式错误或文件为空
        """
        if not self.identity_path.exists():
            raise FileNotFoundError(f"核心层人设文件不存在: {self.identity_path}")

        # 检查文件是否为空
        content = self.identity_path.read_text(encoding="utf-8")
        if not content.strip():
            raise ValueError(f"人设文件为空: {self.identity_path}")

        # 使用parser解析文件
        parser = IdentityParser()
        identity = parser.parse_file(self.identity_path)

        logger.info(f"Loaded core identity from {self.identity_path}")

        return identity


def load_identity(identity_path: Optional[Path] = None) -> Identity:
    """便捷函数：加载核心层人设。

    Args:
        identity_path: 人设文件路径，None则使用默认路径

    Returns:
        Identity对象
    """
    loader = IdentityLoader(identity_path)
    return loader.load()
