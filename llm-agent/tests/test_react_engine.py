"""
ReAct 引擎单元测试
测试推理循环、Action/Result 解析、输出校验和边界情况处理。
"""

from __future__ import annotations

import json
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# 添加 src 目录到 sys.path
_src_dir = Path(__file__).resolve().parent.parent / "src"
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

from config import config
from react_engine import ReActEngine, _TIMEOUT_DECISION_TEMPLATE
from tools.registry import ToolRegistry
from output_validator import OutputValidator


class TestReActActionParsing(unittest.TestCase):
    """测试 Action 解析功能。"""

    def setUp(self):
        """每个测试用例前的初始化。"""
        self.mock_llm = MagicMock()
        self.tool_registry = ToolRegistry()

        # 注册一个模拟工具用于测试
        def mock_tool(args):
            return {"success": True, "data": {"result": "ok"}, "error": ""}

        self.tool_registry.register("test_tool", mock_tool, "测试工具")

        self.engine = ReActEngine(
            cfg=config,
            tools_registry=self.tool_registry,
            llm_instance=self.mock_llm,
        )

    def test_parse_action_python_style(self):
        """测试解析 Python 风格的 Action。"""
        text = "思考：需要查询规则库。\nAction: search_rules(query='高速接近', layers=[1,2])"
        result = self.engine._parse_action(text)
        self.assertIsNotNone(result)
        self.assertEqual(result["tool"], "search_rules")
        self.assertIn("query", result["args"])
        self.assertEqual(result["args"]["query"], "高速接近")

    def test_parse_action_shell_style(self):
        """测试解析 Shell 风格的 Action。"""
        text = "Action: query_kb entity_type=drone query=DJIMavic3 top_k=5"
        result = self.engine._parse_action(text)
        self.assertIsNotNone(result)
        self.assertEqual(result["tool"], "query_kb")
        self.assertEqual(result["args"]["entity_type"], "drone")
        self.assertEqual(result["args"]["top_k"], 5)

    def test_parse_action_json_style(self):
        """测试解析 JSON 格式的 Action。"""
        text = '需要TOPSIS计算。{"action": "run_topsis", "args": {"target_id": "T001"}}'
        result = self.engine._parse_action(text)
        self.assertIsNotNone(result)
        self.assertEqual(result["tool"], "run_topsis")
        self.assertEqual(result["args"]["target_id"], "T001")

    def test_parse_action_chinese_marker(self):
        """测试解析中文标记的 Action。"""
        text = "行动: check_devices(device_type='干扰器', status='在线')"
        result = self.engine._parse_action(text)
        self.assertIsNotNone(result)
        self.assertEqual(result["tool"], "check_devices")
        self.assertEqual(result["args"]["device_type"], "干扰器")

    def test_parse_action_no_match(self):
        """测试无法解析的文本。"""
        text = "这是一段普通的推理文本，没有 Action 指令。"
        result = self.engine._parse_action(text)
        self.assertIsNone(result)

    def test_parse_action_boolean_args(self):
        """测试布尔值参数解析。"""
        text = "Action: test_tool(flag1=true, flag2=false)"
        result = self.engine._parse_action(text)
        self.assertIsNotNone(result)
        self.assertEqual(result["args"]["flag1"], True)
        self.assertEqual(result["args"]["flag2"], False)

    def test_parse_action_quoted_args(self):
        """测试引号参数的解析。"""
        text = 'Action: search_rules(query="高速接近 未知型号")'
        result = self.engine._parse_action(text)
        self.assertIsNotNone(result)
        self.assertEqual(result["args"]["query"], "高速接近 未知型号")


