"""
提示词模板质量测试
验证系统提示词、Few-shot 示例和术语词典的完整性和质量。
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

# 项目根目录（llm-agent/）
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_PROMPT_TEMPLATES_DIR = _PROJECT_ROOT / "prompt_templates"


class TestSystemPrompt(unittest.TestCase):
    """测试系统提示词模板。"""

    @classmethod
    def setUpClass(cls):
        """加载系统提示词。"""
        prompt_path = _PROMPT_TEMPLATES_DIR / "system_prompt.txt"
        if not prompt_path.exists():
            cls.fail(cls, f"系统提示词模板不存在: {prompt_path}")

        with open(prompt_path, "r", encoding="utf-8") as f:
            cls.prompt_text = f.read()
        cls.prompt_length = len(cls.prompt_text)

    def test_prompt_is_not_empty(self):
        """测试提示词非空。"""
        self.assertGreater(self.prompt_length, 0)

    def test_prompt_has_minimum_length(self):
        """测试提示词长度不少于 1000 字符。"""
        self.assertGreaterEqual(self.prompt_length, 1000, "系统提示词应至少 1000 字符")

    def test_contains_role_definition(self):
        """测试包含角色定义。"""
        self.assertIn("决策参谋", self.prompt_text)
        self.assertIn("反无人机", self.prompt_text)

    def test_contains_core_principles(self):
        """测试包含核心原则。"""
        self.assertIn("建议者非执行者", self.prompt_text)
        self.assertIn("ROE", self.prompt_text)
        self.assertIn("渐进升级", self.prompt_text)

    def test_contains_output_format_requirements(self):
        """测试包含输出格式要求。"""
        self.assertIn("decision_id", self.prompt_text)
        self.assertIn("threat_assessment", self.prompt_text)
        self.assertIn("recommended_action", self.prompt_text)
        self.assertIn("reasoning_chain", self.prompt_text)

    def test_contains_tool_placeholder(self):
        """测试包含工具占位符。"""
        self.assertIn("{available_tools}", self.prompt_text,
                      "系统提示词必须包含 {available_tools} 占位符")

    def test_contains_reasoning_constraints(self):
        """测试包含推理约束。"""
        self.assertIn("最多执行5轮", self.prompt_text)
        self.assertIn("置信度", self.prompt_text)

    def test_contains_uncertainty_flags(self):
        """测试包含不确定性标记说明。"""
        self.assertIn("低信噪比", self.prompt_text)
        self.assertIn("未知型号", self.prompt_text)
        self.assertIn("平民区临近", self.prompt_text)

    def test_contains_action_type_reference(self):
        """测试包含动作类型参考。"""
        self.assertIn("全频段压制", self.prompt_text)
        self.assertIn("选择性干扰", self.prompt_text)
        self.assertIn("导航诱骗", self.prompt_text)
        self.assertIn("激光摧毁", self.prompt_text)

    def test_contains_military_terminology(self):
        """测试包含军语术语说明。"""
        self.assertIn("CPA", self.prompt_text)
        self.assertIn("TOPSIS", self.prompt_text)
        self.assertIn("蜂群", self.prompt_text)

    def test_prompt_chinese_ratio(self):
        """测试中文文本占比（应为中文主导）。"""
        chinese_chars = sum(1 for c in self.prompt_text if '一' <= c <= '鿿')
        total_alpha = sum(1 for c in self.prompt_text if c.isalpha() or '一' <= c <= '鿿')
        if total_alpha > 0:
            cn_ratio = chinese_chars / total_alpha
            self.assertGreater(cn_ratio, 0.5, f"中文字符占比应 >50%, 当前: {cn_ratio:.1%}")


class TestFewShotExamples(unittest.TestCase):
    """测试 Few-shot 示例文件。"""

    @classmethod
    def setUpClass(cls):
        """加载 Few-shot 示例。"""
        examples_path = _PROMPT_TEMPLATES_DIR / "few_shot_examples.json"
        if not examples_path.exists():
            cls.fail(cls, f"Few-shot 示例文件不存在: {examples_path}")

        try:
            with open(examples_path, "r", encoding="utf-8") as f:
                cls.examples = json.load(f)
        except json.JSONDecodeError as e:
            cls.fail(cls, f"Few-shot 示例 JSON 格式错误: {e}")

    def test_examples_is_list(self):
        """测试示例是列表格式。"""
        self.assertIsInstance(self.examples, list)

    def test_examples_count(self):
        """测试示例数量不少于 10 个。"""
        self.assertGreaterEqual(len(self.examples), 10,
                                f"Few-shot 示例应至少 10 个, 当前: {len(self.examples)}")

    def test_each_example_has_id(self):
        """测试每个示例有 id 字段。"""
        for example in self.examples:
            self.assertIn("id", example, f"示例缺少 id: {example.get('title', '?')}")

    def test_each_example_has_title(self):
        """测试每个示例有标题。"""
        for example in self.examples:
            self.assertIn("title", example)

    def test_each_example_has_situation_summary(self):
        """测试每个示例有态势概要。"""
        for example in self.examples:
            self.assertIn("situation_summary", example)
            self.assertGreater(len(example["situation_summary"]), 20)

    def test_each_example_has_task(self):
        """测试每个示例有任务描述。"""
        for example in self.examples:
            self.assertIn("task", example)
            self.assertGreater(len(example["task"]), 5)

    def test_each_example_has_expected_output(self):
        """测试每个示例有预期输出。"""
        for example in self.examples:
            self.assertIn("expected_output", example)
            output = example["expected_output"]
            self.assertIsInstance(output, dict)
            self.assertIn("threat_assessment", output,
                          f"示例 {example.get('id')} 的 expected_output 缺少 threat_assessment")

    def test_example_output_threat_level_range(self):
        """测试每个示例的预期威胁等级在 1-5 范围内。"""
        for example in self.examples:
            output = example.get("expected_output", {})
            ta = output.get("threat_assessment", {})
            if "threat_level" in ta:
                level = ta["threat_level"]
                self.assertGreaterEqual(level, 1, f"示例 {example['id']}: threat_level < 1")
                self.assertLessEqual(level, 5, f"示例 {example['id']}: threat_level > 5")

    def test_example_output_has_action(self):
        """测试每个示例的预期输出包含推荐动作。"""
        for example in self.examples:
            output = example.get("expected_output", {})
            ra = output.get("recommended_action", {})
            self.assertIn("action_type", ra,
                          f"示例 {example.get('id')} 的 recommended_action 缺少 action_type")

    def test_coverage_scenarios(self):
        """测试示例覆盖了关键场景类型。"""
        all_titles = " ".join(e.get("title", "") for e in self.examples)

        # 检查覆盖的场景
        scenarios_expected = [
            "高速", "消费级", "蜂群", "监测", "平民",
            "FPV", "资源", "信号异常", "低信噪比", "GNSS",
        ]

        covered = [s for s in scenarios_expected if s in all_titles]
        self.assertGreaterEqual(
            len(covered), len(scenarios_expected) * 0.7,
            f"示例应覆盖至少 70% 关键场景。已覆盖: {covered}"
        )


class TestTerminology(unittest.TestCase):
    """测试术语词典。"""

    @classmethod
    def setUpClass(cls):
        """加载术语词典。"""
        term_path = _PROMPT_TEMPLATES_DIR / "terminology.json"
        if not term_path.exists():
            cls.fail(cls, f"术语词典文件不存在: {term_path}")

        try:
            with open(term_path, "r", encoding="utf-8") as f:
                cls.terminology = json.load(f)
        except json.JSONDecodeError as e:
            cls.fail(cls, f"术语词典 JSON 格式错误: {e}")

    def test_terminology_is_dict(self):
        """测试术语词典是字典格式。"""
        self.assertIsInstance(self.terminology, dict)

    def test_terminology_count(self):
        """测试术语数量不少于 20 条。"""
        self.assertGreaterEqual(len(self.terminology), 20,
                                f"术语词典应至少 20 条, 当前: {len(self.terminology)}")

    def test_core_terms_present(self):
        """测试核心术语存在。"""
        core_terms = [
            "CPA", "ROE", "TOPSIS", "AHP",
            "GNSS诱骗", "全频段压制", "射频干扰",
            "硬杀伤", "软杀伤", "威胁等级",
        ]
        for term in core_terms:
            self.assertIn(term, self.terminology,
                          f"核心术语缺失: {term}")

    def test_drone_type_terms_present(self):
        """测试无人机类型术语存在。"""
        drone_terms = [
            "固定翼", "四旋翼", "FPV竞速",
            "察打一体", "巡飞弹", "蜂群",
        ]
        for term in drone_terms:
            self.assertIn(term, self.terminology,
                          f"无人机类型术语缺失: {term}")

    def test_countermeasure_terms_present(self):
        """测试反制手段术语存在。"""
        cm_terms = [
            "激光摧毁", "网捕", "微波毁伤",
            "选择性干扰", "导航诱骗",
        ]
        for term in cm_terms:
            self.assertIn(term, self.terminology,
                          f"反制手段术语缺失: {term}")

    def test_each_term_has_description(self):
        """测试每个术语有描述。"""
        for term, description in self.terminology.items():
            self.assertIsInstance(description, str,
                                  f"术语 '{term}' 的描述不是字符串")
            self.assertGreater(len(description), 10,
                               f"术语 '{term}' 的描述过短 (<10字符): {description}")

    def test_signal_terms_present(self):
        """测试信号相关术语存在。"""
        signal_terms = ["RCS", "SNR", "跳频通信", "数据链"]
        for term in signal_terms:
            self.assertIn(term, self.terminology,
                          f"信号术语缺失: {term}")


class TestPromptTemplateFilesExist(unittest.TestCase):
    """测试所有提示词模板文件存在。"""

    def test_system_prompt_exists(self):
        """测试系统提示词文件存在。"""
        path = _PROMPT_TEMPLATES_DIR / "system_prompt.txt"
        self.assertTrue(path.exists(), f"文件不存在: {path}")

    def test_few_shot_examples_exists(self):
        """测试 Few-shot 示例文件存在。"""
        path = _PROMPT_TEMPLATES_DIR / "few_shot_examples.json"
        self.assertTrue(path.exists(), f"文件不存在: {path}")

    def test_terminology_exists(self):
        """测试术语词典文件存在。"""
        path = _PROMPT_TEMPLATES_DIR / "terminology.json"
        self.assertTrue(path.exists(), f"文件不存在: {path}")

    def test_system_prompt_is_utf8(self):
        """测试系统提示词是 UTF-8 编码。"""
        path = _PROMPT_TEMPLATES_DIR / "system_prompt.txt"
        with open(path, "r", encoding="utf-8") as f:
            f.read()  # 不抛异常即为通过

    def test_few_shot_is_valid_json(self):
        """测试 Few-shot 是有效 JSON。"""
        path = _PROMPT_TEMPLATES_DIR / "few_shot_examples.json"
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertIsInstance(data, list)

    def test_terminology_is_valid_json(self):
        """测试术语词典是有效 JSON。"""
        path = _PROMPT_TEMPLATES_DIR / "terminology.json"
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertIsInstance(data, dict)


if __name__ == "__main__":
    unittest.main(verbosity=2)
