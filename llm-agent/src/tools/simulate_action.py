"""
行动效果预测工具 (Tool 6)
预测反制行动对目标的效果和风险。

基于查表 + 简化物理模型：
- 型号匹配: 查询知识库中的 vulnerable_to / resistant_to
- 距离衰减: 自由空间路径损耗公式
- 干扰/信号比: JSR = ERP_jammer - ERP_signal + G_jammer - L_propagation
"""

from __future__ import annotations

import logging
import math
from typing import Any, Optional

logger = logging.getLogger(__name__)

# 自由空间路径损耗基准
_FSPL_BASE = 32.45  # 1km @ 1MHz 的损耗(dB)

# 动作类型到设备类型的映射
_ACTION_DEVICE_MAP = {
    "rf_jamming_full_band": "rf_jammer",
    "rf_jamming_selective": "rf_jammer",
    "rf_jamming_2.4g_5.8g": "rf_jammer",
    "rf_jamming_5.8g": "rf_jammer",
    "gnss_spoofing": "gnss_spoofer",
    "laser_destruction": "laser",
    "net_capture": "net_capture",
    "high_power_microwave": "microwave",
    "kinetic_impact": "kinetic",
    "monitor": "sensor",
    "wait": "any",
}

# 操作风险分级
_ACTION_RISK = {
    "rf_jamming_full_band": {"risk_level": "M-半可逆", "civilian_risk": "MEDIUM"},
    "rf_jamming_selective": {"risk_level": "L-可逆", "civilian_risk": "LOW"},
    "rf_jamming_2.4g_5.8g": {"risk_level": "L-可逆", "civilian_risk": "LOW"},
    "rf_jamming_5.8g": {"risk_level": "L-可逆", "civilian_risk": "LOW"},
    "gnss_spoofing": {"risk_level": "L-可逆", "civilian_risk": "LOW"},
    "laser_destruction": {"risk_level": "H-不可逆", "civilian_risk": "HIGH"},
    "net_capture": {"risk_level": "M-半可逆", "civilian_risk": "LOW"},
    "high_power_microwave": {"risk_level": "M-半可逆", "civilian_risk": "MEDIUM"},
    "kinetic_impact": {"risk_level": "H-不可逆", "civilian_risk": "HIGH"},
    "monitor": {"risk_level": "L-可逆", "civilian_risk": "LOW"},
    "wait": {"risk_level": "L-可逆", "civilian_risk": "LOW"},
}

# 目标类型对不同策略的脆弱性（-1=未知, 0=无效, 0.5=部分有效, 1=完全有效）
_TYPE_VULNERABILITY: dict[str, dict[str, float]] = {
    "consumer_quadcopter": {
        "rf_jamming": 1.0, "gnss_spoofing": 0.9,
        "laser_destruction": 0.3, "net_capture": 0.7,
        "microwave": 0.8, "kinetic": 0.6,
    },
    "diy_fpv_quadcopter": {
        "rf_jamming": 0.8, "gnss_spoofing": 0.0,
        "laser_destruction": 0.6, "net_capture": 0.4,
        "microwave": 0.7, "kinetic": 0.7,
    },
    "military_fixed_wing": {
        "rf_jamming": 0.4, "gnss_spoofing": 0.6,
        "laser_destruction": 0.8, "net_capture": 0.0,
        "microwave": 0.5, "kinetic": 0.9,
    },
    "cluster_swarm": {
        "rf_jamming": 0.7, "gnss_spoofing": 0.2,
        "laser_destruction": 0.2, "net_capture": 0.0,
        "microwave": 0.9, "kinetic": 0.3,
    },
    "unknown": {
        "rf_jamming": 0.6, "gnss_spoofing": 0.4,
        "laser_destruction": 0.5, "net_capture": 0.3,
        "microwave": 0.6, "kinetic": 0.5,
    },
}


def _normalize_action_type(action_type: str) -> str:
    """将动作类型映射到脆弱性表的键。"""
    if action_type.startswith("rf_jamming"):
        return "rf_jamming"
    if "gnss" in action_type or "spoof" in action_type:
        return "gnss_spoofing"
    if "laser" in action_type:
        return "laser_destruction"
    if "net" in action_type:
        return "net_capture"
    if "microwave" in action_type:
        return "microwave"
    if "kinetic" in action_type:
        return "kinetic"
    return action_type


def _get_action_family(action_type: str) -> str:
    """获取动作族（用于脆弱性查表）。"""
    return _normalize_action_type(action_type)


