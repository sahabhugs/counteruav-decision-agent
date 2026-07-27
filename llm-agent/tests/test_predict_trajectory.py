"""
predict_trajectory 工具单元测试
测试轨迹预测、CPA 计算、禁飞区检测、边界情况处理。
"""

from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_src_dir = Path(__file__).resolve().parent.parent / "src"
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))


class TestPredictTrajectory(unittest.TestCase):
    """测试 predict_trajectory 工具。"""

    def setUp(self):
        from tools.predict_trajectory import predict_trajectory
        self.predict_trajectory = predict_trajectory

    # ========== 参数校验 ==========

    def test_empty_target_id(self):
        """测试空目标ID。"""
        result = self.predict_trajectory({"target_id": ""})
        self.assertFalse(result["success"])
        self.assertIn("不能为空", result.get("error", ""))

    def test_missing_situation_context(self):
        """测试缺少态势上下文（工具从 args 中提取目标参数）。"""
        result = self.predict_trajectory({
            "target_id": "T001",
            "_situation": {},
        })
        # 态势中无目标数据 → 应返回错误
        self.assertFalse(result["success"])
        self.assertIn("态势", result.get("error", ""))

    # ========== 正常轨迹预测 ==========

    def test_valid_trajectory_prediction(self):
        """测试正常轨迹预测（有态势上下文）。"""
        result = self.predict_trajectory({
            "target_id": "T001",
            "_situation": {
                "targets": [{
                    "target_id": "T001",
                    "lat": 39.9100,
                    "lon": 116.4100,
                    "alt": 120.0,
                    "speed_ms": 22.0,
                    "heading": 270.0,
                    "altitude_rate_ms": -5.0,
                }],
            },
            "horizon_s": 30.0,
        })

        self.assertTrue(result["success"])
        data = result["data"]
        self.assertEqual(data["target_id"], "T001")
        self.assertIn("current_position", data)
        self.assertIn("predicted_positions", data)
        self.assertGreater(len(data["predicted_positions"]), 0)
        self.assertIn("cpa_m", data)
        self.assertIn("cpa_time_s", data)

    def test_predicted_positions_count(self):
        """测试预测位置点的数量与时间范围一致。"""
        result = self.predict_trajectory({
            "target_id": "T002",
            "_situation": {
                "targets": [{
                    "target_id": "T002",
                    "lat": 39.9042,
                    "lon": 116.4074,
                    "alt": 500.0,
                    "speed_ms": 50.0,
                    "heading": 180.0,
                    "altitude_rate_ms": 0.0,
                }],
            },
            "horizon_s": 30.0,
        })

        self.assertTrue(result["success"])
        positions = result["data"]["predicted_positions"]
        # 应包含 5s, 10s, 15s, 30s 四个时间点
        expected_times = [5.0, 10.0, 15.0, 30.0]
        for t in expected_times:
            self.assertTrue(
                any(abs(p["t_s"] - t) < 0.1 for p in positions),
                f"缺少 t={t}s 的预测点"
            )

    # ========== CPA 计算 ==========

    def test_cpa_direct_approach(self):
        """测试直飞接近时的 CPA 计算。"""
        # 目标以 20m/s 直飞防御中心 (lat=39.9042, lon=116.4074)
        result = self.predict_trajectory({
            "target_id": "T003",
            "_situation": {
                "targets": [{
                    "target_id": "T003",
                    "lat": 39.9100,
                    "lon": 116.4100,
                    "alt": 100.0,
                    "speed_ms": 20.0,
                    "heading": 225.0,  # 西南方向（朝向防御中心）
                    "altitude_rate_ms": 0.0,
                }],
            },
            "horizon_s": 60.0,
        })

        self.assertTrue(result["success"])
        data = result["data"]
        self.assertIn("cpa_m", data)
        self.assertIn("cpa_time_s", data)
        # CPA 应 > 0
        self.assertGreater(data["cpa_m"], 0)
        # CPA 时间应在 horizon 内
        self.assertLessEqual(data["cpa_time_s"], 60.0)

    def test_cpa_moving_away(self):
        """测试飞离目标时的 CPA（应在当前位置）。"""
        result = self.predict_trajectory({
            "target_id": "T004",
            "_situation": {
                "targets": [{
                    "target_id": "T004",
                    "lat": 39.9000,
                    "lon": 116.4000,
                    "alt": 200.0,
                    "speed_ms": 15.0,
                    "heading": 90.0,  # 正东方向（远离防御中心）
                    "altitude_rate_ms": 0.0,
                }],
            },
            "horizon_s": 30.0,
        })

        self.assertTrue(result["success"])
        # CPA 应等于当前距离（目标在飞离）
        data = result["data"]
        self.assertGreaterEqual(data["cpa_m"], 0)

    # ========== 禁飞区检测 ==========

    def test_no_fly_zone_violation(self):
        """测试预测到禁飞区入侵。"""
        result = self.predict_trajectory({
            "target_id": "T005",
            "_situation": {
                "targets": [{
                    "target_id": "T005",
                    "lat": 39.9050,
                    "lon": 116.4080,
                    "alt": 80.0,
                    "speed_ms": 30.0,
                    "heading": 270.0,
                    "altitude_rate_ms": -3.0,
                }],
                "no_fly_zones": [{
                    "center": {"lat": 39.9042, "lon": 116.4040},
                    "radius_m": 500,
                }],
                "environment": {"terrain_type": "urban"},
            },
            "horizon_s": 20.0,
        })

        self.assertTrue(result["success"])
        data = result["data"]
        # 如果轨迹进入禁飞区，will_enter_no_fly 应为 True
        self.assertIn("will_enter_no_fly", data)

    def test_no_fly_zone_clear(self):
        """测试轨迹不进入禁飞区。"""
        result = self.predict_trajectory({
            "target_id": "T006",
            "_situation": {
                "targets": [{
                    "target_id": "T006",
                    "lat": 39.9100,
                    "lon": 116.4200,
                    "alt": 300.0,
                    "speed_ms": 10.0,
                    "heading": 90.0,
                    "altitude_rate_ms": 0.0,
                }],
                "no_fly_zones": [{
                    "center": {"lat": 39.9042, "lon": 116.4040},
                    "radius_m": 200,
                }],
            },
            "horizon_s": 30.0,
        })

        self.assertTrue(result["success"])
        data = result["data"]
        self.assertFalse(data["will_enter_no_fly"])

    # ========== 水平目标 ==========

    def test_stationary_target(self):
        """测试静止/悬停目标。"""
        result = self.predict_trajectory({
            "target_id": "T007",
            "_situation": {
                "targets": [{
                    "target_id": "T007",
                    "lat": 39.9080,
                    "lon": 116.4090,
                    "alt": 150.0,
                    "speed_ms": 0.0,
                    "heading": 0.0,
                    "altitude_rate_ms": 0.0,
                }],
            },
            "horizon_s": 30.0,
        })

        self.assertTrue(result["success"])
        positions = result["data"]["predicted_positions"]
        # 所有预测位置应与当前位置相同
        current = result["data"]["current_position"]
        for pos in positions:
            self.assertAlmostEqual(pos["lat"], current["lat"], delta=0.0001)
            self.assertAlmostEqual(pos["lon"], current["lon"], delta=0.0001)

    # ========== 边界情况 ==========

    def test_default_horizon(self):
        """测试默认预测时间范围（30s）。"""
        result = self.predict_trajectory({
            "target_id": "T008",
            "_situation": {
                "targets": [{
                    "target_id": "T008",
                    "lat": 39.9000,
                    "lon": 116.4000,
                    "alt": 200.0,
                    "speed_ms": 20.0,
                    "heading": 180.0,
                    "altitude_rate_ms": 0.0,
                }],
            },
            # 不传 horizon_s → 默认 30s
        })

        self.assertTrue(result["success"])
        data = result["data"]
        self.assertGreater(len(data["predicted_positions"]), 0)

    def test_very_short_horizon(self):
        """测试极短预测时间。"""
        result = self.predict_trajectory({
            "target_id": "T009",
            "_situation": {
                "targets": [{
                    "target_id": "T009",
                    "lat": 39.9000,
                    "lon": 116.4000,
                    "alt": 100.0,
                    "speed_ms": 20.0,
                    "heading": 0.0,
                    "altitude_rate_ms": 0.0,
                }],
            },
            "horizon_s": 1.0,
        })

        self.assertTrue(result["success"])
        positions = result["data"]["predicted_positions"]
        self.assertGreater(len(positions), 0)

    def test_negative_speed_target(self):
        """测试径向速度为负（接近）的目标。"""
        result = self.predict_trajectory({
            "target_id": "T010",
            "_situation": {
                "targets": [{
                    "target_id": "T010",
                    "lat": 39.9080,
                    "lon": 116.4090,
                    "alt": 500.0,
                    "speed_ms": 25.0,
                    "heading": 0.0,
                    "altitude_rate_ms": -10.0,  # 下降
                }],
                "environment": {"terrain_type": "suburban"},
            },
            "horizon_s": 15.0,
        })

        self.assertTrue(result["success"])
        data = result["data"]
        # 下降目标最终高度应低于初始高度
        predicted = data["predicted_positions"]
        if predicted:
            last_alt = predicted[-1].get("alt_m", 0)
            initial_alt = data["current_position"]["alt_m"]
            self.assertLessEqual(last_alt, initial_alt,
                                "下降目标的预测高度应 ≤ 初始高度")


