#!/usr/bin/env python3
"""
反无人机决策系统 - 性能基准测试脚本

功能：
1. 生成合成测试数据（无人机目标、设备、场景）
2. 规则引擎基准测试（测量 P50/P95/P99 延迟，含预热阶段）
3. LLM Agent 基准测试（可选，测量推理延迟和 token 数）
4. 端到端流水线基准测试（完整流程延迟分解：分类 -> 策略匹配 -> LLM -> 决策）
5. 输出彩色控制台报告（rich/tabulate）和 JSON 报告文件

设计说明：
- 支持纯模拟模式：无需外部服务即可运行完整基准测试
- 含真实 HTTP 调用支持：配置 --llm-endpoint 可对真实 LLM 服务进行测试
- 预热功能：前 N 次迭代不纳入统计，排除冷启动影响
- 统计维度：P50/P95/P99/均值/最小/最大/标准差

依赖（均为可选）：
- rich：彩色表格控制台输出
- tabulate：备选表格输出
- httpx / requests：真实 HTTP 负载测试
"""

from __future__ import annotations

import argparse
import copy
import json
import logging
import math
import os
import random
import statistics
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# 日志配置
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("benchmark")

# ---------------------------------------------------------------------------
# 可选依赖检测
# ---------------------------------------------------------------------------
try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text
    _RICH_AVAILABLE = True
except ImportError:
    _RICH_AVAILABLE = False

try:
    from tabulate import tabulate as _tabulate_fn
    _TABULATE_AVAILABLE = True
except ImportError:
    _TABULATE_AVAILABLE = False

try:
    import httpx
    _HAS_HTTPX = True
except ImportError:
    _HAS_HTTPX = False


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _get_script_dir() -> Path:
    """获取当前脚本所在目录的绝对路径。"""
    return Path(__file__).resolve().parent


def _compute_percentiles(values: List[float]) -> Dict[str, float]:
    """计算延迟的 P50、P95、P99 以及均值/标准差/最小/最大。"""
    if not values:
        return {
            "p50": 0, "p95": 0, "p99": 0,
            "mean": 0, "stdev": 0, "min": 0, "max": 0, "count": 0,
        }
    n = len(values)
    sorted_vals = sorted(values)
    return {
        "p50": sorted_vals[int(n * 0.50)],
        "p95": sorted_vals[min(int(n * 0.95), n - 1)],
        "p99": sorted_vals[min(int(n * 0.99), n - 1)],
        "mean": statistics.mean(sorted_vals),
        "stdev": statistics.stdev(sorted_vals) if n > 1 else 0,
        "min": min(sorted_vals),
        "max": max(sorted_vals),
        "count": n,
    }


# ---------------------------------------------------------------------------
# 合成数据生成器
# ---------------------------------------------------------------------------

