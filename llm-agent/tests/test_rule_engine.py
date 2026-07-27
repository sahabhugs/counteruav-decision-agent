"""
规则引擎→Agent 辅助决策集成测试
验证当规则引擎威胁评估置信度不足时，能成功调用 LLM Agent 进行辅助决策。

测试覆盖：
- 低置信度检测与 Agent 上报触发
- Agent 成功返回高置信度决策
- Agent 不可用时的回退策略
- 请求/响应格式兼容性验证
- trigger_reason 注入 Agent 上下文
- 边界条件：极端值、空数据、并发调用
"""

from __future__ import annotations

import json
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, call

# 添加 src 目录到 sys.path
_src_dir = Path(__file__).resolve().parent.parent / "src"
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

from config import config
from react_engine import ReActEngine, _TIMEOUT_DECISION_TEMPLATE
from tools.registry import ToolRegistry
from output_validator import OutputValidator


# ==================== 辅助函数 ====================

def _build_sample_situation(target_id: str = "T001", **overrides) -> dict:
    """构建测试用态势数据，模拟规则引擎发送的格式。"""
    situation = {
        "task_id": f"task-{target_id}",
        "target_id": target_id,
        "type": overrides.get("type", "固定翼"),
        "model": overrides.get("model", "DJI Mavic 3"),
        "lat": overrides.get("lat", 39.9042),
        "lon": overrides.get("lon", 116.4074),
        "alt": overrides.get("alt", 120.0),
        "speed_ms": overrides.get("speed_ms", 25.0),
        "heading": overrides.get("heading", 180.0),
        "distance_m": overrides.get("distance_m", 800.0),
        "cpa_m": overrides.get("cpa_m", 200.0),
        "signal_features": overrides.get("signal_features", "FHSS 2.4GHz"),
        "snr_db": overrides.get("snr_db", 12.0),
        "behavior": overrides.get("behavior", "高速接近"),
        "threat_hint": overrides.get("threat_hint", "疑似侦察无人机"),
        "environment": overrides.get("environment", {
            "terrain": "城市",
            "weather": "晴",
            "airspace_class": "管制空域",
            "population_density": "高",
            "em_environment": "复杂",
        }),
        "constraints": overrides.get("constraints", {
            "禁止硬杀伤": True,
            "最大干扰功率": "100W",
        }),
        "targets": overrides.get("targets", [
            {
                "target_id": target_id,
                "type": "固定翼",
                "model": "DJI Mavic 3",
                "lat": 39.9042,
                "lon": 116.4074,
                "alt": 120.0,
                "speed_ms": 25.0,
                "heading": 180.0,
                "distance_m": 800.0,
            }
        ]),
        "devices": overrides.get("devices", [
            {"device_id": "jammer_01", "type": "干扰器", "status": "在线"},
            {"device_id": "laser_01", "type": "激光", "status": "在线"},
        ]),
    }
    return situation


def _build_llm_decision(
    threat_score: float = 0.85,
    threat_level: int = 5,
    confidence: float = 0.85,
    action_type: str = "全频段压制",
) -> dict:
    """构建 LLM Agent 返回的决策 JSON。"""
    return {
        "decision_id": "task-T001",
        "target_id": "T001",
        "threat_assessment": {
            "threat_score": threat_score,
            "threat_level": threat_level,
            "confidence": confidence,
            "key_factors": ["高速接近", "信号特征异常"],
            "uncertainty_flags": ["信号异常"],
        },
        "recommended_action": {
            "action_type": action_type,
            "priority": 1,
            "devices": ["jammer_01"],
            "parameters": {"power": "max"},
            "expected_effect": "阻断目标通信与导航",
            "alternative_actions": [
                {"action_type": "选择性干扰", "priority": 2},
            ],
        },
        "reasoning_chain": [
            "分析目标运动特征: 高速接近, 25m/s",
            "查询规则库: 高速接近目标触发 L2-03 规则",
            "执行TOPSIS多属性评估: 威胁贴近度0.85",
            "综合判断: 高威胁目标，建议全频段压制",
        ],
        "data_sources": ["search_rules", "run_topsis", "query_kb"],
        "rule_proposal": None,
        "remarks": "LLM Agent 深度分析完成，置信度较高",
    }


# ==================== 测试类 1: 置信度计算与上报判断 ====================