class TestReActFinalParsing(unittest.TestCase):
    """测试 Final 答案解析功能。"""

    def setUp(self):
        self.mock_llm = MagicMock()
        self.tool_registry = ToolRegistry()
        self.engine = ReActEngine(
            cfg=config,
            tools_registry=self.tool_registry,
            llm_instance=self.mock_llm,
        )

    def test_parse_final_json_block(self):
        """测试从 ```json 代码块解析 Final。"""
        decision_json = json.dumps({
            "decision_id": "test-001",
            "target_id": "T001",
            "threat_assessment": {
                "threat_score": 0.9,
                "threat_level": 5,
                "confidence": 0.85,
                "key_factors": ["高速接近"],
                "uncertainty_flags": ["未知型号"],
            },
            "recommended_action": {
                "action_type": "全频段压制",
                "priority": 1,
                "devices": [],
                "parameters": {},
                "expected_effect": "阻断通信",
                "alternative_actions": [],
            },
            "reasoning_chain": ["步骤1", "步骤2"],
            "data_sources": ["search_rules"],
            "remarks": "",
        }, ensure_ascii=False)

        text = f"推理完成。\nFinal:\n```json\n{decision_json}\n```"
        result = self.engine._parse_final(text)
        self.assertIsNotNone(result)
        self.assertEqual(result["decision_id"], "test-001")

    def test_parse_final_raw_json(self):
        """测试从裸 JSON 解析 Final。"""
        decision_json = json.dumps({
            "decision_id": "test-002",
            "target_id": "T002",
            "threat_assessment": {
                "threat_score": 0.3,
                "threat_level": 2,
                "confidence": 0.9,
                "key_factors": ["低速"],
                "uncertainty_flags": [],
            },
            "recommended_action": {
                "action_type": "监测",
                "priority": 5,
                "devices": [],
                "parameters": {},
                "expected_effect": "持续监测",
                "alternative_actions": [],
            },
            "reasoning_chain": ["分析"],
            "data_sources": ["query_kb"],
            "remarks": "",
        }, ensure_ascii=False)

        text = f"最终决策: {decision_json}"
        result = self.engine._parse_final(text)
        self.assertIsNotNone(result)
        self.assertEqual(result["target_id"], "T002")

    def test_parse_final_no_json(self):
        """测试无 JSON 时的解析。"""
        text = "还在思考中，需要更多信息。"
        result = self.engine._parse_final(text)
        self.assertIsNone(result)

    def test_extract_json_nested(self):
        """测试嵌套花括号的 JSON 提取。"""
        data = {
            "outer": {
                "inner": {"key": "value"},
                "list": [1, 2, 3],
            }
        }
        text = f"结果如下：{json.dumps(data)}"
        result = self.engine._extract_json(text)
        self.assertIsNotNone(result)
        self.assertEqual(result["outer"]["inner"]["key"], "value")


class TestOutputValidation(unittest.TestCase):
    """测试输出校验功能。"""

    def setUp(self):
        self.validator = OutputValidator()

    def test_valid_output(self):
        """测试有效的决策输出。"""
        decision = {
            "decision_id": "test-003",
            "target_id": "T003",
            "threat_assessment": {
                "threat_score": 0.75,
                "threat_level": 4,
                "confidence": 0.82,
                "key_factors": ["高速接近", "接近关键设施"],
                "uncertainty_flags": ["信号异常"],
            },
            "recommended_action": {
                "action_type": "全频段压制",
                "priority": 1,
                "devices": ["jammer_01"],
                "parameters": {"power": "max"},
                "expected_effect": "阻断目标通信",
                "alternative_actions": [],
            },
            "reasoning_chain": ["分析目标特征", "调用TOPSIS", "制定处置方案"],
            "data_sources": ["search_rules", "run_topsis"],
            "remarks": "建议指挥员确认",
        }
        valid, errors = self.validator.validate(decision)
        self.assertTrue(valid, f"校验失败: {errors}")
        self.assertEqual(len(errors), 0)

    def test_invalid_threat_level(self):
        """测试威胁等级超出范围。"""
        decision = {
            "decision_id": "test-004",
            "target_id": "T004",
            "threat_assessment": {
                "threat_score": 1.5,
                "threat_level": 6,  # 超出 1-5 范围
                "confidence": 0.8,
                "key_factors": ["测试"],
                "uncertainty_flags": [],
            },
            "recommended_action": {
                "action_type": "监测",
                "priority": 5,
                "devices": [],
                "parameters": {},
                "expected_effect": "",
                "alternative_actions": [],
            },
            "reasoning_chain": ["测试"],
            "data_sources": ["test"],
            "remarks": "",
        }
        valid, errors = self.validator.validate(decision)
        self.assertFalse(valid)
        self.assertTrue(any("threat_level" in e.lower() or "level" in e.lower() or "6" in e for e in errors))

    def test_missing_required_fields(self):
        """测试缺少必填字段。"""
        decision = {
            "decision_id": "test-005",
            # 缺少 target_id
            "threat_assessment": {
                "threat_score": 0.5,
                "threat_level": 3,
                "confidence": 0.7,
                "key_factors": ["测试"],
                "uncertainty_flags": [],
            },
            "recommended_action": {
                "action_type": "监测",
                "priority": 5,
            },
            "reasoning_chain": [],
            "data_sources": [],
        }
        valid, errors = self.validator.validate(decision)
        self.assertFalse(valid)

    def test_empty_reasoning_chain(self):
        """测试推理链为空。"""
        decision = {
            "decision_id": "test-006",
            "target_id": "T006",
            "threat_assessment": {
                "threat_score": 0.5,
                "threat_level": 3,
                "confidence": 0.7,
                "key_factors": ["测试"],
                "uncertainty_flags": [],
            },
            "recommended_action": {
                "action_type": "监测",
                "priority": 5,
                "devices": [],
                "parameters": {},
                "expected_effect": "",
                "alternative_actions": [],
            },
            "reasoning_chain": [],  # 空列表
            "data_sources": ["test"],
            "remarks": "",
        }
        valid, errors = self.validator.validate(decision)
        self.assertFalse(valid)

    def test_hard_kill_on_low_threat(self):
        """测试低威胁下使用硬杀伤手段。"""
        decision = {
            "decision_id": "test-007",
            "target_id": "T007",
            "threat_assessment": {
                "threat_score": 0.1,
                "threat_level": 1,
                "confidence": 0.9,
                "key_factors": ["低速"],
                "uncertainty_flags": [],
            },
            "recommended_action": {
                "action_type": "激光摧毁",  # 低威胁不应使用
                "priority": 1,
                "devices": [],
                "parameters": {},
                "expected_effect": "",
                "alternative_actions": [],
            },
            "reasoning_chain": ["测试"],
            "data_sources": ["test"],
            "remarks": "",
        }
        valid, errors = self.validator.validate(decision)
        self.assertFalse(valid)
        self.assertTrue(any("硬杀伤" in e or "激光摧毁" in e for e in errors))