class SyntheticDataGenerator:
    """合成测试数据生成器。

    生成模拟的无人机目标、反制设备和综合场景，
    覆盖主流无人机类型的分类特征和威胁行为模式。
    """

    # 无人机型号池（覆盖军用/消费级/DIY/未知等类别）
    DRONE_TYPE_POOL = [
        # 消费级
        {"type": "dji-mavic-3", "category": "CONSUMER_QUADCOPTER", "weight_kg": 0.9},
        {"type": "dji-mini-3-pro", "category": "CONSUMER_QUADCOPTER", "weight_kg": 0.249},
        {"type": "dji-phantom-4", "category": "CONSUMER_QUADCOPTER", "weight_kg": 1.38},
        {"type": "dji-matrice-300", "category": "COMMERCIAL_HEXACOPTER", "weight_kg": 6.3},
        {"type": "autel-evo-ii", "category": "CONSUMER_QUADCOPTER", "weight_kg": 1.1},
        # DIY/FPV
        {"type": "diy-fpv-5inch", "category": "DIY_FPV", "weight_kg": 0.6},
        {"type": "diy-fpv-7inch", "category": "DIY_FPV", "weight_kg": 0.8},
        # 军用
        {"type": "orlan-10", "category": "MILITARY_FIXED_WING", "weight_kg": 14.0},
        {"type": "military_fixed_wing", "category": "MILITARY_FIXED_WING", "weight_kg": 20.0},
        # 未知
        {"type": "unknown", "category": "UNKNOWN", "weight_kg": 0},
        # 集群
        {"type": "cluster_swarm_unit", "category": "CLUSTER_SWARM", "weight_kg": 0.3},
    ]

    # 威胁行为池
    THREAT_BEHAVIORS_POOL = [
        {"tag": "RAPID_APPROACH", "severity_range": (0.7, 1.0)},
        {"tag": "ALTITUDE_DIVE", "severity_range": (0.5, 1.0)},
        {"tag": "SIGNAL_ANOMALY", "severity_range": (0.3, 0.9)},
        {"tag": "LOITERING", "severity_range": (0.2, 0.7)},
        {"tag": "ERRATIC_MOVEMENT", "severity_range": (0.4, 0.9)},
        {"tag": "LOW_ALTITUDE", "severity_range": (0.3, 0.8)},
        {"tag": "HEADING_CHANGE", "severity_range": (0.2, 0.6)},
        {"tag": "DWELL_OBSERVE", "severity_range": (0.3, 0.8)},
    ]

    # 设备类型注册表
    DEVICE_REGISTRY = [
        {
            "device_id": "RF-JAM-001",
            "type": "rf_jammer",
            "effective_range_m": 3000,
            "frequency_coverage": ["400MHz", "900MHz", "1.2GHz", "1.5GHz", "2.4GHz", "5.8GHz"],
            "max_erp_w": 500,
        },
        {
            "device_id": "RF-JAM-002",
            "type": "rf_jammer",
            "effective_range_m": 2500,
            "frequency_coverage": ["2.4GHz", "5.8GHz"],
            "max_erp_w": 200,
        },
        {
            "device_id": "GNSS-SPOOF-001",
            "type": "gnss_spoofer",
            "effective_range_m": 5000,
            "supported_constellations": ["GPS", "GLONASS", "BeiDou", "Galileo"],
        },
        {
            "device_id": "GNSS-SPOOF-002",
            "type": "gnss_spoofer",
            "effective_range_m": 4000,
            "supported_constellations": ["GPS", "BeiDou"],
        },
        {
            "device_id": "LASER-001",
            "type": "laser_destruction",
            "effective_range_m": 2000,
            "power_kw": 30,
        },
        {
            "device_id": "LASER-002",
            "type": "laser_destruction",
            "effective_range_m": 1500,
            "power_kw": 10,
        },
        {
            "device_id": "NET-001",
            "type": "net_capture",
            "effective_range_m": 500,
        },
        {
            "device_id": "MICROWAVE-001",
            "type": "high_power_microwave",
            "effective_range_m": 1500,
            "power_kw": 100,
        },
    ]

    # 调制类型
    MODULATION_TYPES = [
        "OFDM", "FM_Analog", "DSSS", "FHSS",
        "QPSK", "unknown_digital", "OcuSync", "Lightbridge",
    ]

    # 环境类型
    TERRAIN_TYPES = ["urban", "suburban", "rural", "coastal", "mountain"]
    WEATHER_TYPES = ["clear", "cloudy", "rain", "fog", "snow"]

    # RF 频段候选
    RF_FREQUENCIES_MHZ = [433, 900, 1200, 1500, 2400, 2450, 5800, 5850]
    RF_BANDWIDTHS_MHZ = [10, 20, 40, 80]

    def __init__(self, seed: Optional[int] = None):
        self._rng = random.Random(seed)

    # ---- 目标生成 ----

    def generate_target(self, index: int, defense_center: Optional[Dict] = None) -> Dict:
        """生成单个合成无人机目标。

        Args:
            index: 目标序号
            defense_center: 防御中心坐标 {"lat": y, "lon": x, "alt_m": z}

        Returns:
            目标字典
        """
        dc = defense_center or {"lat": 39.9042, "lon": 116.4074, "alt_m": 50}
        dc_lat, dc_lon = dc["lat"], dc["lon"]

        # 随机位置：防御中心周围约 0.1 度（约 11km）
        lat = dc_lat + self._rng.uniform(-0.1, 0.1)
        lon = dc_lon + self._rng.uniform(-0.1, 0.1)
        alt_m = round(self._rng.uniform(20, 500), 1)

        # 距离
        distance = self._haversine(lat, lon, dc_lat, dc_lon)

        # 速度与径向速度
        speed_ms = round(self._rng.uniform(2.0, 45.0), 1)
        heading_deg = round(self._rng.uniform(0, 360), 1)
        bearing = self._bearing(lat, lon, dc_lat, dc_lon)
        angle_diff = math.radians(bearing - heading_deg)
        radial_speed_ms = round(speed_ms * math.cos(angle_diff), 1)

        # 无人机类型
        drone_entry = self._rng.choice(self.DRONE_TYPE_POOL)

        # 威胁行为
        num_bh = self._rng.randint(1, min(4, len(self.THREAT_BEHAVIORS_POOL)))
        selected_bh = self._rng.sample(self.THREAT_BEHAVIORS_POOL, num_bh)
        behaviors = []
        for bh in selected_bh:
            sr = bh["severity_range"]
            behaviors.append({"tag": bh["tag"], "severity": round(self._rng.uniform(*sr), 2)})

        # RF 特征
        rf_freq = self._rng.choice(self.RF_FREQUENCIES_MHZ)
        rf_bw = self._rng.choice(self.RF_BANDWIDTHS_MHZ)
        rf_mod = self._rng.choice(self.MODULATION_TYPES)
        rf_snr = round(self._rng.uniform(-5, 25), 1)

        # 置信度和开集识别
        max_conf = round(self._rng.uniform(0.2, 0.95), 2)

        return {
            "target_id": f"T-BM-{index:04d}",
            "track_id": f"TRK-BM-{index:04d}",
            "detection_time": datetime.now(timezone.utc).isoformat(),
            "position": {"lat": round(lat, 6), "lon": round(lon, 6), "alt_m": alt_m},
            "velocity_ms": speed_ms,
            "heading_deg": heading_deg,
            "radial_speed_ms": radial_speed_ms,
            "distance_m": round(distance, 1),
            "classification": {
                "drone_type": drone_entry["type"],
                "max_class_confidence": max_conf,
                "is_evt_open_set": max_conf < 0.5,
                "top3_classes": [
                    {"type": drone_entry["type"], "confidence": max_conf},
                    {"type": "unknown", "confidence": round(1 - max_conf, 2)},
                    {"type": "consumer_quadcopter", "confidence": round(self._rng.uniform(0.05, 0.2), 2)},
                ],
            },
            "threat_behaviors": behaviors,
            "rf_signature": {
                "frequency_mhz": rf_freq,
                "bandwidth_mhz": rf_bw,
                "modulation_type": rf_mod,
                "snr_db": rf_snr,
            },
            "is_over_civilian_area": self._rng.random() < 0.3,
            "dwell_time_s": self._rng.randint(10, 600),
            "droneCategory": drone_entry["category"],
        }

    # ---- 设备生成 ----

    def generate_devices(self, count: int) -> List[Dict]:
        """从设备注册表中选取指定数量的设备并随机化位置。"""
        available = copy.deepcopy(self.DEVICE_REGISTRY)
        self._rng.shuffle(available)
        selected = available[: min(count, len(available))]
        for dev in selected:
            dev["status"] = self._rng.choice(
                ["ONLINE"] * 8 + ["BUSY"] + ["STANDBY"]
            )
            dev["position"] = {
                "lat": round(39.9042 + self._rng.uniform(-0.01, 0.01), 6),
                "lon": round(116.4074 + self._rng.uniform(-0.01, 0.01), 6),
                "alt_m": round(self._rng.uniform(10, 50), 1),
            }
            dev["current_target_id"] = None
        return selected

    # ---- 场景生成 ----

    def generate_scenario(self, targets: List[Dict], devices: List[Dict]) -> Dict:
        """生成包含多目标和设备的完整场景。"""
        return {
            "request_id": f"sc-bm-{self._rng.randint(10000, 99999)}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "defense_center": {"lat": 39.9042, "lon": 116.4074, "alt_m": 50},
            "protected_zone": {
                "center": {"lat": 39.9042, "lon": 116.4074},
                "radius_m": 5000,
            },
            "targets": targets,
            "available_devices": devices,
            "environment": {
                "terrain_type": self._rng.choice(self.TERRAIN_TYPES),
                "weather": self._rng.choice(self.WEATHER_TYPES),
                "em_environment_noise_db": round(self._rng.uniform(-100, -70), 1),
                "is_night": self._rng.random() < 0.4,
            },
            "mode": "auto",
        }

    # ---- 几何计算 ----

    @staticmethod
    def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """计算地球表面两点之间的 Haversine 距离（米）。"""
        R = 6371000.0
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlam = math.radians(lon2 - lon1)
        a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    @staticmethod
    def _bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """计算从 (lat1,lon1) 到 (lat2,lon2) 的方位角（度，0=正北）。"""
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dlam = math.radians(lon2 - lon1)
        y = math.sin(dlam) * math.cos(phi2)
        x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlam)
        return (math.degrees(math.atan2(y, x)) + 360) % 360