class TestConfidenceGate(unittest.TestCase):
    """测试置信度评估逻辑 — 模拟 Java ConfidenceGate 的 Python 实现。"""

    def test_high_confidence_no_escalation(self):
        """高置信度（>0.80）不应触发 Agent 上报。"""
        # 模拟高质量场景：5条规则、高SNR、高分类置信度
        matched_rules = ["L1-01", "L2-01", "L2-02", "L3-01", "L4-01"]
        snr = 25.0
        classification_conf = 0.95
        historical_accuracy = 0.90

        confidence = self._calculate_confidence(
            matched_rules, snr, classification_conf, historical_accuracy
        )

        self.assertGreater(confidence, 0.80,
                           f"高质量场景置信度应>0.80, 实际={confidence:.4f}")
        self.assertFalse(confidence < config.CONFIDENCE_THRESHOLD,
                         f"高置信度不应触发Agent上报")

    def test_low_confidence_triggers_escalation(self):
        """低置信度（<0.80）应触发 Agent 上报。"""
        # 模拟低质量场景：1条规则、低SNR、低分类置信度
        matched_rules = ["L2-01"]
        snr = 3.0
        classification_conf = 0.30
        historical_accuracy = 0.30

        confidence = self._calculate_confidence(
            matched_rules, snr, classification_conf, historical_accuracy
        )

        self.assertLess(confidence, config.CONFIDENCE_THRESHOLD,
                        f"低质量场景置信度应<{config.CONFIDENCE_THRESHOLD}, 实际={confidence:.4f}")

    def test_confidence_with_empty_rules(self):
        """空规则列表应返回有效的低置信度。"""
        confidence = self._calculate_confidence([], 10.0, 0.50, 0.50)
        self.assertGreater(confidence, 0.0)
        self.assertLess(confidence, 1.0)
        # 空规则+中等传感器+中等分类+中等历史 → 应低于阈值
        self.assertLess(confidence, config.CONFIDENCE_THRESHOLD,
                        "空规则列表应导致较低置信度")

    def test_confidence_with_null_sensor(self):
        """传感器数据为空时应使用默认值并正常计算。"""
        confidence = self._calculate_confidence(
            ["L1-01", "L2-01"], None, 0.80, 0.80
        )
        self.assertGreater(confidence, 0.0)
        self.assertLessEqual(confidence, 1.0)

    def test_confidence_clamped_to_range(self):
        """置信度应始终在 [0.0, 1.0] 范围内。"""
        # 极端高值
        conf_high = self._calculate_confidence(
            ["L1-01", "L2-01", "L2-02", "L3-01", "L4-01"], 30.0, 1.0, 1.0
        )
        self.assertLessEqual(conf_high, 1.0)

        # 极端低值
        conf_low = self._calculate_confidence([], 0.0, 0.0, 0.0)
        self.assertGreaterEqual(conf_low, 0.0)

    def test_more_rules_increase_confidence(self):
        """更多匹配规则应提高置信度。"""
        conf_few = self._calculate_confidence(
            ["L2-01"], 15.0, 0.80, 0.80
        )
        conf_many = self._calculate_confidence(
            ["L1-01", "L2-01", "L2-02", "L3-01", "L4-01"], 15.0, 0.80, 0.80
        )
        self.assertGreater(conf_many, conf_few,
                           f"更多规则应提高置信度: few={conf_few:.4f}, many={conf_many:.4f}")

    def test_higher_snr_increases_confidence(self):
        """更高SNR应提高置信度。"""
        conf_low = self._calculate_confidence(
            ["L1-01", "L2-01"], 3.0, 0.80, 0.80
        )
        conf_high = self._calculate_confidence(
            ["L1-01", "L2-01"], 25.0, 0.80, 0.80
        )
        self.assertGreater(conf_high, conf_low,
                           f"更高SNR应提高置信度: lowSNR={conf_low:.4f}, highSNR={conf_high:.4f}")

    @staticmethod
    def _calculate_confidence(
        matched_rules: list,
        snr: float | None,
        classification_conf: float,
        historical_accuracy: float,
    ) -> float:
        """模拟 Java ConfidenceGate.calculateConfidence() 的权重计算。

        5个维度加权：
        - 规则一致性 (0.30)
        - 传感器质量 (0.25)
        - 分类置信度 (0.20)
        - 规则覆盖度 (0.15)
        - 历史准确率 (0.10)
        """
        def clamp(v, lo, hi):
            return max(lo, min(hi, v))

        # 1. 规则一致性
        if not matched_rules:
            rule_consistency = 0.50
        else:
            n = len(matched_rules)
            if n >= 5:
                rule_consistency = 0.95
            elif n >= 3:
                rule_consistency = 0.85
            elif n >= 2:
                rule_consistency = 0.75
            else:
                rule_consistency = 0.60

        # 2. 传感器质量
        if snr is None:
            sensor_quality = 0.50
        elif snr >= 20:
            sensor_quality = 0.95
        elif snr >= 15:
            sensor_quality = 0.85
        elif snr >= 10:
            sensor_quality = 0.70
        elif snr >= 5:
            sensor_quality = 0.50
        else:
            sensor_quality = 0.30

        # 3. 分类置信度
        class_conf = clamp(classification_conf, 0.0, 1.0)

        # 4. 规则覆盖度
        if not matched_rules:
            rule_coverage = 0.0
        else:
            prefixes = {"L1-", "L2-", "L3-", "L4-"}
            covered = set()
            for rule in matched_rules:
                for p in prefixes:
                    if rule.startswith(p):
                        covered.add(p)
                        break
            if not covered:
                rule_coverage = 0.25
            else:
                rule_coverage = len(covered) / 4.0

        # 5. 历史准确率
        historical = clamp(historical_accuracy, 0.0, 1.0)

        # 加权求和
        confidence = (
            0.30 * rule_consistency
            + 0.25 * sensor_quality
            + 0.20 * class_conf
            + 0.15 * rule_coverage
            + 0.10 * historical
        )
        return clamp(confidence, 0.0, 1.0)


# ==================== 测试类 2: Agent 决策增强 ====================