class TestTimeoutHandling(unittest.TestCase):
    """测试超时处理。"""

    def setUp(self):
        self.mock_llm = MagicMock()
        self.tool_registry = ToolRegistry()
        # 设置极短超时
        import copy
        self.cfg = copy.deepcopy(config)
        self.cfg.TIMEOUT_SECONDS = 0.001  # 1ms 超时
        self.cfg.MAX_ROUNDS = 10

    def test_timeout_decision_generated(self):
        """测试超时时生成保守决策。"""
        engine = ReActEngine(
            cfg=self.cfg,
            tools_registry=self.tool_registry,
            llm_instance=self.mock_llm,
        )

        # 让 LLM 返回一个需要 Action 的响应（触发第二轮）
        self.mock_llm.create_chat_completion.return_value = {
            "choices": [{"message": {"content": "Action: test_tool(x=1)"}}]
        }

        # 注册工具
        def slow_tool(args):
            time.sleep(0.1)
            return {"success": True, "data": {}, "error": ""}
        self.tool_registry.register("test_tool", slow_tool, "慢速工具")

        result = engine.run(task="测试任务", situation={"task_id": "timeout-001"})

        # 应该返回超时决策
        self.assertIn("decision_id", result)
        self.assertEqual(result["threat_assessment"]["threat_level"], 5)
        self.assertIn("推理超时", result.get("remarks", ""))
        # 置信度应该很低
        self.assertLess(result["threat_assessment"].get("confidence", 1.0), 0.5)

    def test_timeout_decision_structure(self):
        """测试超时决策的字段完整性。"""
        engine = ReActEngine(
            cfg=self.cfg,
            tools_registry=self.tool_registry,
            llm_instance=self.mock_llm,
        )
        decision = engine._generate_timeout_decision("task-001", "target-001")

        self.assertEqual(decision["decision_id"], "task-001")
        self.assertEqual(decision["target_id"], "target-001")
        self.assertIn("threat_assessment", decision)
        self.assertIn("recommended_action", decision)
        self.assertEqual(decision["recommended_action"]["action_type"], "全频段压制")