# ---------------------------------------------------------------------------
# 模拟规则引擎（本地执行，不依赖外部服务）
# ---------------------------------------------------------------------------

class MockRuleEngine:
    """模拟 Drools 规则引擎。

    使用轻量级条件判断模拟 L2 威胁等级分类和 L3 策略匹配的计算逻辑。
    模拟的延迟参数基于典型 Java Drools 规则引擎的性能特征。
    """

    def __init__(self, seed: Optional[int] = None):
        self._rng = random.Random(seed)

    def classify_threat(self, target: Dict) -> Dict:
        """模拟威胁等级分类（替代真实 Drools 推理）。

        决策逻辑基于：
        - 距离：<500m 极高危，<1000m 高危，<3000m 中危，>5000m 低危
        - 径向速度：>15m/s 升级
        - 类别：军用/集群 > 未知 > 消费级
        - 行为标签：累加严重度

        Returns:
            {threat_level, threat_label, threat_score, threat_tags, confidence}
        """
        distance = target.get("distance_m", 5000)
        radial_speed = abs(target.get("radial_speed_ms", 0))
        category = target.get("droneCategory", target.get("classification", {}).get("drone_type", "unknown")).upper()
        behaviors = target.get("threat_behaviors", [])
        dwell_time = target.get("dwell_time_s", 0)
        is_over_civilian = target.get("is_over_civilian_area", False)

        threat_score = 0.0
        threat_tags: List[str] = []

        # 距离因素
        if distance < 500:
            threat_score += 0.30
            threat_tags.append("IMMINENT")
        elif distance < 1000:
            threat_score += 0.20
        elif distance < 3000:
            threat_score += 0.10

        # 速度因素
        if radial_speed > 15:
            threat_score += 0.25
            threat_tags.append("RAPID_APPROACH")
        elif radial_speed > 5:
            threat_score += 0.10

        # 类别因素
        if "MILITARY" in category:
            threat_score += 0.20
            threat_tags.append("HOSTILE_PLATFORM")
        elif "UNKNOWN" in category:
            threat_score += 0.15
            threat_tags.append("UNKNOWN_PLATFORM")
        elif "CLUSTER" in category or "SWARM" in category:
            threat_score += 0.30
            threat_tags.append("CLUSTER_SWARM")

        # 行为因素
        for bh in behaviors:
            threat_score += bh.get("severity", 0) * 0.05

        # 驻留时间 > 5分钟
        if dwell_time > 300:
            threat_score += 0.05
            threat_tags.append("PERSISTENT")

        # 平民区域标记
        if is_over_civilian:
            threat_tags.append("CIVILIAN_AREA")

        # 钳制
        threat_score = min(max(threat_score, 0.0), 1.0)

        # 映射到威胁等级 1-5
        if threat_score >= 0.8:
            threat_level, label = 5, "极危"
        elif threat_score >= 0.6:
            threat_level, label = 4, "极高"
        elif threat_score >= 0.4:
            threat_level, label = 3, "高危"
        elif threat_score >= 0.2:
            threat_level, label = 2, "中危"
        else:
            threat_level, label = 1, "低危"

        confidence = round(0.7 + self._rng.uniform(0, 0.28), 2)

        return {
            "threat_level": threat_level,
            "threat_label": label,
            "threat_score": round(threat_score, 3),
            "threat_tags": threat_tags,
            "confidence": confidence,
        }

    def match_strategy(self, target: Dict, threat_result: Dict, devices: List[Dict]) -> Dict:
        """模拟策略匹配（基于目标类别和威胁等级）。"""
        tl = threat_result.get("threat_level", 1)
        category = target.get("droneCategory", "UNKNOWN").upper()
        distance = target.get("distance_m", 5000)

        # 策略映射矩阵
        if tl <= 1:
            primary = "MONITOR_ONLY"
            secondary = None
        elif "MILITARY" in category or "UNKNOWN" in category:
            primary = "FULL_BAND_JAMMING"
            secondary = "LASER_DESTRUCTION" if distance < 2000 else "GNSS_SPOOFING"
        elif "CLUSTER" in category or "SWARM" in category:
            primary = "FULL_BAND_JAMMING"
            secondary = "HIGH_POWER_MICROWAVE"
        elif "FPV" in category:
            primary = "RF_JAMMING_5G8"
            secondary = "NET_CAPTURE"
        else:
            primary = "RF_JAMMING_2G4_5G8"
            secondary = "GNSS_SPOOFING"

        online = [d for d in devices if d.get("status") == "ONLINE"]

        return {
            "primary_strategy": primary,
            "secondary_strategy": secondary,
            "available_device_count": len(online),
            "recommended_device_ids": [d["device_id"] for d in online[:2]],
        }