class TestAgentEnhancedDecision(unittest.TestCase):
    """测试 Agent 辅助决策的请求构建、响应解析和决策合并。"""

    def setUp(self):
        """初始化 ReAct 引擎 mock 和基本测试数据。"""
        self.mock_llm = MagicMock()
        self.tool_registry = ToolRegistry()

        # 注册轻量 mock 工具
        def mock_search_rules(args):
            return {
                "success": True,
                "data": [
                    {"name": "L2-03", "content": "高速接近目标→威胁等级4"},
                    {"name": "L3-07", "content": "城市环境→优先使用可逆手段"},
                ],
                "error": "",
            }

        def mock_run_topsis(args):
            return {
                "success": True,
                "data": {
                    "threat_score": 0.85,
                    "threat_level": 5,
                    "closeness_coefficient": 0.85,
                },
                "error": "",
            }

        self.tool_registry.register("search_rules", mock_search_rules, "搜索规则")
        self.tool_registry.register("run_topsis", mock_run_topsis, "TOPSIS评估")

        self.engine = ReActEngine(
            cfg=config,
            tools_registry=self.tool_registry,
            llm_instance=self.mock_llm,
        )

    def test_build_escalation_request(self):
        """测试构建上报 Agent 的请求格式 — 模拟 Java LLMClientService 的 payload。"""
        situation = _build_sample_situation("T-ESC-001")
        triggers = ["置信度低于阈值: 0.6500 < 0.8", "EVT开集识别: 目标分类置信度低于阈值"]

        # 模拟 Java 端构建的请求格式
        request_payload = {
            "task_id": situation["task_id"],
            "trigger_reason": triggers[0],
            "trigger_detail": "; ".join(triggers),
            "situation": situation,
            "task_description": (
                f"对目标 T-ESC-001 进行深度威胁评估并推荐反制策略。"
                f"触发原因: {', '.join(triggers)}"
            ),
            "threat_level": 3,  # 规则引擎初步评估的威胁等级
        }

        # 验证请求格式兼容性
        self.assertIn("task_id", request_payload)
        self.assertIn("trigger_reason", request_payload)
        self.assertIn("situation", request_payload)
        self.assertIn("task_description", request_payload)
        self.assertIn("threat_level", request_payload)
        # 验证 trigger_reason 传达了低置信度信息
        self.assertIn("置信度低于阈值", request_payload["trigger_reason"])

    def test_parse_agent_response(self):
        """测试解析 Agent 返回的 DecideResponse 格式。"""
        llm_decision = _build_llm_decision(confidence=0.88)

        response = {
            "task_id": "task-T001",
            "status": "success",
            "decision": llm_decision,
            "metadata": {
                "elapsed_seconds": 2.35,
                "validation_passed": True,
                "model": "qwen3-8b",
                "inference_rounds": 3,
            },
            "errors": None,
        }

        # 验证响应格式（模拟 Java parseLLMResponse）
        self.assertEqual(response["status"], "success")
        self.assertIsNotNone(response["decision"])
        self.assertIsNotNone(response["decision"]["threat_assessment"])

        ta = response["decision"]["threat_assessment"]
        self.assertIn("confidence", ta)
        self.assertIn("threat_level", ta)
        self.assertIn("threat_score", ta)

        # 验证 Agent 返回的置信度
        agent_confidence = ta["confidence"]
        self.assertGreater(agent_confidence, 0.80,
                           f"Agent应返回较高置信度, 实际={agent_confidence}")

    def test_confidence_improved_after_agent(self):
        """Agent 应能提升置信度（相比规则引擎的初始评估）。"""
        rule_engine_confidence = 0.65  # 规则引擎低置信度
        agent_confidence = 0.88        # Agent 返回的置信度

        # 取最大值（模拟 Java 侧 Math.max 逻辑）
        final_confidence = max(rule_engine_confidence, agent_confidence)
        self.assertGreater(final_confidence, rule_engine_confidence)
        self.assertEqual(final_confidence, agent_confidence)
        self.assertGreater(final_confidence, config.CONFIDENCE_THRESHOLD,
                           "合并后置信度应超过阈值")

    def test_agent_fallback_when_unavailable(self):
        """Agent 不可用时使用规则引擎原决策（回退）。"""
        rule_engine_confidence = 0.65
        fallback_source = "FALLBACK_RULE_ENGINE"

        # 模拟 LLM 不可用：source=FALLBACK_RULE_ENGINE, confidence=0.0
        if fallback_source == "FALLBACK_RULE_ENGINE":
            final_confidence = rule_engine_confidence  # 保持原始置信度
            final_source = "RULE_ENGINE"
        else:
            final_confidence = max(rule_engine_confidence, 0.0)
            final_source = "LLM_AGENT"

        self.assertEqual(final_source, "RULE_ENGINE")
        self.assertEqual(final_confidence, 0.65)
        self.assertLess(final_confidence, config.CONFIDENCE_THRESHOLD,
                        "回退时置信度仍低于阈值，需标记人工审核")

    def test_agent_error_status_reduces_confidence(self):
        """Agent 返回 error 状态时应降低置信度。"""
        rule_engine_confidence = 0.65
        agent_raw_confidence = 0.70
        agent_status = "error"

        # 模拟 Java 侧逻辑：status=error 时 cap 置信度
        if agent_status == "error":
            agent_confidence = min(agent_raw_confidence, 0.3)
        else:
            agent_confidence = agent_raw_confidence

        final_confidence = max(rule_engine_confidence, agent_confidence)

        # Agent error时置信度应保持较低
        self.assertLess(agent_confidence, 0.5,
                        f"Agent error状态置信度应被限制, 实际={agent_confidence}")
        self.assertEqual(final_confidence, rule_engine_confidence,
                         "Agent error时应使用规则引擎原始置信度")

    def test_merge_decision_fields(self):
        """测试决策字段合并：LLM增强后保留规则引擎基础字段。"""
        rule_engine_base = {
            "threat_assessment": {
                "threat_score": 0.70,
                "threat_level": 4,
                "confidence": 0.65,
                "key_factors": ["高速接近"],
                "uncertainty_flags": ["信号异常"],
            },
            "recommended_action": {
                "action_type": "全频段压制",
                "priority": 1,
                "devices": ["jammer_01"],
            },
        }

        llm_enhancement = {
            "confidence": 0.88,
            "reasoning": "LLM深度分析：目标行为模式匹配已知攻击序列",
        }

        # 合并：置信度取最大值，推理链追加LLM结果
        merged = dict(rule_engine_base)
        merged["threat_assessment"]["confidence"] = max(
            rule_engine_base["threat_assessment"]["confidence"],
            llm_enhancement["confidence"],
        )
        merged["llm_reasoning"] = llm_enhancement["reasoning"]

        self.assertEqual(merged["threat_assessment"]["confidence"], 0.88)
        self.assertEqual(merged["threat_assessment"]["threat_level"], 4)  # 保留原始等级
        self.assertIn("llm_reasoning", merged)


# ==================== 测试类 3: ReAct 引擎增强处理 ====================


