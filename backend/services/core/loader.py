"""核心层加载器 - 加载、解析、重载 identity.md。"""

import logging
import re
from pathlib import Path
from typing import Optional

import yaml

from backend.services.core.models import Identity

logger = logging.getLogger(__name__)

DEFAULT_IDENTITY_PATH = Path(__file__).parent / "identity.md"


class IdentityLoader:
    """加载和解析 identity.md 人设文件。

    支持三层结构解析和可塑层 YAML 提取。
    提供 reload() 方法供梦境更新后重载。
    """

    def __init__(self, identity_path: Optional[Path] = None):
        self.identity_path = identity_path or DEFAULT_IDENTITY_PATH
        self._identity: Optional[Identity] = None

    @property
    def identity(self) -> Identity:
        """获取当前加载的身份，未加载则自动加载。"""
        if self._identity is None:
            self._identity = self.load()
        return self._identity

    def load(self) -> Identity:
        """加载核心层人设文件。

        Returns:
            Identity对象

        Raises:
            FileNotFoundError: 文件不存在
            ValueError: 文件格式错误
        """
        if not self.identity_path.exists():
            raise FileNotFoundError(f"人设文件不存在: {self.identity_path}")

        content = self.identity_path.read_text(encoding="utf-8")
        if not content.strip():
            raise ValueError(f"人设文件为空: {self.identity_path}")

        identity = self._parse(content)
        self._identity = identity
        logger.info(f"核心层加载完成: {self.identity_path}")
        return identity

    def reload(self) -> Identity:
        """重新加载人设文件（梦境更新后调用）。"""
        logger.info("重新加载核心层...")
        return self.load()

    def update_malleable(self, new_yaml: str) -> Identity:
        """更新可塑层 YAML 并写回文件。

        Args:
            new_yaml: 新的可塑层 YAML 文本

        Returns:
            更新后的 Identity
        """
        content = self.identity_path.read_text(encoding="utf-8")

        # 替换 MALLEABLE_START 和 MALLEABLE_END 之间的内容
        pattern = r"(<!-- MALLEABLE_START -->\n```yaml\n)(.*?)(```\s*\n?<!-- MALLEABLE_END -->)"
        replacement = rf"\g<1>{new_yaml}\n\g<3>"

        new_content, count = re.subn(pattern, replacement, content, flags=re.DOTALL)

        if count == 0:
            logger.error("未找到可塑层标记，无法更新")
            raise ValueError("identity.md 中未找到 MALLEABLE_START/END 标记")

        self.identity_path.write_text(new_content, encoding="utf-8")
        logger.info("可塑层已更新并写入文件")

        return self.reload()

    def _parse(self, content: str) -> Identity:
        """解析 identity.md 内容。

        提取三层结构和可塑层 YAML。
        """
        sections = self._extract_sections(content)

        invariant_text = self._find_section(
            sections, ["不变层", "不变", "Immutable"]
        )
        stable_text = self._find_section(
            sections, ["稳定层", "稳定", "Stable"]
        )

        # 提取可塑层 YAML
        malleable_yaml = self._extract_malleable_yaml(content)
        malleable_data = self._parse_yaml(malleable_yaml)

        return Identity(
            invariant_text=invariant_text or "",
            stable_text=stable_text or "",
            malleable_yaml=malleable_yaml,
            malleable_data=malleable_data,
            raw_text=content,
            source_path=self.identity_path,
        )

    def _extract_sections(self, content: str) -> dict:
        """提取所有 ## 标题的 section。"""
        sections = {}
        pattern = r"^##\s+([^\n]+)\n+(.*?)(?=^##|\Z)"
        for match in re.finditer(pattern, content, re.MULTILINE | re.DOTALL):
            title = match.group(1).strip()
            section_content = match.group(2).strip()
            # 排除可塑层（单独处理）
            if any(kw in title for kw in ["可塑", "Malleable"]):
                continue
            sections[title] = section_content
        return sections

    def _find_section(self, sections: dict, keywords: list) -> Optional[str]:
        """根据关键词查找 section。"""
        for title, content in sections.items():
            for keyword in keywords:
                if keyword in title:
                    return content
        return None

    def _extract_malleable_yaml(self, content: str) -> str:
        """提取 MALLEABLE_START/END 之间的 YAML 文本。"""
        pattern = r"<!-- MALLEABLE_START -->\n```yaml\n(.*?)```\s*\n?<!-- MALLEABLE_END -->"
        match = re.search(pattern, content, re.DOTALL)
        if match:
            return match.group(1).strip()
        return ""

    def _parse_yaml(self, yaml_text: str) -> Optional[dict]:
        """解析 YAML 文本。"""
        if not yaml_text:
            return None
        try:
            return yaml.safe_load(yaml_text)
        except yaml.YAMLError as e:
            logger.warning(f"可塑层 YAML 解析失败: {e}")
            return None


# 模块级单例
identity_loader = IdentityLoader()
