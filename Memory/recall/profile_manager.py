"""个人档案管理器模块。

本模块提供ProfileManager类，管理人物实体的个人档案，
支持渐进创建、更新和加载。
"""

import json
import logging
from pathlib import Path
from typing import Optional, Dict, List
from datetime import datetime, timedelta

import requests

from Memory.storage.profile_store import ProfileStore
from Memory.storage.experience_store import ExperienceStore, Experience
from Memory.storage.entity_store import EntityStore, Entity
from Memory.recall.profile_data import InteractionStyle
from Memory.config.settings import settings

logger = logging.getLogger(__name__)


def _style_to_dict(style: InteractionStyle) -> Dict[str, float]:
    """将 InteractionStyle dataclass 转为字典。"""
    return {
        "warmth": style.warmth,
        "formality": style.formality,
        "humor": style.humor,
        "proactivity": style.proactivity,
        "directness": style.directness,
        "boundaries": style.boundaries,
    }


class ProfileManager:
    """个人档案管理器（RECALL-13）。

    管理人物实体的个人档案，支持渐进创建、更新、加载。
    内部统一使用 profile_store.PersonProfile（数据库模型），
    InteractionStyle 仅用于推导初始值和解析 LLM 响应。

    Attributes:
        profile_store: ProfileStore实例
        experience_store: ExperienceStore实例
        entity_store: EntityStore实例
        THRESHOLD_COUNT: 出现次数阈值（D-13）
        THRESHOLD_DAYS: 跨天数阈值（D-13）
    """

    THRESHOLD_COUNT = 3  # 出现次数阈值（D-13）
    THRESHOLD_DAYS = 3  # 跨天数阈值（D-13）

    def __init__(
        self,
        profile_store: ProfileStore,
        experience_store: ExperienceStore,
        entity_store: EntityStore,
    ):
        """初始化ProfileManager。

        Args:
            profile_store: ProfileStore实例
            experience_store: ExperienceStore实例
            entity_store: EntityStore实例
        """
        self.profile_store = profile_store
        self.experience_store = experience_store
        self.entity_store = entity_store

        logger.info("ProfileManager initialized")

    def check_and_create_profile(self, entity_name: str, experience: Experience):
        """检查是否应该创建档案（D-13）。

        该实体在experiences中出现≥3次且跨天数≥3天时创建。

        Args:
            entity_name: 实体名
            experience: 当前体验（用于设置初始相处方式）
        """
        # 1. 检查是否已存在
        existing = self.profile_store.get_by_name(entity_name)
        if existing:
            logger.debug(f"Profile already exists for {entity_name}")
            return False

        # 2. 检查阈值（D-13）
        stats = self.experience_store.get_entity_stats(entity_name)

        if (
            stats.get("count", 0) >= self.THRESHOLD_COUNT
            and stats.get("unique_days", 0) >= self.THRESHOLD_DAYS
        ):

            logger.info(f"Threshold met for {entity_name}, creating profile")

            # 3. 创建档案
            profile = self._create_profile(entity_name, experience)
            self.profile_store.create(profile)

            logger.info(f"Profile created for {entity_name}")
            return True
        else:
            logger.debug(
                f"Threshold not met for {entity_name}: "
                f"count={stats.get('count', 0)}, days={stats.get('unique_days', 0)}"
            )
            return False

    def _create_profile(self, entity_name: str, experience: Experience):
        """创建个人档案（D-15：初始相处方式根据上下文设置）。

        使用 profile_store.PersonProfile（数据库模型），interaction_style 为 Dict。
        """
        from Memory.storage.profile_store import PersonProfile as StoreProfile

        # 获取实体信息
        entity = self.entity_store.get_by_name(entity_name)
        if not entity:
            logger.warning(f"Entity {entity_name} not found")
            entity = Entity(id="unknown", name=entity_name, type="person")

        # 根据上下文设置初始相处方式（D-15），转为 Dict
        initial_style = self._derive_initial_style(experience)
        style_dict = _style_to_dict(initial_style)

        profile = StoreProfile(
            id=f"profile_{entity_name}",
            basic={
                "name": entity_name,
                "type": entity.type,
                "first_met": experience.created_at,
                "relation_to_self": (
                    entity.properties.get("relation_to_self", "unknown")
                    if entity.properties
                    else "unknown"
                ),
                "notes": f"自动创建于{datetime.now().isoformat()}",
            },
            interaction_style=style_dict,
            preferences={},
        )

        return profile

    def _derive_initial_style(self, experience: Experience) -> InteractionStyle:
        """根据上下文设置初始相处方式（D-15）"""
        # 基于情感类别和时段推导初始参数
        emotion = experience.emotion_category or "neutral"
        time_of_day = experience.context_time_of_day or "unknown"

        # 基础值（中性）
        style = InteractionStyle()

        # 根据情感调整（简化规则）
        if emotion in ["joy", "excitement", "satisfaction"]:
            style.warmth = 0.7  # 开心 → 热情
            style.humor = 0.6  # 开心 → 幽默
        elif emotion in ["sadness", "anger", "frustration"]:
            style.boundaries = 0.7  # 负面情感 → 保持距离
            style.formality = 0.6  # 负面情感 → 正式

        # 根据时段调整
        if time_of_day in ["凌晨", "深夜"]:
            style.formality = 0.4  # 深夜 → 随意
            style.directness = 0.6  # 深夜 → 直接

        return style

    def load_profile(self, entity_name: str) -> Optional[str]:
        """加载个人档案并返回prompt注入文本（RECALL-13）。

        Args:
            entity_name: 实体名

        Returns:
            prompt注入文本，如果档案不存在则返回None
        """
        profile = self.profile_store.get_by_name(entity_name)
        if not profile:
            logger.debug(f"No profile found for {entity_name}")
            return None

        # 格式化为prompt注入文本
        prompt_text = self._format_profile_prompt(profile)

        logger.debug(f"Loaded profile for {entity_name}")
        return prompt_text

    def _format_profile_prompt(self, profile) -> str:
        """格式化档案为prompt注入文本。

        Args:
            profile: profile_store.PersonProfile 对象（interaction_style 为 Dict）
        """
        style = profile.interaction_style or {}
        basic = profile.basic or {}

        text = f"""## 关于{basic.get('name', '未知')}

你们的关系: {basic.get('relation_to_self', '未知')}
初次见面: {basic.get('first_met', '未知')}

相处方式:
- 热情度: {style.get('warmth', 0.5):.1f}
- 正式度: {style.get('formality', 0.5):.1f}
- 幽默感: {style.get('humor', 0.5):.1f}
- 主动性: {style.get('proactivity', 0.5):.1f}
- 直接度: {style.get('directness', 0.5):.1f}
- 边界感: {style.get('boundaries', 0.5):.1f}
"""

        notes = basic.get("notes")
        if notes:
            text += f"\n备注: {notes}\n"

        return text

    def _load_identity(self) -> str:
        """获取AI核心价值观（D-04）。

        通过 HTTP 从 Backend 主系统获取核心层人设文本。

        Returns:
            核心层文本，如果获取失败返回空字符串
        """
        try:
            backend_url = settings.dream.backend_url
            resp = requests.get(f"{backend_url}/api/core/identity", timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                parts = []
                if data.get("stable_text"):
                    parts.append(data["stable_text"])
                if data.get("malleable_yaml"):
                    parts.append(data["malleable_yaml"])
                content = "\n\n".join(parts)
                logger.debug(f"Loaded identity from Backend ({len(content)} chars)")
                return content
            else:
                logger.warning(f"Backend returned {resp.status_code}")
                return ""
        except Exception as e:
            logger.warning(f"Failed to load identity from Backend: {e}")
            return ""

    def _query_conversation_history(self, entity_name: str, days: int = 7) -> List[Dict]:
        """查询最近N天的对话历史（D-03）。

        Args:
            entity_name: 实体名
            days: 查询天数（默认7天）

        Returns:
            对话历史列表，每个元素包含role, content, timestamp, emotion_category, intensity
        """
        from Memory.storage.database import db_manager

        # 计算时间范围（最近N天）
        cutoff_time = datetime.now() - timedelta(days=days)

        try:
            with db_manager.transaction() as cursor:
                cursor.execute(
                    """
                    SELECT
                        id, L3_raw, L0_text, created_at,
                        emotion_category, emotion_intensity
                    FROM experiences
                    WHERE created_at >= ?
                    AND (L3_raw LIKE ? OR L0_text LIKE ?)
                    ORDER BY created_at DESC
                    LIMIT 100
                    """,
                    (cutoff_time.isoformat(), f"%{entity_name}%", f"%{entity_name}%")
                )

                rows = cursor.fetchall()

                # 格式化为对话历史
                history = []
                for row in rows:
                    history.append({
                        "role": "user",  # 简化实现
                        "content": row["L3_raw"] or row["L0_text"],
                        "timestamp": row["created_at"],
                        "emotion_category": row["emotion_category"],
                        "intensity": row["emotion_intensity"] or 0.0,
                    })

                logger.debug(f"Found {len(history)} conversations for {entity_name} in last {days} days")
                return history

        except Exception as e:
            logger.error(f"Failed to query conversation history for {entity_name}: {e}")
            return []

    def _format_conversation_history(self, history: List[Dict]) -> str:
        """格式化对话历史为prompt注入文本。

        Args:
            history: 对话历史列表

        Returns:
            格式化的文本，用于注入prompt
        """
        formatted = []
        for item in history:
            formatted.append(
                f"- {item['role']}: {item['content']} "
                f"({item['timestamp']}, emotion={item['emotion_category']})"
            )
        return "\n".join(formatted)

    def _load_prompt_template(self) -> str:
        """读取profile_update.txt prompt模板。

        Returns:
            prompt模板内容

        Raises:
            FileNotFoundError: 如果prompt文件不存在
        """
        try:
            prompt_path = Path(__file__).parent.parent / "config" / "prompts" / "profile_update.txt"
            with open(prompt_path, "r", encoding="utf-8") as f:
                content = f.read()
                logger.debug(f"Loaded prompt template ({len(content)} chars)")
                return content
        except Exception as e:
            logger.error(f"Failed to load prompt template: {e}")
            raise  # prompt模板必须存在，抛出异常

    def update_profiles(self):
        """每次巩固都更新个人档案（D-14）。

        梦境AI在巩固阶段运行，分析对话历史并更新档案（PROFILE-04）。
        实现规则：
        - 收敛：用户明确反对时调整相应维度
        - 不迎合：用户表达喜欢时不加强
        - 可调整：情感持续负面时微调

        流程：
        1. 查询所有有档案的人物
        2. 对每个人物，查询最近7天对话历史
        3. 从 Backend HTTP 获取核心层人设
        4. 调用梦境AI分析并生成新相处方式
        5. 更新ProfileStore
        """
        from Memory.llm.factory import LLMFactory

        # 1. 查询所有有档案的人物
        all_profiles = self.profile_store.list_all()

        if not all_profiles:
            logger.info("No profiles to update")
            return

        # 2. 从 Backend HTTP 获取核心层人设（实现D-04）
        identity_text = self._load_identity()

        # 3. 创建LLM客户端
        llm_client = LLMFactory.create_client()

        for profile in all_profiles:
            basic = profile.basic or {}
            entity_name = basic.get("name")

            if not entity_name:
                logger.warning(f"Profile {profile.id} has no name, skipping")
                continue

            try:
                # 4. 查询最近7天对话历史（实现D-03）
                conversation_history = self._query_conversation_history(entity_name, days=7)

                if not conversation_history:
                    logger.debug(f"No conversation history for {entity_name}")
                    continue

                # 5. 读取prompt模板
                prompt_template = self._load_prompt_template()

                # 6. 构建输入数据（interaction_style 是 Dict）
                current_style = profile.interaction_style or {}
                input_data = {
                    "entity_name": entity_name,
                    "conversation_history": self._format_conversation_history(conversation_history),
                    "warmth": current_style.get("warmth", 0.5),
                    "formality": current_style.get("formality", 0.5),
                    "humor": current_style.get("humor", 0.5),
                    "proactivity": current_style.get("proactivity", 0.5),
                    "directness": current_style.get("directness", 0.5),
                    "boundaries": current_style.get("boundaries", 0.5),
                    "ai_core_identity": identity_text,
                }

                # 7. 调用梦境AI
                prompt = prompt_template.format(**input_data)
                response = llm_client.call(prompt=prompt, response_format="json")

                # 8. 解析响应 → Dict
                result = json.loads(response)
                new_style_dict = result["new_interaction_style"]

                # 9. 更新ProfileStore（使用 profile_id，传入 Dict）
                profile_id = f"profile_{entity_name}"
                self.profile_store.update_interaction_style(profile_id, new_style_dict)

                logger.info(
                    f"Profile updated for {entity_name}: {result.get('reasoning', '')[:100]}..."
                )

            except Exception as e:
                logger.error(f"Failed to update profile for {entity_name}: {e}")
                # 单个档案更新失败不影响其他档案

    def process_pending_facts(self, threshold: int = 20):
        """从 profile_pending_facts 表中积累的事实更新个人档案。

        当某个人的 pending facts 达到 threshold 条时，
        将其合并为一段文本追加到档案的 notes 中，然后删除已处理的 facts。

        Args:
            threshold: 触发更新的最小 fact 条数
        """
        from Memory.storage.database import db_manager
        from datetime import datetime

        try:
            with db_manager.transaction() as cursor:
                # 统计每个人的 fact 数量
                cursor.execute(
                    "SELECT entity_name, COUNT(*) as cnt FROM profile_pending_facts GROUP BY entity_name HAVING cnt >= ?",
                    (threshold,),
                )
                candidates = cursor.fetchall()

            for row in candidates:
                entity_name = row["entity_name"]
                try:
                    # 读取该人的所有 facts
                    with db_manager.transaction() as cursor:
                        cursor.execute(
                            "SELECT fact_text, created_at FROM profile_pending_facts WHERE entity_name = ? ORDER BY created_at",
                            (entity_name,),
                        )
                        facts = cursor.fetchall()

                    if not facts:
                        continue

                    # 合并 facts 为一段文本
                    combined = "; ".join(f["fact_text"] for f in facts)
                    now = datetime.now().isoformat()

                    # 更新档案
                    profile = self.profile_store.get_by_name(entity_name)
                    if profile:
                        basic = profile.basic or {}
                        existing_notes = basic.get("notes", "")
                        new_notes = f"{existing_notes}\n[{now}] {combined}" if existing_notes else f"[{now}] {combined}"
                        basic["notes"] = new_notes
                        profile.basic = basic
                        self.profile_store.update(profile)
                        logger.info(f"档案更新: {entity_name} 合并了 {len(facts)} 条事实")
                    else:
                        logger.debug(f"档案不存在: {entity_name}, 跳过更新")

                    # 删除已处理的 facts
                    with db_manager.transaction() as cursor:
                        cursor.execute(
                            "DELETE FROM profile_pending_facts WHERE entity_name = ?",
                            (entity_name,),
                        )

                except Exception as e:
                    logger.error(f"处理 {entity_name} 的 pending facts 失败: {e}")

        except Exception as e:
            logger.error(f"process_pending_facts 失败: {e}")