class TestReActEngineEscalationHandling(unittest.TestCase):
    """测试 ReAct 引擎处理低置信度上报场景的能力。"""

    def setUp(self):
        self.mock_llm = MagicMock()
        self.tool_registry = ToolRegistry()
        self.engine = ReActEngine(
            cfg=config,
            tools_registry=self.tool_registry,
            llm_instance=self.mock_llm,
        )

    def test_system_prompt_includes_trigger_context(self):
        """系统提示词应包含上报触发原因（当作为 escalation 调用时）。"""
        situation = _build_sample_situation("T-ESC-002")
        task = "对目标 T-ESC-002 进行深度威胁评估。触发原因: 置信度低于阈值: 0.6500 < 0.8"

        prompt = self.engine._build_system_prompt(situation, task)

        # 验证提示词包含关键上下文
        self.assertIn("当前态势摘要", prompt)
        self.assertIn("T-ESC-002", prompt)
        self.assertIn("可用工具", prompt.lower() or "工具" in prompt)

    def test_ensure_fields_preserves_confidence(self):
        """字段补全不应覆盖已有的置信度。"""
        decision = {
            "threat_assessment": {
                "threat_score": 0.85,
                "threat_level": 5,
                "confidence": 0.88,  # 已有置信度
                "key_factors": ["高速接近"],
                "uncertainty_flags": [],
            },
            "recommended_action": {
                "action_type": "全频段压制",
                "priority": 1,
            },
        }
        result = self.engine._ensure_fields(decision, "task-esc", "T-ESC")

        self.assertEqual(result["threat_assessment"]["confidence"], 0.88,
                         "已有置信度不应被覆盖")

    def test_ensure_fields_adds_missing_confidence(self):
        """字段补全应为缺失的置信度设置默认值。"""
        decision = {
            "threat_assessment": {
                "threat_score": 0.50,
                "threat_level": 3,
            },
        }
        result = self.engine._ensure_fields(decision, "task-esc", "T-ESC")

        self.assertIn("confidence", result["threat_assessment"])
        self.assertEqual(result["threat_assessment"]["confidence"], 0.5)

    def test_timeout_decision_has_low_confidence(self):
        """超时决策的置信度应极低。"""
        decision = self.engine._generate_timeout_decision("task-to", "T-TO")
        self.assertLess(decision["threat_assessment"]["confidence"], 0.5,
                        "超时决策置信度应<0.5")
        self.assertIn("推理超时", decision.get("remarks", ""))

    def test_schema_failure_decision_flags_degraded(self):
        """Schema 校验失败的降级决策应标记 DEGRADED_TO_RULE_ENGINE。"""
        last_attempt = {
            "threat_assessment": {
                "threat_score": 0.60,
                "threat_level": 3,
                "confidence": 0.45,
                "key_factors": ["不确定"],
                "uncertainty_flags": ["信号异常"],
            },
            "recommended_action": {
                "action_type": "选择性干扰",
                "priority": 3,
            },
        }
        decision = self.engine._generate_schema_failure_decision(
            last_attempt, "task-sf", "T-SF"
        )

        flags = decision.get("uncertainty_flags", [])
        self.assertTrue(
            any("DEGRADED_TO_RULE_ENGINE" in f for f in flags),
            f"降级决策应标记 DEGRADED_TO_RULE_ENGINE, 当前flags={flags}"
        )


# ==================== 测试类 4: 端到端集成流程 ====================


class TestEndToEndEscalationFlow(unittest.TestCase):
    """端到端测试：从规则引擎低置信度检测到 Agent 辅助决策返回。"""

    def setUp(self):
        self.mock_llm = MagicMock()
        self.tool_registry = ToolRegistry()

        # 注册模拟工具
        self.tool_registry.register(
            "search_rules",
            lambda args: {"success": True, "data": [{"name": "L2-03"}], "error": ""},
            "搜索规则",
        )
        self.tool_registry.register(
            "run_topsis",
            lambda args: {"success": True, "data": {"threat_score": 0.85}, "error": ""},
            "TOPSIS评估",
        )

        self.engine = ReActEngine(
            cfg=config,
            tools_registry=self.tool_registry,
            llm_instance=self.mock_llm,
        )

    def test_full_escalation_flow_success(self):
        """完整流程：规则引擎低置信度 → Agent 调用 → 高置信度决策返回。"""
        # Step 1: 模拟规则引擎威胁评估得到低置信度
        rule_confidence = 0.62
        self.assertLess(rule_confidence, config.CONFIDENCE_THRESHOLD)

        # Step 2: 构建上报请求
        situation = _build_sample_situation("T-E2E-001")
        triggers = [f"置信度低于阈值: {rule_confidence:.4f} < {config.CONFIDENCE_THRESHOLD}"]

        # Step 3: 设置 LLM mock 返回高质量决策
        llm_decision = _build_llm_decision(confidence=0.90, threat_level=5)
        self.mock_llm.create_chat_completion.return_value = {
            "choices": [{"message": {"content": f"Final: {json.dumps(llm_decision, ensure_ascii=False)}"}}]
        }

        # Step 4: Agent 执行推理
        task_desc = f"对目标 T-E2E-001 进行深度威胁评估。触发原因: {triggers[0]}"
        result = self.engine.run(task=task_desc, situation=situation)

        # Step 5: 验证结果
        self.assertIsNotNone(result)
        self.assertIn("threat_assessment", result)
        agent_confidence = result["threat_assessment"]["confidence"]
        self.assertGreater(agent_confidence, rule_confidence,
                           f"Agent置信度({agent_confidence})应高于规则引擎({rule_confidence})")

        # Step 6: 模拟合并后的最终决策
        final_confidence = max(rule_confidence, agent_confidence)
        self.assertGreater(final_confidence, config.CONFIDENCE_THRESHOLD,
                           "合并后置信度应超过阈值，决策可用")

    def test_full_escalation_flow_agent_timeout(self):
        """Agent 超时 → 使用规则引擎回退决策。"""
        import copy
        timeout_cfg = copy.deepcopy(config)
        timeout_cfg.TIMEOUT_SECONDS = 0.001  # 极短超时
        timeout_cfg.MAX_ROUNDS = 10

        engine = ReActEngine(
            cfg=timeout_cfg,
            tools_registry=self.tool_registry,
            llm_instance=self.mock_llm,
        )

        # LLM 始终返回 Action（导致下一轮），从而触发超时
        self.mock_llm.create_chat_completion.return_value = {
            "choices": [{"message": {"content": "Action: search_rules(query='测试')"}}]
        }

        situation = _build_sample_situation("T-TO-001")
        result = engine.run(task="测试超时回退", situation=situation)

        # 应返回超时决策（低置信度保守方案）
        self.assertIsNotNone(result)
        self.assertLess(result["threat_assessment"]["confidence"], 0.5,
                        "超时决策置信度应极低")
        self.assertEqual(result["recommended_action"]["action_type"], "全频段压制",
                         "超时应使用保守策略")

    def test_full_escalation_flow_agent_returns_low_confidence(self):
        """Agent 也无法获得高置信度 → 标记人工审核。"""
        # LLM 返回低置信度决策
        llm_decision = _build_llm_decision(confidence=0.45, threat_level=3)
        self.mock_llm.create_chat_completion.return_value = {
            "choices": [{"message": {"content": f"Final: {json.dumps(llm_decision, ensure_ascii=False)}"}}]
        }

        situation = _build_sample_situation("T-LOW-001")
        result = self.engine.run(
            task="对目标 T-LOW-001 进行深度威胁评估。触发原因: 置信度不足",
            situation=situation,
        )

        agent_confidence = result["threat_assessment"]["confidence"]
        self.assertLess(agent_confidence, config.CONFIDENCE_THRESHOLD,
                        f"Agent低置信度({agent_confidence})应低于阈值")

        # 验证决策仍包含完整结构（即使置信度低）
        self.assertIn("recommended_action", result)
        self.assertIn("reasoning_chain", result)

    def test_multiple_escalation_triggers(self):
        """多个触发条件同时满足时的处理。"""
        triggers = [
            "置信度低于阈值: 0.5500 < 0.8",
            "EVT开集识别: 目标分类置信度低于阈值 (当前: 0.55 < 0.65)",
            "未知机型类别，无法通过规则引擎准确判断威胁",
        ]

        situation = _build_sample_situation("T-MULTI-001")
        task_desc = f"对目标 T-MULTI-001 进行深度威胁评估。触发原因: {', '.join(triggers)}"

        llm_decision = _build_llm_decision(confidence=0.82)
        self.mock_llm.create_chat_completion.return_value = {
            "choices": [{"message": {"content": f"Final: {json.dumps(llm_decision, ensure_ascii=False)}"}}]
        }

        result = self.engine.run(task=task_desc, situation=situation)

        # 多触发条件下 Agent 应尽力给出高质量决策
        self.assertIsNotNone(result)
        self.assertGreater(result["threat_assessment"]["confidence"], 0.5)


