"""核心层解析器模块。

DEPRECATED: 本模块已废弃。核心层数据现通过 Backend HTTP API (GET /api/core/identity) 获取。
参见 Memory/api/memory_api.py load_core()。

本模块提供核心层人设的解析功能，解析identity.md文件的三层结构和锚点。
"""

import logging
import re
from pathlib import Path
from typing import Dict, List, Optional

from Memory.core.models import Identity

logger = logging.getLogger(__name__)


class IdentityParser:
    """核心层人设解析器。

    解析identity.md文件，提取三层结构和锚点。

    Examples:
        >>> parser = IdentityParser()
        >>> identity = parser.parse_file(Path("identity.md"))
        >>> print(identity.invariant_text)
    """

    # Markdown section正则表达式
    SECTION_PATTERN = r"^##\s+([^\n]+)\n+(.*?)(?=^##|\Z)"

    def __init__(self):
        """初始化解析器。"""
        self.logger = logging.getLogger(__name__)

    def parse_file(self, file_path: Path) -> Identity:
        """解析identity.md文件。

        Args:
            file_path: 人设文件路径

        Returns:
            Identity对象，包含解析后的三层和锚点

        Raises:
            FileNotFoundError: 文件不存在
            ValueError: 文件格式错误
        """
        if not file_path.exists():
            raise FileNotFoundError(f"人设文件不存在: {file_path}")

        # 读取文件内容
        content = file_path.read_text(encoding="utf-8")

        # 解析文本
        return self.parse_text(content, source_path=file_path)

    def parse_text(self, content: str, source_path: Optional[Path] = None) -> Identity:
        """解析人设文本内容。

        Args:
            content: identity.md文件内容
            source_path: 文件路径（用于追踪）

        Returns:
            Identity对象

        Raises:
            ValueError: 解析失败
        """
        # 提取所有section
        sections = self._extract_sections(content)

        # 解析三层结构
        layers = self._parse_three_layers(sections)

        # 提取锚点（传入完整内容以处理子标题）
        anchors = self._extract_anchors(sections, full_content=content)

        # 创建Identity对象
        identity = Identity(
            invariant_text=layers["invariant"],
            stable_text=layers["stable"],
            plastic_text=layers["malleable"],
            anchors=anchors,
            raw_text=content,
            source_path=source_path,
        )

        self.logger.info(f"Parsed core identity from {source_path or 'text'}")
        return identity

    def _extract_sections(self, content: str) -> Dict[str, str]:
        """提取markdown所有section。

        Args:
            content: markdown文本

        Returns:
            {标题: 内容}字典
        """
        sections = {}
        for match in re.finditer(self.SECTION_PATTERN, content, re.MULTILINE | re.DOTALL):
            title = match.group(1).strip()
            section_content = match.group(2).strip()
            sections[title] = section_content

        return sections

    def _parse_three_layers(self, sections: Dict[str, str]) -> Dict[str, str]:
        """解析三层同心圆结构。

        Args:
            sections: section字典

        Returns:
            {invariant, stable, malleable}字典
        """
        # 定义可能的标题变体
        invariant_keywords = ["不变层", "不变", "Immutable", "底线"]
        stable_keywords = ["稳定层", "稳定", "Stable", "性格"]
        malleable_keywords = ["可塑层", "可塑", "Malleable", "风格"]

        # 查找匹配的section
        invariant_text = self._find_section_by_keywords(sections, invariant_keywords)
        stable_text = self._find_section_by_keywords(sections, stable_keywords)
        malleable_text = self._find_section_by_keywords(sections, malleable_keywords)

        return {
            "invariant": invariant_text or "",
            "stable": stable_text or "",
            "malleable": malleable_text or "",
        }

    def _find_section_by_keywords(
        self, sections: Dict[str, str], keywords: List[str]
    ) -> Optional[str]:
        """根据关键词查找section。

        Args:
            sections: section字典
            keywords: 关键词列表

        Returns:
            匹配的section内容，None表示未找到
        """
        for title, content in sections.items():
            for keyword in keywords:
                if keyword in title:
                    return content
        return None

    def _extract_anchors(
        self, sections: Dict[str, str], full_content: str = None
    ) -> Dict[str, List[str]]:
        """提取结构化锚点。

        Args:
            sections: section字典
            full_content: 完整的markdown内容（用于直接搜索锚点部分）

        Returns:
            {
                "bottom_lines": [...],
                "style_keywords": [...],
                "values_priority": [...]
            }
        """
        anchors = {"bottom_lines": [], "style_keywords": [], "values_priority": []}

        # 如果提供了完整内容，直接从完整内容中提取锚点部分
        # 这样可以处理锚点section内容为空的情况（因为有子标题###）
        anchor_text = None

        if full_content:
            # 查找"## 锚点"到文件结尾之间的所有内容
            # 使用 (锚点|Anchors) 匹配完整的词，而不是字符类
            # 使用 (?<!#) 负向回顾断言确保只匹配两个#，而不是三个#
            anchor_pattern = r"##[^#]*(?:锚点|Anchors)[^#]*\n+([\s\S]*)"
            anchor_match = re.search(anchor_pattern, full_content, re.MULTILINE | re.DOTALL)
            if anchor_match:
                anchor_text = anchor_match.group(1)
        else:
            # 旧逻辑：从section字典中查找
            for title, content in sections.items():
                if "锚点" in title or "Anchor" in title:
                    anchor_text = content
                    break

        if not anchor_text:
            self.logger.warning("未找到锚点section，返回空锚点")
            return anchors

        # 解析锚点内容（包括子标题###）
        current_anchor_type = None

        for line in anchor_text.split("\n"):
            line = line.strip()

            # 跳过空行
            if not line:
                continue

            # 检测子标题锚点类型（如"### 底线"）
            if line.startswith("###"):
                if "底线" in line or "Bottom" in line:
                    current_anchor_type = "bottom_lines"
                elif "风格关键词" in line or "Style" in line:
                    current_anchor_type = "style_keywords"
                elif "价值排序" in line or "Values" in line:
                    current_anchor_type = "values_priority"
                continue

            # 提取列表项（去除序号和符号）
            if current_anchor_type and line:
                # 跳过分隔线和注释
                if line.startswith("---") or line.startswith("*"):
                    continue

                # 去除 "- "、"* "、"1. "等前缀
                # 注意："- "后面不一定有点号，所以要分别处理
                cleaned = re.sub(r"^[\-\*]\s+", "", line)  # 处理 "- " 或 "* "
                cleaned = re.sub(r"^\d+\.\s*", "", cleaned)  # 处理 "1. "
                if cleaned and not cleaned.startswith("#"):  # 确保不是标题
                    anchors[current_anchor_type].append(cleaned)

        return anchors


def parse_three_layers(text: str) -> Dict[str, str]:
    """便捷函数：解析三层结构。

    Args:
        text: identity.md内容

    Returns:
        {invariant, stable, malleable}字典
    """
    parser = IdentityParser()
    sections = parser._extract_sections(text)
    return parser._parse_three_layers(sections)


def extract_anchors(text: str) -> Dict[str, List[str]]:
    """便捷函数：提取锚点。

    Args:
        text: identity.md内容

    Returns:
        锚点字典
    """
    parser = IdentityParser()
    sections = parser._extract_sections(text)
    return parser._extract_anchors(sections, full_content=text)