def _calc_range_factor(target_dist_m: float, device_range_m: float) -> float:
    """计算距离因子 (0-1)。
    目标在有效范围内=1.0，超出后指数衰减。
    """
    if device_range_m <= 0:
        return 0.0
    if target_dist_m <= device_range_m:
        return 1.0
    # 超出范围后指数衰减
    ratio = target_dist_m / device_range_m
    return math.exp(-2.0 * (ratio - 1.0))


def _calc_jsr(
    jammer_erp_w: float, target_dist_m: float, freq_mhz: float
) -> float:
    """估算干扰/信号比 (dB)。

    考虑自由空间路径损耗。

    Args:
        jammer_erp_w: 干扰机 ERP（瓦）。
        target_dist_m: 目标距离（米）。
        freq_mhz: 目标频率（MHz）。

    Returns:
        JSR (dB)。
    """
    if jammer_erp_w <= 0 or target_dist_m <= 0:
        return 0.0

    # 自由空间路径损耗
    dist_km = target_dist_m / 1000.0
    if dist_km < 0.001:
        dist_km = 0.001
    fspl = _FSPL_BASE + 20 * math.log10(dist_km) + 20 * math.log10(freq_mhz)

    # 假设目标信号 ERP 为 0.1W（无人机典型发射功率）
    signal_erp_w = 0.1
    jammer_erp_db = 10 * math.log10(jammer_erp_w)
    signal_erp_db = 10 * math.log10(signal_erp_w)

    # JSR = 干扰功率 - 信号功率（在目标处）
    # 简化模型：ERP_jammer(dB) - FSPL - (ERP_signal(dB) - FSPL)
    # = ERP_jammer(dB) - ERP_signal(dB)
    # 实际上两者的 FSPL 相同（距离 = 频率近似），所以抵消
    jsr = jammer_erp_db - signal_erp_db
    return max(0.0, jsr)


def _estimate_obstruction(terrain_type: str, weather: str) -> float:
    """估算地形/天气遮挡因子 (0-1)。"""
    factor = 1.0
    if terrain_type == "urban":
        factor *= 0.80
    elif terrain_type == "mountain":
        factor *= 0.70
    elif terrain_type == "forest":
        factor *= 0.85

    if weather in ("rain", "fog", "haze"):
        factor *= 0.75
    elif weather == "snow":
        factor *= 0.65
    elif weather == "storm":
        factor *= 0.50

    return factor