# ---------------------------------------------------------------------------
# LLM Agent 模拟/真实客户端
# ---------------------------------------------------------------------------

class LLMAgentClient:
    """LLM Agent 客户端。

    支持两种模式：
    1. 模拟模式（默认）：模拟推理延迟和 token 计数，无网络请求
    2. 真实模式：连接真实 LLM Agent 服务进行负载测试
    """

    def __init__(self, llm_endpoint: Optional[str] = None, seed: Optional[int] = None):
        self.llm_endpoint = llm_endpoint
        self._rng = random.Random(seed)

    def is_reachable(self) -> bool:
        """检查 LLM 服务是否可达。"""
        if not self.llm_endpoint:
            return False
        try:
            client = self._get_client()
            resp = client.get(f"{self.llm_endpoint}/health", timeout=2)
            return resp.status_code == 200
        except Exception:
            return False

    def _get_client(self):
        """获取 HTTP 客户端。"""
        if _HAS_HTTPX:
            return httpx.Client(timeout=30)
        import urllib.request
        return None  # 回退到 urllib

    def consult(self, scenario: Dict, target: Dict, threat_result: Dict) -> Tuple[Dict, float, int]:
        """LLM 咨询（模拟或真实）。

        Returns:
            (decision_dict, latency_seconds, total_tokens)
        """
        if self.llm_endpoint and self.is_reachable():
            return self._real_consult(scenario, target, threat_result)
        return self._mock_consult(scenario, target, threat_result)

    def _mock_consult(self, scenario: Dict, target: Dict, threat_result: Dict) -> Tuple[Dict, float, int]:
        """模拟 LLM 推理。

        模拟参数基于 t5-tiny/qwen2-0.5b 等轻量模型在 CPU 上的典型表现：
        - 输入 ~400-800 tokens
        - 输出 ~150-400 tokens
        - 推理延迟 ~150-800ms（带随机抖动）
        """
        # 模拟推理延迟：基础 + 复杂度 + 高斯噪声
        num_targets = len(scenario.get("targets", []))
        num_behaviors = len(target.get("threat_behaviors", []))
        base_lat = self._rng.uniform(0.15, 0.45)
        complexity = num_targets * 0.015 + num_behaviors * 0.008
        noise = self._rng.gauss(0, 0.04)
        latency = max(0.03, base_lat + complexity + noise)

        # 模拟 token 数
        prompt_tokens = self._rng.randint(400, 800)
        completion_tokens = self._rng.randint(150, 400)
        total_tokens = prompt_tokens + completion_tokens

        tl = threat_result.get("threat_level", 1)

        decision = {
            "decision_id": f"dm-{self._rng.randint(100000, 999999)}",
            "target_id": target.get("target_id", ""),
            "threat_assessment": {
                "threat_score": threat_result.get("threat_score", 0.5),
                "threat_level": tl,
                "confidence": threat_result.get("confidence", 0.8),
                "key_factors": threat_result.get("threat_tags", []),
                "uncertainty_flags": ["SIMULATED_BENCHMARK"],
            },
            "recommended_action": {
                "action_type": "全频段压制" if tl >= 4 else "选择性干扰",
                "priority": min(tl + 1, 10),
                "devices": [],
                "parameters": {"mode": "benchmark_test"},
                "expected_effect": "模拟基准测试效果（非真实推理）",
            },
            "reasoning_chain": [
                "步骤1: 分析目标运动特征和RF签名 [模拟]",
                "步骤2: 评估威胁等级并比对历史数据 [模拟]",
                "步骤3: 在策略空间寻优匹配最佳反制方案 [模拟]",
                "步骤4: 校验ROE约束并生成决策建议 [模拟]",
            ],
            "data_sources": ["synthetic_benchmark_data"],
        }
        return decision, latency, total_tokens

    def _real_consult(self, scenario: Dict, target: Dict, threat_result: Dict) -> Tuple[Dict, float, int]:
        """发起真实的 LLM API 调用。"""
        t0 = time.perf_counter()
        try:
            payload = {
                "request_id": scenario.get("request_id", ""),
                "target": target,
                "threat_assessment": threat_result,
                "available_devices": scenario.get("available_devices", []),
                "environment": scenario.get("environment", {}),
            }

            if _HAS_HTTPX:
                with httpx.Client(timeout=30) as client:
                    resp = client.post(
                        f"{self.llm_endpoint}/v1/decide",
                        json=payload,
                    )
                    elapsed = time.perf_counter() - t0
                    if resp.status_code == 200:
                        data = resp.json()
                        tokens = data.get("usage", {}).get("total_tokens", 0)
                        return data.get("decision", data), elapsed, tokens
                    return {}, elapsed, 0
            else:
                import urllib.request
                req = urllib.request.Request(
                    f"{self.llm_endpoint}/v1/decide",
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=30) as resp:
                    elapsed = time.perf_counter() - t0
                    data = json.loads(resp.read())
                    tokens = data.get("usage", {}).get("total_tokens", 0)
                    return data.get("decision", data), elapsed, tokens
        except Exception as e:
            elapsed = time.perf_counter() - t0
            logger.warning("LLM API 调用失败: %s", e)
            return {}, elapsed, 0


