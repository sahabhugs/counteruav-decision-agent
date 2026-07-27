"""
simulate_action 工具单元测试
测试反制行动效果预测、风险评估、设备匹配和边界情况处理。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_src_dir = Path(__file__).resolve().parent.parent / "src"
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))


class TestSimulateAction(unittest.TestCase):
    """测试 simulate_action 工具。"""

    def setUp(self):
        from tools.simulate_action import simulate_action
        self.simulate_action = simulate_action

    # ========== 参数校验 ==========

    def test_empty_target_id(self):
        """测试空目标ID。"""
        result = self.simulate_action({
            "target_id": "",
            "action_type": "rf_jamming_full_band",
        })
        self.assertFalse(result["success"])
        self.assertIn("target_id", result.get("error", ""))

    def test_empty_action_type(self):
        """测试空行动类型。"""
        result = self.simulate_action({
            "target_id": "T001",
            "action_type": "",
        })
        self.assertFalse(result["success"])
        self.assertIn("action_type", result.get("error", ""))

    def test_unknown_action_type(self):
        """测试未知的行动类型。"""
        result = self.simulate_action({
            "target_id": "T001",
            "action_type": "unknown_action_xyz",
        })
        self.assertFalse(result["success"])
        self.assertIn("不支持", result.get("error", ""))

    # ========== 正常模拟 ==========

    def test_rf_jamming_simulation(self):
        """测试射频干扰模拟。"""
        result = self.simulate_action({
            "target_id": "T001",
            "action_type": "rf_jamming_full_band",
            "device_id": "RF-JAM-001",
            "_situation": {
                "targets": [{
                    "target_id": "T001",
                    "lat": 39.9080, "lon": 116.4090, "alt": 120.0,
                    "speed_ms": 22.0,
                    "rf_signature": {"frequency_mhz": 5850, "bandwidth_mhz": 40},
                    "drone_type": "unknown",
                }],
                "available_devices": [{
                    "device_id": "RF-JAM-001",
                    "type": "rf_jammer",
                    "status": "ONLINE",
                    "position": {"lat": 39.9050, "lon": 116.4080, "alt_m": 30},
                    "effective_range_m": 3000,
                    "frequency_coverage": ["2.4GHz", "5.8GHz"],
                    "max_erp_w": 500,
                }],
            },
        })

        self.assertTrue(result["success"])
        data = result["data"]
        self.assertEqual(data["target_id"], "T001")
        self.assertEqual(data["action_type"], "rf_jamming_full_band")
        self.assertIn("estimated_effectiveness", data)
        self.assertGreaterEqual(data["estimated_effectiveness"], 0.0)
        self.assertLessEqual(data["estimated_effectiveness"], 1.0)
        self.assertIn("effectiveness_factors", data)
        self.assertIn("risks", data)
        self.assertIn("predicted_outcome", data)

    def test_gnss_spoofing_simulation(self):
        """测试 GNSS 诱骗模拟。"""
        result = self.simulate_action({
            "target_id": "T002",
            "action_type": "gnss_spoofing",
            "_situation": {
                "targets": [{
                    "target_id": "T002",
                    "lat": 39.9030, "lon": 116.4080, "alt": 200.0,
                    "speed_ms": 10.0,
                    "drone_type": "consumer_quadcopter",
                }],
                "available_devices": [{
                    "device_id": "GNSS-SPOOF-001",
                    "type": "gnss_spoofer",
                    "status": "ONLINE",
                    "position": {"lat": 39.9050, "lon": 116.4080, "alt_m": 30},
                    "effective_range_m": 5000,
                }],
            },
        })

        self.assertTrue(result["success"])
        data = result["data"]
        self.assertEqual(data["action_type"], "gnss_spoofing")
        self.assertIn("estimated_effectiveness", data)

    def test_laser_destruction_simulation(self):
        """测试激光摧毁模拟。"""
        result = self.simulate_action({
            "target_id": "T003",
            "action_type": "laser_destruction",
            "_situation": {
                "targets": [{
                    "target_id": "T003",
                    "lat": 39.9060, "lon": 116.4070, "alt": 300.0,
                    "speed_ms": 15.0,
                    "drone_type": "military_fixed_wing",
                }],
                "available_devices": [{
                    "device_id": "LASER-001",
                    "type": "laser",
                    "status": "ONLINE",
                    "position": {"lat": 39.9050, "lon": 116.4080, "alt_m": 30},
                    "effective_range_m": 2000,
                }],
                "environment": {"weather": "clear", "is_night": False},
            },
        })

        self.assertTrue(result["success"])
        data = result["data"]
        self.assertEqual(data["action_type"], "laser_destruction")
        # 激光是硬杀伤，应标记高风险
        risks = data.get("risks", {})
        self.assertIn("escalation_risk", risks)

    # ========== 风险评估 ==========

    def test_civilian_area_restriction(self):
        """测试民用区域限制评估。"""
        result = self.simulate_action({
            "target_id": "T004",
            "action_type": "laser_destruction",
            "_situation": {
                "targets": [{
                    "target_id": "T004",
                    "lat": 39.9060, "lon": 116.4070, "alt": 80.0,
                    "speed_ms": 5.0,
                    "drone_type": "consumer_quadcopter",
                    "is_over_civilian_area": True,
                }],
                "environment": {"terrain_type": "urban"},
            },
        })

        self.assertTrue(result["success"])
        data = result["data"]
        risks = data.get("risks", {})
        self.assertEqual(risks.get("civilian_interference_risk"), "HIGH")
        # 民用区域 + 激光 → 效果应该被降权
        self.assertLess(data.get("estimated_effectiveness", 1.0), 0.8,
                        "民用区域上空的硬杀伤应显著降低效果评分")

    def test_device_offline_effect(self):
        """测试设备离线时的模拟结果。"""
        result = self.simulate_action({
            "target_id": "T005",
            "action_type": "rf_jamming_selective",
            "device_id": "RF-JAM-002",
            "_situation": {
                "targets": [{
                    "target_id": "T005",
                    "lat": 39.9080, "lon": 116.4100, "alt": 150.0,
                    "speed_ms": 18.0,
                    "drone_type": "consumer_quadcopter",
                }],
                "available_devices": [{
                    "device_id": "RF-JAM-002",
                    "type": "rf_jammer",
                    "status": "FAULT",
                    "position": {"lat": 39.9050, "lon": 116.4080, "alt_m": 30},
                    "effective_range_m": 3000,
                }],
            },
        })

        self.assertTrue(result["success"])
        data = result["data"]
        self.assertAlmostEqual(data["estimated_effectiveness"], 0.0,
                              msg="故障设备的预期效果应为 0")

    def test_target_out_of_range(self):
        """测试目标超出设备有效范围。"""
        result = self.simulate_action({
            "target_id": "T006",
            "action_type": "rf_jamming_full_band",
            "_situation": {
                "targets": [{
                    "target_id": "T006",
                    "lat": 39.9500, "lon": 116.4500, "alt": 200.0,
                    "speed_ms": 10.0,
                    "drone_type": "unknown",
                }],
                "available_devices": [{
                    "device_id": "RF-JAM-003",
                    "type": "rf_jammer",
                    "status": "ONLINE",
                    "position": {"lat": 39.9050, "lon": 116.4080, "alt_m": 30},
                    "effective_range_m": 500,
                }],
            },
        })

        self.assertTrue(result["success"])
        data = result["data"]
        self.assertLess(data["estimated_effectiveness"], 0.3,
                       "超远距离目标的模拟效果应非常低")
        self.assertIn("range_factor", data["effectiveness_factors"])

    # ========== 自动设备匹配 ==========

    def test_auto_device_selection(self):
        """测试不指定 device_id 时自动匹配设备。"""
        result = self.simulate_action({
            "target_id": "T007",
            "action_type": "rf_jamming_full_band",
            "_situation": {
                "targets": [{
                    "target_id": "T007",
                    "lat": 39.9060, "lon": 116.4090, "alt": 100.0,
                    "speed_ms": 12.0,
                    "drone_type": "consumer_quadcopter",
                }],
                "available_devices": [
                    {
                        "device_id": "LASER-002",
                        "type": "laser",
                        "status": "ONLINE",
                        "position": {"lat": 39.9050, "lon": 116.4080, "alt_m": 30},
                        "effective_range_m": 2000,
                    },
                    {
                        "device_id": "RF-JAM-004",
                        "type": "rf_jammer",
                        "status": "ONLINE",
                        "position": {"lat": 39.9050, "lon": 116.4080, "alt_m": 30},
                        "effective_range_m": 3000,
                    },
                ],
            },
        })

        self.assertTrue(result["success"])
        data = result["data"]
        # 应自动选择 RF 干扰器（匹配 action_type）
        self.assertEqual(data["device_id"], "RF-JAM-004")

    # ========== 不同操作类型效果评估 ==========

    def test_net_capture_simulation(self):
        """测试网捕模拟（短距离限制）。"""
        result = self.simulate_action({
            "target_id": "T008",
            "action_type": "net_capture",
            "_situation": {
                "targets": [{
                    "target_id": "T008",
                    "lat": 39.9055, "lon": 116.4085, "alt": 40.0,
                    "speed_ms": 3.0, "drone_type": "consumer_quadcopter",
                    "distance_m": 300,  # 近距离
                }],
            },
        })

        self.assertTrue(result["success"])
        data = result["data"]
        # 网捕对低速近距离目标效果应 > 0.5
        self.assertGreater(data["estimated_effectiveness"], 0.5)

    def test_microwave_simulation(self):
        """测试微波毁伤模拟。"""
        result = self.simulate_action({
            "target_id": "T009",
            "action_type": "high_power_microwave",
            "_situation": {
                "targets": [{
                    "target_id": "T009",
                    "lat": 39.9060, "lon": 116.4090, "alt": 200.0,
                    "speed_ms": 18.0, "drone_type": "cluster_swarm",
                }],
            },
        })

        self.assertTrue(result["success"])
        data = result["data"]
        self.assertIn("estimated_effectiveness", data)
        risks = data.get("risks", {})
        self.assertIn("collateral_damage_risk", risks)

    def test_kinetic_impact_simulation(self):
        """测试动能打击模拟。"""
        result = self.simulate_action({
            "target_id": "T010",
            "action_type": "kinetic_impact",
            "_situation": {
                "targets": [{
                    "target_id": "T010",
                    "lat": 39.9060, "lon": 116.4070, "alt": 500.0,
                    "speed_ms": 35.0, "drone_type": "military_fixed_wing",
                }],
            },
        })

        self.assertTrue(result["success"])
        data = result["data"]
        risks = data.get("risks", {})
        self.assertEqual(risks.get("collateral_damage_risk"), "HIGH")
        self.assertEqual(risks.get("escalation_risk"), "最高级别武力使用")


class TestSimulateActionEdgeCases(unittest.TestCase):
    """测试 simulate_action 边界情况。"""

    def setUp(self):
        from tools.simulate_action import simulate_action
        self.simulate_action = simulate_action

    def test_no_devices_available(self):
        """测试无可用设备时的模拟（应返回基于通用参数的粗略估算）。"""
        result = self.simulate_action({
            "target_id": "T011",
            "action_type": "rf_jamming_full_band",
            "_situation": {
                "targets": [{
                    "target_id": "T011",
                    "lat": 39.9060, "lon": 116.4070, "alt": 100.0,
                    "speed_ms": 10.0, "drone_type": "unknown",
                    "distance_m": 2000,
                }],
                "available_devices": [],
            },
        })

        self.assertTrue(result["success"])
        data = result["data"]
        # 无设备时返回粗略估算（基于类型匹配），效果应 < 0.5（无设备）
        self.assertLess(data["estimated_effectiveness"], 0.5)
        self.assertEqual(data["device_id"], "")

    def test_minimal_situation(self):
        """测试最少态势信息。"""
        result = self.simulate_action({
            "target_id": "T012",
            "action_type": "monitor",
            "_situation": {
                "targets": [{
                    "target_id": "T012",
                    "lat": 39.9000, "lon": 116.4000, "alt": 500.0,
                    "speed_ms": 5.0, "drone_type": "unknown",
                }],
            },
        })

        self.assertTrue(result["success"])
        data = result["data"]
        self.assertEqual(data["action_type"], "monitor")
        self.assertIn("estimated_effectiveness", data)


if __name__ == "__main__":
    unittest.main(verbosity=2)