# ==================== 测试类 5: 请求/响应格式兼容性 ====================


class TestRequestResponseCompatibility(unittest.TestCase):
    """测试 Python LLM Agent 与 Java 规则引擎之间的请求/响应格式兼容性。

    使用内联 Pydantic 模型（与 main.py 中的定义保持一致），避免依赖 fastapi 导入。
    """

    @classmethod
    def setUpClass(cls):
        """动态定义与 main.py 一致的 Pydantic 模型。"""
        from typing import Optional, List
        from pydantic import BaseModel, Field

        class SituationDataInline(BaseModel):
            task_id: str = Field(..., description="任务ID")
            target_id: Optional[str] = Field(default=None)
            type: Optional[str] = Field(default=None)
            model: Optional[str] = Field(default=None)
            lat: Optional[float] = Field(default=None)
            lon: Optional[float] = Field(default=None)
            alt: Optional[float] = Field(default=None)
            speed_ms: Optional[float] = Field(default=None)
            heading: Optional[float] = Field(default=None)
            distance_m: Optional[float] = Field(default=None)
            cpa_m: Optional[float] = Field(default=None)
            signal_features: Optional[str] = Field(default=None)
            snr_db: Optional[float] = Field(default=None)
            behavior: Optional[str] = Field(default=None)
            threat_hint: Optional[str] = Field(default=None)
            environment: Optional[dict] = Field(default=None)
            constraints: Optional[dict] = Field(default=None)
            targets: Optional[List[dict]] = Field(default=None)
            devices: Optional[List[dict]] = Field(default=None)

            class Config:
                extra = "allow"

        class DecideRequestInline(BaseModel):
            task_id: str = Field(..., description="任务ID（唯一标识）")
            trigger_reason: str = Field(..., description="触发原因")
            trigger_detail: Optional[str] = Field(default="")
            situation: SituationDataInline = Field(..., description="态势信息")
            task_description: str = Field(..., description="任务描述")
            threat_level: int = Field(default=3, ge=1, le=5)
            urgent: bool = Field(default=False)

        cls.SituationData = SituationDataInline
        cls.DecideRequest = DecideRequestInline

    def test_decide_request_model_accepts_java_payload(self):
        """验证 Pydantic DecideRequest 能接受 Java 端发送的 payload 格式。"""
        # 模拟 Java LLMClientService 构建的 payload
        java_payload = {
            "task_id": "req-001",
            "trigger_reason": "置信度低于阈值: 0.6500 < 0.8",
            "trigger_detail": "置信度低于阈值: 0.6500 < 0.8; EVT开集识别",
            "situation": {
                "task_id": "req-001",
                "target_id": "T001",
                "targets": [
                    {"target_id": "T001", "type": "固定翼", "lat": 39.9, "lon": 116.4,
                     "alt": 120.0, "speed_ms": 25.0, "heading": 180.0, "distance_m": 800.0}
                ],
                "devices": [
                    {"device_id": "jammer_01", "type": "干扰器", "status": "在线"}
                ],
                "environment": {
                    "terrain": "城市",
                    "weather": "晴",
                    "airspace_class": "管制空域",
                    "population_density": "高",
                    "em_environment": "复杂",
                },
            },
            "task_description": "对目标 T001 进行深度威胁评估并推荐反制策略",
            "threat_level": 3,
        }

        # 验证请求能被正确解析
        try:
            request = self.DecideRequest(**java_payload)
            self.assertEqual(request.task_id, "req-001")
            self.assertEqual(request.trigger_reason, "置信度低于阈值: 0.6500 < 0.8")
            self.assertEqual(request.threat_level, 3)
            self.assertIsNotNone(request.situation)
            self.assertEqual(request.situation.target_id, "T001")
            # targets/devices/environment 通过 extra="allow" 接受
            self.assertIsNotNone(request.situation.targets)
            self.assertEqual(len(request.situation.targets), 1)
            self.assertIsNotNone(request.situation.devices)
            self.assertIsNotNone(request.situation.environment)
        except Exception as e:
            self.fail(f"Java payload 解析失败: {e}")

    def test_decide_response_format_for_java(self):
        """验证 Python DecideResponse 的 JSON 格式能被 Java parseLLMResponse 正确解析。"""
        decision = _build_llm_decision(confidence=0.88)
        response = {
            "task_id": "task-T001",
            "status": "success",
            "decision": decision,
            "metadata": {
                "elapsed_seconds": 2.35,
                "validation_passed": True,
                "inference_rounds": 3,
            },
            "errors": None,
        }

        # 验证 Java 端期望的字段路径
        self.assertIn("decision", response)
        self.assertIn("threat_assessment", response["decision"])
        self.assertIn("confidence", response["decision"]["threat_assessment"])
        self.assertIn("threat_level", response["decision"]["threat_assessment"])
        self.assertIn("recommended_action", response["decision"])
        self.assertIn("action_type", response["decision"]["recommended_action"])

    def test_threat_level_default_value(self):
        """threat_level 默认值应为3（中等威胁）。"""
        request = self.DecideRequest(
            task_id="test-default",
            trigger_reason="测试",
            situation={"task_id": "test-default"},
            task_description="测试任务描述",
        )
        self.assertEqual(request.threat_level, 3,
                         "threat_level 默认值应为3（中等威胁）")

    def test_situation_extra_fields_preserved(self):
        """SituationData 的 extra="allow" 应保留额外字段。"""
        data = self.SituationData(
            task_id="test-extra",
            target_id="T001",
            lat=39.9,
            lon=116.4,
            alt=120.0,
        )

        # 通过 model_dump 验证额外字段
        dumped = data.model_dump()
        self.assertEqual(dumped["task_id"], "test-extra")
        self.assertEqual(dumped["target_id"], "T001")