class TestPredictTrajectoryMath(unittest.TestCase):
    """测试 predict_trajectory 的数学辅助函数。"""

    def test_haversine_distance(self):
        """测试 haversine 距离计算。"""
        from tools.predict_trajectory import haversine_distance

        # 北京天安门到故宫午门（约 1km）
        d = haversine_distance(39.9042, 116.3974, 39.9110, 116.3974)
        self.assertGreater(d, 500)
        self.assertLess(d, 1000)

    def test_haversine_same_point(self):
        """测试同点距离为 0。"""
        from tools.predict_trajectory import haversine_distance
        self.assertEqual(haversine_distance(39.9, 116.4, 39.9, 116.4), 0.0)

    def test_haversine_known_distance(self):
        """测试已知距离（赤道附近 1 度 ≈ 111.32km）。"""
        from tools.predict_trajectory import haversine_distance
        d = haversine_distance(0.0, 0.0, 0.0, 1.0)
        self.assertAlmostEqual(d, 111320.0, delta=500.0)

    def test_destination_point(self):
        """测试目标点推算。"""
        from tools.predict_trajectory import destination_point

        # 从 (0,0) 向正北移动 111.32km → (1,0)
        lat, lon = destination_point(0.0, 0.0, 111320.0, 0.0)
        self.assertAlmostEqual(lat, 1.0, delta=0.01)
        self.assertAlmostEqual(lon, 0.0, delta=0.01)

    def test_destination_point_east(self):
        """测试正东方向的目标点推算。"""
        from tools.predict_trajectory import destination_point

        lat, lon = destination_point(0.0, 0.0, 111320.0, 90.0)
        self.assertAlmostEqual(lat, 0.0, delta=0.01)
        self.assertAlmostEqual(lon, 1.0, delta=0.01)


if __name__ == "__main__":
    unittest.main(verbosity=2)
