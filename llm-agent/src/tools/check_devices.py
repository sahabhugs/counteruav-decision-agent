"""
设备状态查询工具
查询反无人机设备系统的当前部署和状态信息。
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

try:
    from ..config import config
except (ImportError, ValueError):
    from config import config  # type: ignore[no-redef]

logger = logging.getLogger(__name__)


def check_devices(args: dict) -> dict:
    """查询设备状态。

    无需必要参数，可接受可选的筛选条件。

    Args:
        args: 参数字典，可选:
            - device_type (str, 可选): 筛选设备类型，如"干扰器"/"雷达"/"光电"/"激光"/"诱骗"
            - status (str, 可选): 筛选设备状态，如"在线"/"离线"/"忙碌"/"故障"
            - position_area (str, 可选): 按区域筛选

    Returns:
        设备状态列表字典：
        {
            "success": bool,
            "data": [
                {
                    "device_id": str,
                    "type": str,
                    "status": str,
                    "position": dict,
                    "effective_range_m": float,
                    "current_target_id": str,
                    "health_metrics": dict,
                },
                ...
            ],
            "error": str,
        }
    """
    device_type = args.get("device_type", None)
    status = args.get("status", None)
    position_area = args.get("position_area", None)

    # 优先尝试 HTTP 调用
    try:
        result = _check_devices_http(device_type, status)
        if result["success"]:
            return result
        logger.warning(f"HTTP 设备状态查询失败，使用态势数据回退: {result.get('error', '')}")
    except Exception as e:
        logger.warning(f"HTTP 设备状态查询异常，使用态势数据回退: {e}")

    # 回退到态势数据
    try:
        return _check_devices_from_situation(args)
    except Exception as e:
        logger.error(f"设备状态回退查询也失败: {e}")
        return {
            "success": False,
            "data": None,
            "error": f"设备状态查询均失败: {e}",
        }


def _check_devices_http(
    device_type: Optional[str],
    status_filter: Optional[str],
) -> dict:
    """通过 HTTP 查询规则引擎的设备状态接口。"""
    url = f"{config.RULE_ENGINE_URL}/api/devices/status"
    params: dict[str, str] = {}
    if device_type:
        params["type"] = device_type
    if status_filter:
        params["status"] = status_filter

    try:
        with httpx.Client(timeout=5.0) as client:
            response = client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            # 适配多种响应格式
            devices = data if isinstance(data, list) else data.get("devices", data.get("data", []))

            # 确保每个设备包含必要字段
            normalized: list[dict] = []
            for d in devices:
                normalized.append(_normalize_device_info(d))

            logger.info(f"HTTP 设备状态查询成功: {len(normalized)} 台设备")
            return {"success": True, "data": normalized, "error": ""}

    except httpx.ConnectError:
        return {"success": False, "data": None, "error": f"无法连接规则引擎: {url}"}
    except httpx.TimeoutException:
        return {"success": False, "data": None, "error": "设备状态查询请求超时"}
    except httpx.HTTPStatusError as e:
        return {"success": False, "data": None, "error": f"规则引擎返回错误: {e.response.status_code}"}
    except Exception as e:
        return {"success": False, "data": None, "error": f"HTTP 请求异常: {e}"}


def _check_devices_from_situation(args: dict) -> dict:
    """从态势数据中提取设备信息（回退方案）。

    从调用上下文（args 中的 situation 字段）获取设备列表。
    """
    situation = args.get("_situation", args.get("situation", {}))

    devices = situation.get("devices", situation.get("device_status", []))

    if not devices:
        logger.warning("态势数据中无设备信息")
        return {
            "success": True,
            "data": [],
            "error": "态势数据中未包含设备信息",
        }

    normalized: list[dict] = []
    for d in devices:
        normalized.append(_normalize_device_info(d))

    # 可选的类型筛选
    device_type = args.get("device_type")
    if device_type:
        normalized = [d for d in normalized if d.get("type") == device_type]

    status_filter = args.get("status")
    if status_filter:
        normalized = [d for d in normalized if d.get("status") == status_filter]

    logger.info(f"态势数据设备查询成功: {len(normalized)} 台设备")
    return {"success": True, "data": normalized, "error": ""}


def _normalize_device_info(device: dict) -> dict:
    """标准化设备信息格式。

    Args:
        device: 原始设备信息字典。

    Returns:
        标准化后的设备信息字典。
    """
    return {
        "device_id": str(device.get("device_id", device.get("id", "unknown"))),
        "type": str(device.get("type", device.get("device_type", "未知"))),
        "status": str(device.get("status", device.get("state", "未知"))),
        "position": {
            "lat": float(device.get("lat", device.get("latitude", 0))),
            "lon": float(device.get("lon", device.get("longitude", 0))),
            "alt": float(device.get("alt", device.get("altitude", 0))),
        },
        "effective_range_m": float(device.get("effective_range_m", device.get("range_m", 0))),
        "current_target_id": str(device.get("current_target_id", device.get("target_id", ""))),
        "health_metrics": {
            "battery": device.get("battery", device.get("battery_level", 100)),
            "temperature": device.get("temperature", device.get("temp_c", 25)),
            "uptime_hours": device.get("uptime_hours", device.get("uptime", 0)),
            "error_count": device.get("error_count", 0),
        },
    }