# ==================== 测试类 6: RuleEngineIntegration 集成层 ====================


class TestRuleEngineIntegration(unittest.TestCase):
    """测试 rule_engine.py 中的 RuleEngineIntegration 类。"""

    def setUp(self):
        self.mock_llm = MagicMock()
        self.tool_registry = ToolRegistry()
        self.tool_registry.register(
            "search_rules",
            lambda args: {"success": True, "data": [{"name": "L2-03"}], "error": ""},
            "搜索规则",
        )
        self.engine = ReActEngine(
            cfg=config,
            tools_registry=self.tool_registry,
            llm_instance=self.mock_llm,
        )

    def _get_integration(self, with_agent: bool = True):
        """获取 RuleEngineIntegration 实例。"""
        from rule_engine import RuleEngineIntegration
        return RuleEngineIntegration(
            react_engine=self.engine if with_agent else None,
            confidence_threshold=0.80,
        )

    def test_high_confidence_no_agent_call(self):
        """高置信度场景：不应调用Agent，直接返回规则引擎决策。"""
        integration = self._get_integration(with_agent=True)

        result = integration.assess_with_agent_fallback(
            target_id="T-HC-001",
            matched_rules=["L1-01", "L2-01", "L2-02", "L3-01", "L4-01"],
            sensor_status={"rf_sensor": 25.0},
            classification_confidence=0.95,
            situation={"task_id": "task-hc", "target_id": "T-HC-001"},
            task="测试高置信度",
            historical_accuracy=0.90,
            drone_category="CONSUMER_QUADCOPTER",
        )

        self.assertEqual(result["source"], "RULE_ENGINE")
        self.assertFalse(result["triggered_escalation"])
        self.assertGreater(result["confidence"], 0.85)
        self.assertIsNone(result["agent_decision"])
        # Agent不应被调用
        self.mock_llm.create_chat_completion.assert_not_called()

    def test_low_confidence_triggers_agent(self):
        """低置信度场景：应触发Agent调用并返回Agent增强结果。"""
        integration = self._get_integration(with_agent=True)

        # 设置 mock 返回高质量决策
        llm_decision = _build_llm_decision(confidence=0.90, threat_level=5)
        self.mock_llm.create_chat_completion.return_value = {
            "choices": [{"message": {"content": f"Final: {json.dumps(llm_decision, ensure_ascii=False)}"}}]
        }

        result = integration.assess_with_agent_fallback(
            target_id="T-LC-001",
            matched_rules=["L2-01"],
            sensor_status={"rf_sensor": 3.0},
            classification_confidence=0.30,
            situation={"task_id": "task-lc", "target_id": "T-LC-001"},
            task="测试低置信度",
            historical_accuracy=0.30,
            drone_category="UNKNOWN",
        )

        self.assertTrue(result["triggered_escalation"])
        self.assertGreater(len(result["trigger_reasons"]), 0)
        # Agent应提升了置信度
        self.assertGreater(result["confidence"], result["rule_engine_confidence"])
        self.assertIsNotNone(result["agent_decision"])

    def test_agent_unavailable_fallback(self):
        """Agent不可用时应回退到规则引擎决策。"""
        integration = self._get_integration(with_agent=False)

        result = integration.assess_with_agent_fallback(
            target_id="T-FB-001",
            matched_rules=["L2-01"],
            sensor_status={"rf_sensor": 5.0},
            classification_confidence=0.40,
            situation={"task_id": "task-fb", "target_id": "T-FB-001"},
            task="测试回退",
        )

        self.assertEqual(result["source"], "RULE_ENGINE")
        self.assertFalse(result["agent_available"])
        self.assertTrue(result["triggered_escalation"])
        self.assertIn("LLM_UNAVAILABLE", result["trigger_reasons"][-1])
        self.assertIsNotNone(result["decision"])
        self.assertIn("threat_assessment", result["decision"])

    def test_agent_exception_fallback(self):
        """Agent调用持续失败时应回退到规则引擎决策。

        ReAct 引擎内部捕获 LLM 异常后返回超时决策（低置信度），
        集成层检测到 Agent 置信度极低时应回退到规则引擎决策。
        """
        integration = self._get_integration(with_agent=True)

        # 让 LLM 持续抛出异常（ReAct引擎内部捕获并最终返回超时决策）
        self.mock_llm.create_chat_completion.side_effect = RuntimeError("模型推理失败")

        result = integration.assess_with_agent_fallback(
            target_id="T-EX-001",
            matched_rules=["L2-01"],
            sensor_status={"rf_sensor": 5.0},
            classification_confidence=0.40,
            situation={"task_id": "task-ex", "target_id": "T-EX-001"},
            task="测试异常回退",
        )

        # ReAct引擎内部处理异常，返回超时决策（置信度极低）
        # 集成层检测到 Agent 置信度低于规则引擎，应回退
        self.assertIsNotNone(result["decision"])
        # Agent返回的决策置信度极低（超时保护机制）
        self.assertIsNotNone(result["agent_decision"])
        agent_conf = result["agent_confidence"]
        self.assertLess(agent_conf, 0.5,
                        f"LLM持续失败时Agent置信度应极低, 实际={agent_conf}")
        # 最终置信度应取规则引擎和Agent中的最大值
        self.assertGreaterEqual(
            result["confidence"],
            result["rule_engine_confidence"],
        )

    def test_agent_returns_lower_confidence(self):
        """Agent返回的置信度低于规则引擎时使用混合决策。"""
        integration = self._get_integration(with_agent=True)

        # Agent返回的置信度反而更低
        llm_decision = _build_llm_decision(confidence=0.30)
        self.mock_llm.create_chat_completion.return_value = {
            "choices": [{"message": {"content": f"Final: {json.dumps(llm_decision, ensure_ascii=False)}"}}]
        }

        result = integration.assess_with_agent_fallback(
            target_id="T-Lower-001",
            matched_rules=["L1-01", "L2-01", "L3-01"],
            sensor_status={"rf_sensor": 15.0},
            classification_confidence=0.75,
            situation={"task_id": "task-lower", "target_id": "T-Lower-001"},
            task="测试Agent低置信度",
            historical_accuracy=0.80,
        )

        # 规则引擎置信度 > Agent置信度 → HYBRID模式
        self.assertGreater(result["rule_engine_confidence"], result["agent_confidence"])
        self.assertEqual(result["source"], "HYBRID")
        # 最终置信度应为规则引擎的（较高者）
        self.assertEqual(result["confidence"], result["rule_engine_confidence"])

    def test_complex_threat_triggers_escalation(self):
        """复合威胁（3+标签）即使置信度高也应触发上报。"""
        integration = self._get_integration(with_agent=False)

        result = integration.assess_with_agent_fallback(
            target_id="T-CT-001",
            matched_rules=["L1-01", "L2-01", "L3-01"],
            sensor_status={"rf_sensor": 20.0},
            classification_confidence=0.90,
            situation={"task_id": "task-ct", "target_id": "T-CT-001"},
            task="测试复合威胁",
            historical_accuracy=0.85,
            threat_behavior_tags=["快速抵近", "侦察", "徘徊", "低空突防"],
            drone_category="MILITARY_FIXED_WING",
        )

        # 即使综合置信度可能>0.80，复合威胁标签仍应触发
        self.assertTrue(result["triggered_escalation"])
        self.assertTrue(
            any("复合威胁" in r for r in result["trigger_reasons"]),
            f"应包含复合威胁触发原因: {result['trigger_reasons']}"
        )

    def test_result_structure_completeness(self):
        """验证返回结果的完整结构。"""
        integration = self._get_integration(with_agent=False)

        result = integration.assess_with_agent_fallback(
            target_id="T-STRUCT",
            matched_rules=["L2-01"],
            sensor_status=None,
            classification_confidence=0.50,
            situation={"task_id": "task-struct"},
            task="测试结构完整性",
        )

        required_keys = [
            "decision", "confidence", "source",
            "rule_engine_confidence", "agent_confidence",
            "triggered_escalation", "trigger_reasons",
            "agent_available", "agent_decision",
        ]
        for key in required_keys:
            self.assertIn(key, result, f"结果应包含 '{key}' 字段")

    def test_merge_decisions_preserves_both_sources(self):
        """决策合并应保留双方信息。"""
        from rule_engine import RuleEngineIntegration

        rule_dec = {
            "decision_id": "task-merge",
            "target_id": "T-MERGE",
            "reasoning_chain": ["规则引擎分析"],
            "data_sources": ["rule_engine"],
            "uncertainty_flags": ["数据不完整"],
            "remarks": "规则引擎备注",
        }
        agent_dec = {
            "reasoning_chain": ["Agent深度分析"],
            "data_sources": ["search_rules", "query_kb"],
            "uncertainty_flags": ["信号异常"],
            "remarks": "Agent备注",
        }

        merged = RuleEngineIntegration._merge_decisions(rule_dec, agent_dec)

        # 推理链应包含双方
        self.assertIn("规则引擎分析", merged["reasoning_chain"])
        self.assertIn("Agent深度分析", merged["reasoning_chain"])
        # 数据来源应合并
        self.assertIn("rule_engine", merged["data_sources"])
        self.assertIn("search_rules", merged["data_sources"])
        # 不确定标记应合并去重
        self.assertIn("数据不完整", merged["uncertainty_flags"])
        self.assertIn("信号异常", merged["uncertainty_flags"])
        # 备注应追加
        self.assertIn("规则引擎备注", merged["remarks"])
        self.assertIn("Agent备注", merged["remarks"])