# ---------------------------------------------------------------------------
# 基准测试运行器
# ---------------------------------------------------------------------------

class BenchmarkRunner:
    """基准测试运行器。

    管理测试生命周期：数据生成 -> 预热 -> 正式测试 -> 统计 -> 报告。
    """

    def __init__(
        self,
        num_targets: int = 100,
        num_iterations: int = 10,
        warmup: int = 5,
        seed: Optional[int] = None,
        llm_endpoint: Optional[str] = None,
        skip_llm: bool = False,
    ):
        if warmup >= num_iterations:
            logger.warning(
                "预热次数 (%d) >= 迭代次数 (%d)，将没有有效样本",
                warmup, num_iterations,
            )

        self.num_targets = num_targets
        self.num_iterations = num_iterations
        self.warmup = warmup
        self.seed = seed

        self.generator = SyntheticDataGenerator(seed=seed)
        self.rule_engine = MockRuleEngine(seed=seed)
        self.llm_agent = LLMAgentClient(llm_endpoint=llm_endpoint, seed=seed)
        self.skip_llm = skip_llm

        # 延迟样本收集
        self.classification_latencies: List[float] = []   # ms
        self.strategy_match_latencies: List[float] = []   # ms
        self.llm_latencies: List[float] = []              # ms
        self.llm_token_counts: List[int] = []
        self.e2e_latencies: List[float] = []              # ms
        self.e2e_breakdown: Dict[str, List[float]] = defaultdict(list)  # ms

    # ---- 进度条 ----

    def _iter_with_progress(self, iterable, total: int, desc: str = ""):
        """带进度条的迭代器（rich > tqdm > plain）。"""
        if _RICH_AVAILABLE:
            from rich.progress import (
                Progress, SpinnerColumn, TextColumn,
                BarColumn, TimeElapsedColumn,
            )
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                TextColumn("({task.completed}/{task.total})"),
                TimeElapsedColumn(),
            ) as progress:
                task = progress.add_task(desc, total=total)
                for item in iterable:
                    yield item
                    progress.update(task, advance=1)
        elif _TQDM_AVAILABLE:
            try:
                from tqdm import tqdm
                yield from tqdm(iterable, total=total, desc=desc)
            except ImportError:
                yield from iterable
        else:
            yield from iterable

    # ---- 单次端到端 ----

    def _run_single_e2e(self, target: Dict, devices: List[Dict], scenario: Dict) -> Dict:
        """运行单次端到端流水线并计时各阶段。

        Returns:
            {target_id, threat_result, strategy, llm_decision, breakdown, total_latency}
        """
        breakdown: Dict[str, float] = {}

        # 阶段 1: 威胁分类（规则引擎或等效计算）
        t0 = time.perf_counter()
        threat_result = self.rule_engine.classify_threat(target)
        # 模拟 Drools RETE 网络匹配延迟（典型 5-50ms）
        time.sleep(self.generator._rng.uniform(0.005, 0.05))
        breakdown["classification"] = (time.perf_counter() - t0) * 1000

        # 阶段 2: 策略匹配
        t0 = time.perf_counter()
        strategy = self.rule_engine.match_strategy(target, threat_result, devices)
        time.sleep(self.generator._rng.uniform(0.003, 0.03))
        breakdown["strategy_match"] = (time.perf_counter() - t0) * 1000

        # 阶段 3: LLM 咨询（可选）
        llm_decision = None
        if not self.skip_llm:
            t0 = time.perf_counter()
            llm_decision, llm_lat, llm_tokens = self.llm_agent.consult(
                scenario, target, threat_result,
            )
            breakdown["llm_consult"] = (time.perf_counter() - t0) * 1000
        else:
            breakdown["llm_consult"] = 0.0

        # 阶段 4: 决策汇总
        t0 = time.perf_counter()
        time.sleep(self.generator._rng.uniform(0.001, 0.01))
        breakdown["decision"] = (time.perf_counter() - t0) * 1000

        total = sum(breakdown.values())

        return {
            "target_id": target["target_id"],
            "threat_result": threat_result,
            "strategy": strategy,
            "llm_decision": llm_decision,
            "breakdown": breakdown,
            "total_latency_ms": total,
        }

    # ---- 子基准测试 ----

    def bench_classification(self, targets: List[Dict]) -> None:
        """威胁分类基准。"""
        logger.info(">>> [1/4] 威胁等级分类基准")
        for iteration in self._iter_with_progress(
            range(self.num_iterations), self.num_iterations, "威胁分类"
        ):
            for target in targets:
                t0 = time.perf_counter()
                _ = self.rule_engine.classify_threat(target)
                lat_ms = (time.perf_counter() - t0) * 1000
                if iteration >= self.warmup:
                    self.classification_latencies.append(lat_ms)

    def bench_strategy_match(self, targets: List[Dict], devices: List[Dict]) -> None:
        """策略匹配基准。"""
        logger.info(">>> [2/4] 策略匹配基准")
        for iteration in self._iter_with_progress(
            range(self.num_iterations), self.num_iterations, "策略匹配"
        ):
            for target in targets:
                threat = self.rule_engine.classify_threat(target)
                t0 = time.perf_counter()
                _ = self.rule_engine.match_strategy(target, threat, devices)
                lat_ms = (time.perf_counter() - t0) * 1000
                if iteration >= self.warmup:
                    self.strategy_match_latencies.append(lat_ms)

    def bench_llm(self, targets: List[Dict], devices: List[Dict]) -> None:
        """LLM Agent 基准。"""
        if self.skip_llm:
            logger.info(">>> [3/4] 跳过 LLM Agent 基准 (--no-llm)")
            return

        logger.info(">>> [3/4] LLM Agent 基准")
        scenario = self.generator.generate_scenario(targets[:1], devices)
        # LLM 测试使用较少目标（模拟真实场景中的触发频率）
        llm_targets = targets[: min(20, len(targets))]

        for iteration in self._iter_with_progress(
            range(self.num_iterations), self.num_iterations, "LLM Agent"
        ):
            for target in llm_targets:
                threat = self.rule_engine.classify_threat(target)
                _, lat_s, tokens = self.llm_agent.consult(scenario, target, threat)
                if iteration >= self.warmup:
                    self.llm_latencies.append(lat_s * 1000)
                    self.llm_token_counts.append(tokens)

    def bench_e2e(self, targets: List[Dict], devices: List[Dict]) -> None:
        """端到端流水线基准。"""
        logger.info(">>> [4/4] 端到端流水线基准")
        scenario = self.generator.generate_scenario(targets[: min(10, len(targets))], devices)
        e2e_targets = targets[: min(30, len(targets))]

        for iteration in self._iter_with_progress(
            range(self.num_iterations), self.num_iterations, "端到端"
        ):
            for target in e2e_targets:
                result = self._run_single_e2e(target, devices, scenario)
                if iteration >= self.warmup:
                    self.e2e_latencies.append(result["total_latency_ms"])
                    for stage, lat in result["breakdown"].items():
                        self.e2e_breakdown[stage].append(lat)

    # ---- 主流程 ----

    def run(self) -> Dict:
        """执行完整基准测试并返回报告字典。"""
        overall_start = time.perf_counter()

        logger.info("=" * 60)
        logger.info("  反无人机决策系统 - 性能基准测试")
        logger.info("  目标: %d | 迭代: %d | 预热: %d | LLM: %s",
                     self.num_targets, self.num_iterations, self.warmup,
                     "跳过" if self.skip_llm else "启用")
        logger.info("=" * 60)

        # 数据生成
        logger.info(">>> 生成合成测试数据...")
        t0 = time.perf_counter()
        targets = [
            self.generator.generate_target(i)
            for i in range(self.num_targets)
        ]
        devices = self.generator.generate_devices(4)
        gen_time = time.perf_counter() - t0
        logger.info("生成 %d 个目标 + %d 个设备，耗时 %.2f 秒",
                     len(targets), len(devices), gen_time)

        # 执行各阶段基准
        self.bench_classification(targets)
        self.bench_strategy_match(targets, devices)
        self.bench_llm(targets, devices)
        self.bench_e2e(targets, devices)

        total_time = time.perf_counter() - overall_start

        # 计算统计
        report = self._build_report(targets, devices, gen_time, total_time)
        return report

    def _build_report(self, targets, devices, gen_time: float, total_time: float) -> Dict:
        """构建完整的 JSON 报告结构。"""
        # 各阶段统计
        cls_stats = _compute_percentiles(self.classification_latencies)
        strat_stats = _compute_percentiles(self.strategy_match_latencies)
        llm_stats = _compute_percentiles(self.llm_latencies)
        e2e_stats = _compute_percentiles(self.e2e_latencies)

        # 端到端阶段分解
        breakdown_stats = {}
        for stage, lats in self.e2e_breakdown.items():
            breakdown_stats[stage] = _compute_percentiles(lats)

        # Token 统计
        token_info = {}
        if self.llm_token_counts:
            token_info = {
                "mean": statistics.mean(self.llm_token_counts),
                "median": statistics.median(self.llm_token_counts),
                "total": sum(self.llm_token_counts),
                "samples": len(self.llm_token_counts),
                "estimated_cost_usd": round(
                    sum(self.llm_token_counts) * 0.0015 / 1000, 4
                ),  # 假设 $1.5/M tokens
            }

        report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "configuration": {
                "num_targets": self.num_targets,
                "num_iterations": self.num_iterations,
                "warmup": self.warmup,
                "seed": self.seed,
                "skip_llm": self.skip_llm,
                "llm_endpoint": self.llm_agent.llm_endpoint,
            },
            "data_generation": {
                "time_seconds": round(gen_time, 3),
                "targets_generated": len(targets),
                "devices_configured": len(devices),
            },
            "results": {
                "threat_classification": {
                    "label": "威胁等级分类",
                    "unit": "ms",
                    **cls_stats,
                },
                "strategy_match": {
                    "label": "策略匹配",
                    "unit": "ms",
                    **strat_stats,
                },
                "llm_agent": {
                    "label": "LLM Agent 咨询",
                    "unit": "ms",
                    **llm_stats,
                    "token_stats": token_info if token_info else None,
                },
                "end_to_end_pipeline": {
                    "label": "端到端流水线",
                    "unit": "ms",
                    **e2e_stats,
                    "breakdown": breakdown_stats,
                },
            },
            "total_benchmark_time_seconds": round(total_time, 2),
        }
        return report


