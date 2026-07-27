"""
轨迹预测工具 (Tool 5)
基于目标当前运动状态做线性外推轨迹预测，计算 CPA 和禁飞区入侵时间。

使用 L1 物理定律层的简单运动学公式：
- lat(t) = lat_0 + v * cos(heading) * t / 111320.0
- lon(t) = lon_0 + v * sin(heading) * t / (111320.0 * cos(lat_0))
- alt(t) = alt_0 + v_vertical * t
"""

from __future__ import annotations

import logging
import math
from typing import Any, Optional

logger = logging.getLogger(__name__)

# 球体半径（米）
_EARTH_RADIUS_M = 6371000.0
# 默认防御中心（北京天安门附近，可通过 situation 中的 defense_center 覆盖）
_DEFAULT_DEFENSE_CENTER = {"lat": 39.9042, "lon": 116.4074, "alt_m": 50.0}


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """计算两点间的大圆距离（米）。

    Args:
        lat1, lon1: 第一点经纬度（度）。
        lat2, lon2: 第二点经纬度（度）。

    Returns:
        两点间距离（米）。
    """
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return _EARTH_RADIUS_M * c


def destination_point(
    lat: float, lon: float, distance_m: float, bearing_deg: float
) -> tuple[float, float]:
    """给定起点、距离和方位角，计算目标点位置。

    Args:
        lat, lon: 起点经纬度（度）。
        distance_m: 距离（米）。
        bearing_deg: 方位角（度，0=北，90=东）。

    Returns:
        (lat, lon) 目标点经纬度（度）。
    """
    bearing = math.radians(bearing_deg)
    phi = math.radians(lat)
    angular_distance = distance_m / _EARTH_RADIUS_M

    phi2 = math.asin(
        math.sin(phi) * math.cos(angular_distance)
        + math.cos(phi) * math.sin(angular_distance) * math.cos(bearing)
    )
    lambda2 = math.radians(lon) + math.atan2(
        math.sin(bearing) * math.sin(angular_distance) * math.cos(phi),
        math.cos(angular_distance) - math.sin(phi) * math.sin(phi2),
    )
    return math.degrees(phi2), math.degrees(lambda2)


def _find_cpa(
    target: dict, defense_center: dict, horizon_s: float
) -> tuple[float, float]:
    """通过采样搜索最近接近点 (CPA)。

    以 0.5s 为步长在 horizon 内采样，找到目标与防御中心距离最近的时刻。

    Args:
        target: 目标信息字典。
        defense_center: 防御中心坐标。
        horizon_s: 预测时间范围。

    Returns:
        (cpa_m, cpa_time_s): CPA 距离和到达 CPA 的时间。
    """
    lat0 = float(target.get("lat", 0))
    lon0 = float(target.get("lon", 0))
    speed = float(target.get("speed_ms", 0))
    heading = float(target.get("heading", 0))

    if speed <= 0:
        # 静止目标，CPA = 当前距离
        current_dist = haversine_distance(
            lat0, lon0,
            float(defense_center["lat"]), float(defense_center["lon"]),
        )
        return current_dist, 0.0

    step_s = 0.5
    min_dist = float("inf")
    min_time = 0.0

    t = 0.0
    while t <= horizon_s:
        dist_m = speed * t * math.cos(math.radians(heading)) / 111320.0
        # 使用 destination_point 更精确
        lat_t, lon_t = destination_point(lat0, lon0, speed * t, heading)
        dist = haversine_distance(
            lat_t, lon_t,
            float(defense_center["lat"]), float(defense_center["lon"]),
        )
        if dist < min_dist:
            min_dist = dist
            min_time = t
        t += step_s

    return min_dist, min_time


def _check_no_fly_zones(
    positions: list[dict],
    no_fly_zones: list[dict],
) -> tuple[bool, Optional[float], Optional[str]]:
    """检查预测轨迹是否进入禁飞区。

    Args:
        positions: 预测位置点列表。
        no_fly_zones: 禁飞区定义列表。

    Returns:
        (will_enter, violation_time_s, zone_description)
    """
    if not no_fly_zones:
        return False, None, None

    for pos in positions:
        lat = pos["lat"]
        lon = pos["lon"]
        for zone in no_fly_zones:
            center = zone.get("center", {})
            radius = float(zone.get("radius_m", 0))
            zone_lat = float(center.get("lat", 0))
            zone_lon = float(center.get("lon", 0))
            dist = haversine_distance(lat, lon, zone_lat, zone_lon)
            if dist <= radius:
                return True, pos["t_s"], zone.get("name", "未命名禁飞区")

    return False, None, None