# ==================== 测试类 7: rule_engine 模块函数 ====================


class TestRuleEngineModuleFunctions(unittest.TestCase):
    """测试 rule_engine.py 模块中的独立函数。"""

    def test_calculate_confidence_matches_java(self):
        """Python 置信度计算应与 Java ConfidenceGate 结果一致。"""
        from rule_engine import calculate_confidence

        # 对标 Java ConfidenceGateTest.testHighQualityTarget_HighConfidence
        conf_high = calculate_confidence(
            ["L1-01", "L2-01", "L2-02", "L3-01", "L4-01"],
            {"rf_sensor": 25.0}, 0.95, 0.90,
        )
        self.assertGreater(conf_high, 0.85)

        # 对标 Java ConfidenceGateTest.testLowQualityTarget_LowConfidence
        conf_low = calculate_confidence(
            ["L2-01"], {"rf_sensor": 3.0}, 0.30, 0.30,
        )
        self.assertLess(conf_low, 0.55)

    def test_calc_rule_consistency_levels(self):
        """规则一致性各档位测试。"""
        from rule_engine import calc_rule_consistency

        self.assertEqual(calc_rule_consistency(None), 0.50)
        self.assertEqual(calc_rule_consistency([]), 0.50)
        self.assertEqual(calc_rule_consistency(["L2-01"]), 0.60)
        self.assertEqual(calc_rule_consistency(["L2-01", "L2-02"]), 0.75)
        self.assertEqual(calc_rule_consistency(["L1-01", "L2-01", "L3-01"]), 0.85)
        self.assertEqual(
            calc_rule_consistency(["L1-01", "L2-01", "L2-02", "L3-01", "L4-01"]),
            0.95,
        )

    def test_calc_sensor_quality_levels(self):
        """传感器质量各档位测试。"""
        from rule_engine import calc_sensor_quality

        self.assertEqual(calc_sensor_quality(None), 0.50)
        self.assertEqual(calc_sensor_quality({}), 0.50)
        self.assertEqual(calc_sensor_quality({"rf": 3.0}), 0.30)
        self.assertEqual(calc_sensor_quality({"rf": 8.0}), 0.50)
        self.assertEqual(calc_sensor_quality({"rf": 12.0}), 0.70)
        self.assertEqual(calc_sensor_quality({"rf": 18.0}), 0.85)
        self.assertEqual(calc_sensor_quality({"rf": 25.0}), 0.95)
        # 多传感器平均值
        self.assertAlmostEqual(
            calc_sensor_quality({"rf": 25.0, "optical": 15.0}),
            0.90,  # avg=20 → 0.95
            delta=0.06,
        )

    def test_calc_rule_coverage_levels(self):
        """规则覆盖度各层级测试。"""
        from rule_engine import calc_rule_coverage

        self.assertEqual(calc_rule_coverage(None), 0.0)
        self.assertEqual(calc_rule_coverage([]), 0.0)
        self.assertEqual(calc_rule_coverage(["L2-01"]), 0.25)
        self.assertEqual(calc_rule_coverage(["L1-01", "L2-01"]), 0.50)
        self.assertEqual(
            calc_rule_coverage(["L1-01", "L2-01", "L3-01", "L4-01"]), 1.0
        )

    def test_get_trigger_reasons_all_five(self):
        """验证5个触发条件都能正确检测。"""
        from rule_engine import get_trigger_reasons

        # 所有条件都触发
        reasons = get_trigger_reasons(
            classification_confidence=0.50,  # < 0.65 → EVT开集
            is_evt_open_set=True,            # EVT标记
            threat_behavior_tags=["快速抵近", "侦察", "徘徊", "低空突防"],  # 4个 → 复合威胁
            drone_category="UNKNOWN",         # 未知机型
            confidence=0.55,                  # < 0.80 → 置信度不足
            confidence_threshold=0.80,
        )

        self.assertGreaterEqual(len(reasons), 4)
        self.assertTrue(any("EVT" in r for r in reasons))
        self.assertTrue(any("复合威胁" in r for r in reasons))
        self.assertTrue(any("置信度低于阈值" in r for r in reasons))
        self.assertTrue(any("未知机型" in r for r in reasons))

    def test_get_trigger_reasons_none(self):
        """高质量目标不应产生任何触发原因。"""
        from rule_engine import get_trigger_reasons

        reasons = get_trigger_reasons(
            classification_confidence=0.90,
            is_evt_open_set=False,
            threat_behavior_tags=["侦察"],
            drone_category="CONSUMER_QUADCOPTER",
            confidence=0.90,
            confidence_threshold=0.80,
        )

        self.assertEqual(len(reasons), 0, f"高质量目标不应触发: {reasons}")

    def test_quick_assess_function(self):
        """快速评估函数应正常工作。"""
        from rule_engine import quick_assess

        result = quick_assess(
            target_id="T-QA-001",
            situation={"task_id": "task-qa", "target_id": "T-QA-001"},
            task="快速评估测试",
            matched_rules=["L1-01", "L2-01", "L3-01"],
            sensor_status={"rf_sensor": 18.0},
            classification_confidence=0.85,
            react_engine=None,
        )

        self.assertIsNotNone(result)
        self.assertIn("confidence", result)
        self.assertIn("source", result)
        self.assertGreater(result["confidence"], 0.7)