# ---------------------------------------------------------------------------
# 控制台报告输出
# ---------------------------------------------------------------------------

def _print_rich_report(report: Dict) -> None:
    """使用 rich 库输出彩色控制台报告。"""
    console = Console()

    # 标题
    console.print(Panel(
        Text("反无人机决策系统 - 性能基准测试报告", style="bold cyan"),
        subtitle=f"生成: {report['timestamp']}",
        border_style="cyan",
    ))

    # 配置
    config = report["configuration"]
    ct = Table(title="测试配置", border_style="blue")
    ct.add_column("参数", style="dim")
    ct.add_column("值", style="bright_white")
    ct.add_row("目标数量", str(config["num_targets"]))
    ct.add_row("迭代次数", str(config["num_iterations"]))
    ct.add_row("预热迭代", str(config["warmup"]))
    ct.add_row("随机种子", str(config["seed"]))
    ct.add_row("跳过 LLM", str(config["skip_llm"]))
    if config.get("llm_endpoint"):
        ct.add_row("LLM 端点", config["llm_endpoint"])
    console.print(ct)

    # 延迟表
    results = report["results"]
    lt = Table(title="延迟统计 (ms)", border_style="green", highlight=True)
    lt.add_column("阶段", style="bold")
    lt.add_column("样本数", justify="right")
    lt.add_column("均值", justify="right")
    lt.add_column("P50", justify="right")
    lt.add_column("P95", justify="right")
    lt.add_column("P99", justify="right")
    lt.add_column("最大", justify="right")

    for key, stats in results.items():
        if not isinstance(stats, dict) or "mean" not in stats:
            continue
        mean_v = stats.get("mean", 0)
        style = "green" if mean_v < 1 else ("yellow" if mean_v < 10 else ("bright_yellow" if mean_v < 100 else "red"))
        lt.add_row(
            stats.get("label", key),
            str(stats.get("count", 0)),
            f"[{style}]{mean_v:.2f}[/{style}]",
            f"{stats.get('p50', 0):.2f}",
            f"{stats.get('p95', 0):.2f}",
            f"{stats.get('p99', 0):.2f}",
            f"{stats.get('max', 0):.2f}",
        )
    console.print(lt)

    # 分解
    bd = results.get("end_to_end_pipeline", {}).get("breakdown", {})
    e2e_p50 = results.get("end_to_end_pipeline", {}).get("p50", 1)
    if bd:
        bdt = Table(title="端到端阶段分解 (P50)", border_style="magenta")
        bdt.add_column("阶段", style="bold")
        bdt.add_column("P50 (ms)", justify="right")
        bdt.add_column("P95 (ms)", justify="right")
        bdt.add_column("占比", justify="right")
        for stage, s in sorted(bd.items()):
            p50v = s.get("p50", 0)
            pct = p50v / e2e_p50 * 100 if e2e_p50 > 0 else 0
            bdt.add_row(stage, f"{p50v:.2f}", f"{s.get('p95', 0):.2f}", f"{pct:.1f}%")
        console.print(bdt)

    # Token 信息
    tok = results.get("llm_agent", {}).get("token_stats")
    if tok:
        tkt = Table(title="LLM Token 统计", border_style="yellow")
        tkt.add_column("指标", style="dim")
        tkt.add_column("值", style="bright_white")
        tkt.add_row("平均 Tokens/次", f"{tok.get('mean', 0):.0f}")
        tkt.add_row("中位数 Tokens/次", f"{tok.get('median', 0):.0f}")
        tkt.add_row("总 Tokens", str(tok.get("total", 0)))
        tkt.add_row("估算成本", f"${tok.get('estimated_cost_usd', 0):.4f}")
        console.print(tkt)

    # 总耗时
    console.print(Panel(
        f"基准测试完成，总耗时 {report.get('total_benchmark_time_seconds', 0):.1f} 秒",
        border_style="bold green",
    ))


