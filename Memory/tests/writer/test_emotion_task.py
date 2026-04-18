"""情感快照分析任务测试。"""

import pytest
from unittest.mock import Mock
from Memory.writer.tasks.emotion_task import analyze_emotion_and_check_state, EmotionSnapshot


class TestEmotionAnalysis:
    """情感分析功能测试。"""

    def test_analyze_emotion_success(
        self, sample_experience_id, sample_raw_text, mock_llm_client, temp_db_dir
    ):
        """测试成功分析情感。"""
        # 准备
        experience_store = Mock()
        experience_store.get.return_value = Mock()
        experience_store.update.return_value = True

        # 执行
        emotion = analyze_emotion_and_check_state(
            experience_id=sample_experience_id,
            raw_text=sample_raw_text,
            state_focus=None,
            state_mood_label="平静",
            llm_client=mock_llm_client,
            experience_store=experience_store,
        )

        # 验证
        assert isinstance(emotion, EmotionSnapshot)
        assert emotion.category == "joy"
        assert emotion.intensity == 0.8
        assert emotion.valence == 0.7
        assert emotion.arousal == 0.6
        assert emotion.target == "爬山"

    def test_analyze_emotion_store_to_database(
        self, sample_experience_id, sample_raw_text, mock_llm_client, temp_db_dir
    ):
        """测试情感快照存储到数据库。"""
        # 准备
        experience = Mock()
        experience_store = Mock()
        experience_store.get.return_value = experience
        experience_store.update.return_value = True

        # 执行
        analyze_emotion_and_check_state(
            experience_id=sample_experience_id,
            raw_text=sample_raw_text,
            state_focus=None,
            state_mood_label="平静",
            llm_client=mock_llm_client,
            experience_store=experience_store,
        )

        # 验证：情感字段正确设置
        assert experience.emotion_category == "joy"
        assert experience.emotion_intensity == 0.8
        assert experience.emotion_valence == 0.7
        assert experience.emotion_arousal == 0.6
        assert experience.emotion_target == "爬山"
        assert experience_store.update.called