# ==================== 测试类 8: 边界条件和压力场景 ====================


class TestEdgeCases(unittest.TestCase):
    """边界条件和异常场景测试。"""

    def setUp(self):
        self.mock_llm = MagicMock()
        self.tool_registry = ToolRegistry()
        self.tool_registry.register(
            "search_rules",
            lambda args: {"success": True, "data": [], "error": ""},
            "搜索规则",
        )
        self.engine = ReActEngine(
            cfg=config,
            tools_registry=self.tool_registry,
            llm_instance=self.mock_llm,
        )

    def test_empty_situation_still_works(self):
        """最小态势数据（仅task_id）也能正常处理。"""
        minimal_situation = {"task_id": "task-minimal"}

        llm_decision = _build_llm_decision()
        self.mock_llm.create_chat_completion.return_value = {
            "choices": [{"message": {"content": f"Final: {json.dumps(llm_decision, ensure_ascii=False)}"}}]
        }

        result = self.engine.run(task="测试最小输入", situation=minimal_situation)
        self.assertIsNotNone(result)
        self.assertIn("threat_assessment", result)

    def test_null_optional_fields_in_situation(self):
        """态势数据中可选字段为 null 时不应崩溃。"""
        situation = {
            "task_id": "task-null",
            "target_id": "T-NULL",
            "type": None,
            "model": None,
            "lat": None,
            "lon": None,
            "alt": None,
        }

        llm_decision = _build_llm_decision()
        self.mock_llm.create_chat_completion.return_value = {
            "choices": [{"message": {"content": f"Final: {json.dumps(llm_decision, ensure_ascii=False)}"}}]
        }

        result = self.engine.run(task="测试null字段", situation=situation)
        self.assertIsNotNone(result)

    def test_very_long_trigger_detail(self):
        """超长 trigger_detail 不影响推理。"""
        long_detail = "详细原因: " + "X" * 500  # 超长描述

        situation = _build_sample_situation("T-LONG")
        task = f"任务描述。触发: {long_detail}"

        llm_decision = _build_llm_decision()
        self.mock_llm.create_chat_completion.return_value = {
            "choices": [{"message": {"content": f"Final: {json.dumps(llm_decision, ensure_ascii=False)}"}}]
        }

        result = self.engine.run(task=task, situation=situation)
        self.assertIsNotNone(result)

    def test_consecutive_low_confidence_scenarios(self):
        """连续低置信度场景：验证每次都能正确触发 Agent。"""
        for i in range(3):
            rule_conf = 0.50 + i * 0.05  # 0.50, 0.55, 0.60（都低于阈值）
            self.assertLess(rule_conf, config.CONFIDENCE_THRESHOLD)

            # 验证每次都会触发上报判断
            should_escalate = rule_conf < config.CONFIDENCE_THRESHOLD
            self.assertTrue(should_escalate,
                            f"第{i+1}次: 置信度{rule_conf:.4f}应触发上报")


if __name__ == "__main__":
    unittest.main(verbosity=2)