class TestMaxRoundsHandling(unittest.TestCase):
    """测试最大轮次处理。"""

    def setUp(self):
        self.mock_llm = MagicMock()
        self.tool_registry = ToolRegistry()
        import copy
        self.cfg = copy.deepcopy(config)
        self.cfg.MAX_ROUNDS = 2  # 仅2轮
        self.cfg.TIMEOUT_SECONDS = 30.0  # 长超时

    def test_max_rounds_force_finalize(self):
        """测试达到最大轮次时强制生成决策。"""
        engine = ReActEngine(
            cfg=self.cfg,
            tools_registry=self.tool_registry,
            llm_instance=self.mock_llm,
        )

        # 前两轮始终返回 Action
        call_count = [0]

        def mock_llm_response(**kwargs):
            call_count[0] += 1
            if call_count[0] <= 2:
                # 前两轮：返回 Action
                return {
                    "choices": [{"message": {"content": "Action: test_tool(x=1)"}}]
                }
            else:
                # 第三轮（强制结束）：返回 Final
                decision = json.dumps({
                    "decision_id": "maxround-001",
                    "target_id": "T001",
                    "threat_assessment": {
                        "threat_score": 0.6,
                        "threat_level": 3,
                        "confidence": 0.7,
                        "key_factors": ["中等威胁"],
                        "uncertainty_flags": [],
                    },
                    "recommended_action": {
                        "action_type": "选择性干扰",
                        "priority": 3,
                        "devices": [],
                        "parameters": {},
                        "expected_effect": "",
                        "alternative_actions": [],
                    },
                    "reasoning_chain": ["强制结束"],
                    "data_sources": ["test_tool"],
                    "remarks": "最大轮次强制生成",
                }, ensure_ascii=False)
                return {
                    "choices": [{"message": {"content": f"Final: {decision}"}}]
                }

        self.mock_llm.create_chat_completion.side_effect = mock_llm_response

        def simple_tool(args):
            return {"success": True, "data": {"tool_result": "ok"}, "error": ""}
        self.tool_registry.register("test_tool", simple_tool, "简单工具")

        result = engine.run(task="测试任务", situation={"task_id": "maxround-001"})

        self.assertIsNotNone(result)
        self.assertIn("decision_id", result)


class TestFieldEnsuring(unittest.TestCase):
    """测试字段补全功能。"""

    def setUp(self):
        self.mock_llm = MagicMock()
        self.tool_registry = ToolRegistry()
        self.engine = ReActEngine(
            cfg=config,
            tools_registry=self.tool_registry,
            llm_instance=self.mock_llm,
        )

    def test_ensure_minimal_fields(self):
        """测试补全最小字段。"""
        minimal = {"threat_level": 5}
        result = self.engine._ensure_fields(minimal, "task-x", "target-x")

        self.assertIn("decision_id", result)
        self.assertIn("target_id", result)
        self.assertIn("threat_assessment", result)
        self.assertIn("recommended_action", result)
        self.assertIn("reasoning_chain", result)
        self.assertIn("data_sources", result)

    def test_ensure_threat_level_from_score(self):
        """测试从威胁评分推算威胁等级。"""
        partial = {
            "threat_assessment": {"threat_score": 0.85},
        }
        result = self.engine._ensure_fields(partial, "task-y", "target-y")
        self.assertEqual(result["threat_assessment"]["threat_level"], 4)  # 0.85*5 ≈ 4


class TestObservationFormatting(unittest.TestCase):
    """测试工具观察结果的格式化。"""

    def setUp(self):
        self.mock_llm = MagicMock()
        self.tool_registry = ToolRegistry()
        self.engine = ReActEngine(
            cfg=config,
            tools_registry=self.tool_registry,
            llm_instance=self.mock_llm,
        )

    def test_format_success_observation(self):
        """测试成功结果的格式化。"""
        result = {"success": True, "data": {"key": "value"}, "error": ""}
        obs = self.engine._format_observation("test_tool", result)
        self.assertIn("成功", obs)
        self.assertIn("test_tool", obs)

    def test_format_failure_observation(self):
        """测试失败结果的格式化。"""
        result = {"success": False, "data": None, "error": "连接被拒绝"}
        obs = self.engine._format_observation("test_tool", result)
        self.assertIn("失败", obs)
        self.assertIn("连接被拒绝", obs)

    def test_format_large_output_truncation(self):
        """测试大输出截断。"""
        large_data = {"items": ["x" * 500] * 10}  # ~5KB
        result = {"success": True, "data": large_data, "error": ""}
        obs = self.engine._format_observation("test_tool", result)
        self.assertLess(len(obs), 5000)


if __name__ == "__main__":
    unittest.main(verbosity=2)