def predict_trajectory(args: dict) -> dict:
    """预测目标轨迹。

    从 args 的 _situation 字段提取目标运动参数。

    Args:
        args: 参数字典，包含:
            - target_id (str): 目标 ID（必需）
            - _situation (dict): 态势上下文（必需，包含目标和防御中心信息）
            - horizon_s (float, 可选): 预测时间范围，默认 30s

    Returns:
        {
            "success": bool,
            "data": {
                "target_id": str,
                "current_position": dict,
                "predicted_positions": [...],
                "cpa_m": float,
                "cpa_time_s": float,
                "will_enter_no_fly": bool,
                "no_fly_violation_time_s": float | None,
            },
            "error": str,
        }
    """
    target_id = args.get("target_id", "")
    if not target_id:
        return {"success": False, "data": None, "error": "参数 'target_id' 不能为空"}

    horizon_s = float(args.get("horizon_s", 30.0))
    # 限制范围
    horizon_s = max(1.0, min(120.0, horizon_s))

    situation = args.get("_situation", args.get("situation", {}))

    # 查找目标
    targets = situation.get("targets", [])
    target = None
    for t in targets:
        if t.get("target_id", t.get("id", "")) == target_id:
            target = t
            break

    if target is None:
        # 如果只有一个目标且没有 target_id 匹配，使用 situation 本身
        if "lat" in situation:
            target = situation
        else:
            return {
                "success": False,
                "data": None,
                "error": f"态势数据中未找到目标 '{target_id}' 的运动参数",
            }

    # 提取防御中心
    defense_center = situation.get("defense_center", _DEFAULT_DEFENSE_CENTER)

    # 提取目标运动参数
    lat0 = float(target.get("lat", target.get("position", {}).get("lat", 0)))
    lon0 = float(target.get("lon", target.get("position", {}).get("lon", 0)))
    alt0 = float(target.get("alt", target.get("alt_m",
                     target.get("position", {}).get("alt_m",
                     target.get("position", {}).get("alt", 100.0)))))
    speed = float(target.get("speed_ms", target.get("speed", 0)))
    heading = float(target.get("heading", target.get("heading_deg", 0)))
    alt_rate = float(target.get("altitude_rate_ms",
                     target.get("vertical_speed_ms", 0.0)))

    # 生成预测位置（5s, 10s, 15s, 30s 和自定义 horizon 终点）
    time_points = [t for t in [5.0, 10.0, 15.0, 30.0] if t <= horizon_s]
    if horizon_s not in time_points:
        time_points.append(horizon_s)
    time_points.sort()

    predicted_positions: list[dict] = []
    for t_sec in time_points:
        lat_t, lon_t = destination_point(lat0, lon0, speed * t_sec, heading)
        alt_t = alt0 + alt_rate * t_sec
        dist_to_defense = haversine_distance(
            lat_t, lon_t,
            float(defense_center.get("lat", 39.9042)),
            float(defense_center.get("lon", 116.4074)),
        )
        predicted_positions.append({
            "t_s": round(t_sec, 1),
            "lat": round(lat_t, 6),
            "lon": round(lon_t, 6),
            "alt_m": round(alt_t, 1),
            "distance_to_defense_m": round(dist_to_defense, 1),
        })

    # 计算 CPA
    cpa_m, cpa_time_s = _find_cpa(target, defense_center, horizon_s)

    # 检查禁飞区
    no_fly_zones = situation.get("no_fly_zones", [])
    will_enter, violation_time, zone_desc = _check_no_fly_zones(
        predicted_positions, no_fly_zones
    )

    data = {
        "target_id": target_id,
        "current_position": {
            "lat": round(lat0, 6),
            "lon": round(lon0, 6),
            "alt_m": round(alt0, 1),
        },
        "current_distance_to_defense_m": round(
            haversine_distance(
                lat0, lon0,
                float(defense_center.get("lat", 39.9042)),
                float(defense_center.get("lon", 116.4074)),
            ), 1
        ),
        "predicted_positions": predicted_positions,
        "cpa_m": round(cpa_m, 1),
        "cpa_time_s": round(cpa_time_s, 1),
        "will_enter_no_fly": will_enter,
        "no_fly_violation_time_s": round(violation_time, 1) if violation_time else None,
        "no_fly_zone_description": zone_desc,
        "horizon_s": horizon_s,
        "_source": "L1运动学外推",
    }

    logger.info(
        f"轨迹预测完成: target={target_id}, cpa={cpa_m:.1f}m, "
        f"cpa_time={cpa_time_s:.1f}s, no_fly={will_enter}"
    )
    return {"success": True, "data": data, "error": ""}
