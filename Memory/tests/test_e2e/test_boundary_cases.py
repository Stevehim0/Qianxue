"""测试边界情况和错误处理。"""

import pytest
from Memory.api import MemoryAPI, InputError


class TestBoundaryCases:
    """测试边界情况。"""

    def test_empty_input(self, real_api: MemoryAPI):
        """测试空输入处理。"""
        # 空字符串应该抛出 InputError
        with pytest.raises(InputError):
            real_api.receive_event(role="user", content="")

        with pytest.raises(InputError):
            real_api.receive_event(role="", content="测试")

    def test_special_characters(self, real_api: MemoryAPI):
        """测试特殊字符处理。"""
        # Emoji
        exp_id = real_api.receive_event("user", "😊🎉🚀💻⭐")
        assert exp_id is not None

        # 键盘符号
        exp_id = real_api.receive_event("user", "!@#$%^&*()_+")
        assert exp_id is not None

        # 混合内容
        exp_id = real_api.receive_event("user", "测试😊!@#$%")
        assert exp_id is not None

    def test_duplicate_content(self, real_api: MemoryAPI):
        """测试重复内容处理。"""
        # 写入重复内容
        for i in range(3):
            real_api.receive_event("user", "测试测试测试测试")

        # 系统应该正常处理，不崩溃
        status = real_api.get_status()
        assert status["total_experiences"] >= 3

    def test_very_long_content(self, real_api: MemoryAPI):
        """测试超长内容处理。"""
        # 创建超长内容（1000个字符）
        long_content = "测试" * 500

        exp_id = real_api.receive_event("user", long_content)
        assert exp_id is not None

        # 验证能正常召回
        recalls = real_api.check_recall(query="测试", context={"recent_history": []})
        assert len(recalls) > 0