def _print_plain_report(report: Dict) -> None:
    """使用 tabulate 或纯文本输出报告。"""
    results = report["results"]
    config = report["configuration"]

    print("=" * 70)
    print("  反无人机决策系统 - 性能基准测试报告")
    print(f"  生成时间: {report['timestamp']}")
    print("=" * 70)
    print(f"\n  配置: targets={config['num_targets']}, "
          f"iterations={config['num_iterations']}, "
          f"warmup={config['warmup']}, skip_llm={config['skip_llm']}")

    headers = ["阶段", "样本数", "均值(ms)", "P50(ms)", "P95(ms)", "P99(ms)", "最大(ms)"]
    rows = []
    for key, stats in results.items():
        if isinstance(stats, dict) and "mean" in stats:
            rows.append([
                stats.get("label", key),
                stats.get("count", 0),
                stats.get("mean", 0),
                stats.get("p50", 0),
                stats.get("p95", 0),
                stats.get("p99", 0),
                stats.get("max", 0),
            ])

    if _TABULATE_AVAILABLE:
        print()
        print(_tabulate_fn(rows, headers=headers, tablefmt="grid",
                           floatfmt=".2f", numalign="right"))
    else:
        print("\n  " + " | ".join(headers))
        print("  " + "-" * 65)
        for row in rows:
            print("  " + " | ".join(f"{c:.2f}" if isinstance(c, float) else str(c) for c in row))

    print(f"\n  总耗时: {report.get('total_benchmark_time_seconds', 0):.1f} 秒")
    print("=" * 70)