def simulate_action(args: dict) -> dict:
    """预测反制行动对目标的效果和风险。

    Args:
        args: 参数字典，包含:
            - target_id (str): 目标 ID（必需）
            - action_type (str): 反制行动类型（必需）
            - device_id (str, 可选): 指定设备 ID，None 则自动匹配
            - _situation (dict): 态势上下文

    Returns:
        模拟结果字典。
    """
    target_id = args.get("target_id", "")
    action_type = args.get("action_type", "")
    device_id = args.get("device_id", None)

    if not target_id:
        return {"success": False, "data": None, "error": "参数 'target_id' 不能为空"}
    if not action_type:
        return {"success": False, "data": None, "error": "参数 'action_type' 不能为空"}

    # 检查行动类型是否已知
    if action_type not in _ACTION_DEVICE_MAP and action_type not in _ACTION_RISK:
        return {
            "success": False, "data": None,
            "error": f"不支持的行动类型: {action_type}，支持: {list(_ACTION_DEVICE_MAP.keys())}",
        }

    situation = args.get("_situation", args.get("situation", {}))

    # 查找目标
    targets = situation.get("targets", [])
    target = None
    for t in targets:
        if t.get("target_id", t.get("id", "")) == target_id:
            target = t
            break
    if target is None:
        if "lat" in situation:
            target = situation
        else:
            return {
                "success": False, "data": None,
                "error": f"态势数据中未找到目标 '{target_id}'",
            }

    # 提取目标信息
    drone_type = str(target.get("drone_type", target.get("type", "unknown")))
    target_lat = float(target.get("lat", target.get("position", {}).get("lat", 0)))
    target_lon = float(target.get("lon", target.get("position", {}).get("lon", 0)))
    target_alt = float(target.get("alt", target.get("alt_m",
                         target.get("position", {}).get("alt_m",
                         target.get("position", {}).get("alt", 100.0)))))
    target_speed = float(target.get("speed_ms", target.get("speed", 0)))

    rf = target.get("rf_signature", {})
    target_freq = float(rf.get("frequency_mhz", 2400.0)) if isinstance(rf, dict) else 2400.0

    is_civilian_area = bool(target.get("is_over_civilian_area", False))

    # 查找/匹配设备
    devices = situation.get("available_devices", situation.get("devices", []))
    matched_device: Optional[dict] = None

    if device_id:
        for d in devices:
            if d.get("device_id", d.get("id", "")) == device_id:
                matched_device = d
                break
    else:
        # 自动匹配：寻找匹配 action_type 的在线设备
        desired_type = _ACTION_DEVICE_MAP.get(action_type, "rf_jammer")
        for d in devices:
            d_type = str(d.get("type", "")).lower()
            d_status = str(d.get("status", "")).upper()
            if desired_type in d_type and d_status == "ONLINE":
                matched_device = d
                break
        # 如果没有匹配的，取第一个在线设备
        if matched_device is None:
            for d in devices:
                if str(d.get("status", "")).upper() == "ONLINE":
                    matched_device = d
                    break

    device_id_matched = matched_device.get("device_id", matched_device.get("id", "")) if matched_device else ""

    # --- 计算各效果因子 ---

    # 1. 设备可用性
    device_available = 1.0
    if matched_device and str(matched_device.get("status", "")).upper() in ("FAULT", "OFFLINE"):
        device_available = 0.0
    elif not matched_device and action_type not in ("monitor", "wait"):
        device_available = 0.0

    # 2. 距离因子
    device_pos = matched_device.get("position", {}) if matched_device else {}
    device_lat = float(device_pos.get("lat", 0)) if device_pos else 0.0
    device_lon = float(device_pos.get("lon", 0)) if device_pos else 0.0

    if device_lat and device_lon:
        from .predict_trajectory import haversine_distance
        target_dist = haversine_distance(target_lat, target_lon, device_lat, device_lon)
    else:
        # 使用距离字段
        target_dist = float(target.get("distance_m", target.get("distance", 3000.0)))

    device_range = float(matched_device.get("effective_range_m", 3000.0)) if matched_device else 3000.0
    range_factor = _calc_range_factor(target_dist, device_range) if device_available > 0 else 0.0

    # 3. 类型匹配因子
    action_family = _get_action_family(action_type)
    type_vuln = _TYPE_VULNERABILITY.get(drone_type, _TYPE_VULNERABILITY["unknown"])
    type_match_factor = type_vuln.get(action_family, 0.5)

    # 4. 干扰/信号比
    jammer_erp = 500.0
    if matched_device:
        jammer_erp = float(matched_device.get("max_erp_w", matched_device.get("power_w", 500.0)))
    jsr_db = _calc_jsr(jammer_erp, target_dist, target_freq)
    jsr_factor = min(1.0, jsr_db / 20.0)  # 20dB JSR 即满分

    # 5. 遮挡因子
    env = situation.get("environment", {})
    terrain = str(env.get("terrain_type", env.get("terrain", "open")))
    weather = str(env.get("weather", "clear"))
    obstruction_factor = _estimate_obstruction(terrain, weather)

    # --- 综合效果评估 ---
    factors = {
        "device_available": round(device_available, 2),
        "range_factor": round(range_factor, 2),
        "type_match_factor": round(type_match_factor, 2),
        "jam_to_signal_ratio_db": round(jsr_db, 1),
        "jsr_factor": round(jsr_factor, 2),
        "obstruction_factor": round(obstruction_factor, 2),
    }

    # 需要设备的行动：无设备则效果为 0
    needs_device = action_type not in ("monitor", "wait")
    if needs_device and device_available <= 0:
        # 用户指定了设备但设备不可用 → 效果为 0
        if device_id:
            effectiveness = 0.0
        else:
            # 未指定设备且无可用设备：基于通用参数做粗略估算
            if action_type == "net_capture":
                effectiveness = max(0.0, min(1.0, (800 - target_dist) / 600))
            elif action_type == "laser_destruction":
                effectiveness = type_match_factor * _estimate_obstruction(terrain, weather) * 0.3
            elif action_type.startswith("rf_jamming"):
                effectiveness = type_match_factor * 0.4
            else:
                effectiveness = type_match_factor * 0.3
    elif action_type == "net_capture" and target_dist > 800:
        # 网捕：超过 800m 几乎不可能
        effectiveness = max(0.0, 1.0 - (target_dist - 200) / 600)
    else:
        # 乘法模型：距离因子作为基础因子，乘以类型匹配和环境
        base_factor = range_factor if needs_device else 1.0
        effectiveness = base_factor * (
            0.35 * type_match_factor
            + 0.20 * jsr_factor
            + 0.15 * obstruction_factor
        ) + 0.30 * type_match_factor
        effectiveness = max(0.0, min(1.0, effectiveness))

    # 民用区域惩罚（硬杀伤）
    risk_info = _ACTION_RISK.get(action_type, {"risk_level": "M-半可逆", "civilian_risk": "MEDIUM"})
    if is_civilian_area and risk_info["risk_level"] == "H-不可逆":
        effectiveness *= 0.3
    elif is_civilian_area and risk_info["risk_level"] == "M-半可逆":
        effectiveness *= 0.7

    effectiveness = max(0.0, min(1.0, effectiveness))

    # --- 风险评估 ---
    risks = {
        "civilian_interference_risk": "HIGH" if is_civilian_area and risk_info["risk_level"] == "H-不可逆"
        else "MEDIUM" if is_civilian_area else "LOW",
        "friendly_comm_interference": action_type.startswith("rf_jamming_full"),
        "collateral_damage_risk": "HIGH" if risk_info["risk_level"] == "H-不可逆"
        else "MEDIUM" if risk_info["risk_level"] == "M-半可逆"
        else "LOW",
        "escalation_risk": "最高级别武力使用" if action_type == "kinetic_impact"
        else "可能导致目标坠毁" if action_type == "laser_destruction"
        else "目标可能退化为惯性导航" if action_type == "gnss_spoofing"
        else "干扰后目标可能失控/返航",
    }

    # --- 预期结果描述 ---
    effectiveness_label = (
        "高" if effectiveness >= 0.7
        else "中等" if effectiveness >= 0.4
        else "低" if effectiveness >= 0.1
        else "几乎无效"
    )
    if action_type == "monitor":
        predicted_outcome = f"保持监测态势，效果确定性高（无主动干预）"
    elif effectiveness >= 0.7:
        predicted_outcome = f"预计效果{effectiveness_label}（成功率约 {effectiveness:.0%}），建议优先采用"
    elif effectiveness >= 0.4:
        predicted_outcome = f"预计效果{effectiveness_label}（成功率约 {effectiveness:.0%}），需结合备选方案"
    else:
        predicted_outcome = f"预计效果{effectiveness_label}（成功率约 {effectiveness:.0%}），建议寻找替代方案"

    data = {
        "target_id": target_id,
        "action_type": action_type,
        "risk_level": risk_info["risk_level"],
        "device_id": device_id_matched,
        "device_status": str(matched_device.get("status", "N/A")) if matched_device else "N/A",
        "estimated_effectiveness": round(effectiveness, 3),
        "effectiveness_factors": factors,
        "target_distance_m": round(target_dist, 1),
        "risks": risks,
        "predicted_outcome": predicted_outcome,
        "limitations": _get_limitations(action_type, drone_type, effectiveness),
        "_source": "查表+简化物理模型",
    }

    logger.info(
        f"行动模拟完成: target={target_id}, action={action_type}, "
        f"effectiveness={effectiveness:.3f}, risk={risk_info['risk_level']}"
    )
    return {"success": True, "data": data, "error": ""}


def _get_limitations(action_type: str, drone_type: str, effectiveness: float) -> list[str]:
    """生成局限性说明。"""
    limitations = []

    if action_type.startswith("rf_jamming"):
        limitations.append("目标可能已预设自主航线（无遥控仍可飞行）")
        if drone_type == "military_fixed_wing":
            limitations.append("军用无人机可能有跳频/扩频抗干扰能力")
    elif action_type == "gnss_spoofing":
        limitations.append("目标若配备惯性导航或视觉导航则效果有限")
        if drone_type == "diy_fpv_quadcopter":
            limitations.append("FPV 竞速无人机通常不依赖 GNSS，诱骗几乎无效")
    elif action_type == "laser_destruction":
        limitations.append("需要稳定视线跟踪，受天气和烟雾影响大")
        limitations.append("碎片可能坠落造成附带损伤")
    elif action_type == "net_capture":
        limitations.append("有效距离短（<500m），仅低速近距离目标适用")
    elif action_type == "high_power_microwave":
        limitations.append("功耗极大，可能影响友方电子设备")
        limitations.append("需视线条件")

    if effectiveness < 0.4:
        limitations.append("综合效果评估偏低，建议考虑备选方案或组合策略")

    return limitations
