"""Test dream prompt templates.

Tests for dream module prompt template validation:
- System prompt uses dream persona (not normal conversation)
- Task prompts have correct placeholders
- All prompts load successfully
- Prompts follow design document specifications
"""

import pytest
from pathlib import Path


class TestDreamPromptExports:
    """Test task module exports dream task functions."""

    def test_tasks_module_exports_all_four_dream_tasks(self):
        """Test 1: tasks module exports all four dream task functions."""
        from Memory.consolidator.tasks import (
            dream_reorganize,
            dream_emotion,
            dream_distort,
            dream_simulate,
        )

        # Verify all four functions are callable
        assert callable(dream_reorganize)
        assert callable(dream_emotion)
        assert callable(dream_distort)
        assert callable(dream_simulate)


class TestDreamSystemPrompt:
    """Test dream_system.txt uses specialized dream persona."""

    def test_dream_system_uses_dream_persona(self):
        """Test 2: dream_system.txt uses specialized dream persona (not normal conversation)."""
        from pathlib import Path

        prompts_dir = Path(__file__).parent.parent.parent / "config" / "prompts"
        system_prompt_path = prompts_dir / "dream_system.txt"

        assert system_prompt_path.exists(), "dream_system.txt must exist"

        content = system_prompt_path.read_text(encoding="utf-8")

        # Check it uses dream persona language
        assert (
            "梦境" in content or "dream" in content.lower()
        ), "System prompt must mention dream persona"
        assert (
            "不是正常对话" in content or "not normal conversation" in content.lower()
        ), "System prompt must differentiate from normal conversation"


class TestDreamReorganizePrompt:
    """Test dream_reorganize.txt has correct placeholders."""

    def test_reorganize_prompt_has_memory_placeholders(self):
        """Test 3: dream_reorganize.txt has {memory_a_L0}, {memory_a_L1}, {memory_b_L0}, {memory_b_L1} placeholders."""
        from pathlib import Path

        prompts_dir = Path(__file__).parent.parent.parent / "config" / "prompts"
        prompt_path = prompts_dir / "dream_reorganize.txt"

        assert prompt_path.exists(), "dream_reorganize.txt must exist"

        content = prompt_path.read_text(encoding="utf-8")

        # Check for required placeholders
        assert "{memory_a_L0}" in content, "Must have {memory_a_L0} placeholder"
        assert "{memory_a_L1}" in content, "Must have {memory_a_L1} placeholder"
        assert "{memory_b_L0}" in content, "Must have {memory_b_L0} placeholder"
        assert "{memory_b_L1}" in content, "Must have {memory_b_L1} placeholder"


class TestDreamEmotionPrompt:
    """Test dream_emotion.txt has correct placeholders."""

    def test_emotion_prompt_has_emotion_placeholders(self):
        """Test 4: dream_emotion.txt has {L0_summary}, {current_emotion}, {current_intensity} placeholders."""
        from pathlib import Path

        prompts_dir = Path(__file__).parent.parent.parent / "config" / "prompts"
        prompt_path = prompts_dir / "dream_emotion.txt"

        assert prompt_path.exists(), "dream_emotion.txt must exist"

        content = prompt_path.read_text(encoding="utf-8")

        # Check for required placeholders
        assert "{L0_summary}" in content, "Must have {L0_summary} placeholder"
        assert "{current_emotion}" in content, "Must have {current_emotion} placeholder"
        assert "{current_intensity}" in content, "Must have {current_intensity} placeholder"


class TestDreamDistortPrompt:
    """Test dream_distort.txt has distortion rules and placeholders."""

    def test_distort_prompt_has_rules_matrix_and_placeholders(self):
        """Test 5: dream_distort.txt has distortion rules matrix and {importance}, {time_distance_days} placeholders."""
        from pathlib import Path

        prompts_dir = Path(__file__).parent.parent.parent / "config" / "prompts"
        prompt_path = prompts_dir / "dream_distort.txt"

        assert prompt_path.exists(), "dream_distort.txt must exist"

        content = prompt_path.read_text(encoding="utf-8")

        # Check for required placeholders
        assert "{importance}" in content, "Must have {importance} placeholder"
        assert "{time_distance_days}" in content, "Must have {time_distance_days} placeholder"

        # Check for distortion rules (mention of rules or matrix)
        assert ("规则" in content or "rules" in content.lower()) and (
            "扭曲" in content or "distort" in content.lower()
        ), "Must have distortion rules"


class TestDreamSimulatePrompt:
    """Test dream_simulate.txt has simulation guidance."""

    def test_simulate_prompt_has_simulation_guidance(self):
        """Test 6: dream_simulate.txt has {original_L0}, {importance} placeholders and simulation guidance."""
        from pathlib import Path

        prompts_dir = Path(__file__).parent.parent.parent / "config" / "prompts"
        prompt_path = prompts_dir / "dream_simulate.txt"

        assert prompt_path.exists(), "dream_simulate.txt must exist"

        content = prompt_path.read_text(encoding="utf-8")

        # Check for required placeholders
        assert "{original_L0}" in content, "Must have {original_L0} placeholder"
        assert "{importance}" in content, "Must have {importance} placeholder"

        # Check for simulation guidance
        assert (
            "推演" in content or "模拟" in content or "simulate" in content.lower()
        ), "Must have simulation guidance"


class TestPromptLoading:
    """Test all prompts load successfully."""

    def test_all_dream_prompts_load_without_errors(self):
        """Test 7: All prompts load successfully (no file errors)."""
        from pathlib import Path

        prompts_dir = Path(__file__).parent.parent.parent / "config" / "prompts"
        prompt_files = [
            "dream_system.txt",
            "dream_reorganize.txt",
            "dream_emotion.txt",
            "dream_distort.txt",
            "dream_simulate.txt",
        ]

        for prompt_file in prompt_files:
            prompt_path = prompts_dir / prompt_file
            assert prompt_path.exists(), f"{prompt_file} must exist"

            # Try to read the file
            content = prompt_path.read_text(encoding="utf-8")
            assert len(content) > 0, f"{prompt_file} must not be empty"