def _print_report(report: Dict) -> None:
    """选择合适的输出方式。"""
    if _RICH_AVAILABLE:
        _print_rich_report(report)
    else:
        _print_plain_report(report)


# ---------------------------------------------------------------------------
# 命令行入口
# ---------------------------------------------------------------------------

def main() -> None:
    """主函数。"""
    parser = argparse.ArgumentParser(
        description="反无人机决策系统 - 性能基准测试",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python benchmark.py
  python benchmark.py --targets 200 --iterations 20 --output report.json
  python benchmark.py --no-llm --seed 42
  python benchmark.py --targets 50 --iterations 5 --warmup 2
  python benchmark.py --llm-endpoint http://localhost:8001
        """,
    )

    parser.add_argument(
        "--targets", type=int, default=100,
        help="生成的合成目标数量 (默认: 100)",
    )
    parser.add_argument(
        "--iterations", type=int, default=10,
        help="每个目标的测试迭代次数 (默认: 10)",
    )
    parser.add_argument(
        "--output", type=str, default="benchmark_report.json",
        help="JSON 报告输出路径 (默认: benchmark_report.json)",
    )
    parser.add_argument(
        "--no-llm", action="store_true", default=False,
        help="跳过 LLM Agent 基准测试",
    )
    parser.add_argument(
        "--warmup", type=int, default=5,
        help="预热迭代次数，不纳入统计 (默认: 5)",
    )
    parser.add_argument(
        "--seed", type=int, default=None,
        help="随机种子，固定后结果可复现 (默认: 随机)",
    )
    parser.add_argument(
        "--llm-endpoint", type=str, default=None,
        help="LLM Agent 服务端点（默认: 模拟模式）",
    )

    args = parser.parse_args()

    # 参数校验
    if args.targets < 1:
        logger.error("--targets 必须 >= 1")
        sys.exit(1)
    if args.iterations < 1:
        logger.error("--iterations 必须 >= 1")
        sys.exit(1)

    runner = BenchmarkRunner(
        num_targets=args.targets,
        num_iterations=args.iterations,
        warmup=args.warmup,
        seed=args.seed,
        llm_endpoint=args.llm_endpoint,
        skip_llm=args.no_llm,
    )

    report = runner.run()

    # 控制台输出
    _print_report(report)

    # JSON 输出
    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = Path.cwd() / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    logger.info("JSON 报告已保存到: %s", output_path)

    # 简要总结
    re_stats = report["results"].get("threat_classification", {})
    e2e = report["results"].get("end_to_end_pipeline", {})
    print(f"\n[Summary] 分类 P50={re_stats.get('p50', 0):.2f}ms | "
          f"端到端 P50={e2e.get('p50', 0):.2f}ms P95={e2e.get('p95', 0):.2f}ms P99={e2e.get('p99', 0):.2f}ms")

    sys.exit(0)


if __name__ == "__main__":
    main()
