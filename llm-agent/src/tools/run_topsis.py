"""
TOPSIS 计算工具
调用规则引擎的 TOPSIS 多属性决策计算服务，获取目标威胁评估。
"""

from __future__ import annotations

import logging
import math
from typing import Any, Optional

import httpx

try:
    from ..config import config
except (ImportError, ValueError):
    from config import config  # type: ignore[no-redef]

logger = logging.getLogger(__name__)


def run_topsis(args: dict) -> dict:
    """调用 TOPSIS 多属性决策计算。

    Args:
        args: 参数字典，包含:
            - target_id (str): 目标 ID（必需）

    Returns:
        TOPSIS 计算结果字典：
        {
            "success": bool,
            "data": {
                "threat_score": float,
                "threat_level": int,
                "indicator_scores": dict,
                "positive_ideal_distance": float,
                "negative_ideal_distance": float,
            },
            "error": str,
        }
    """
    target_id = args.get("target_id", "")

    if not target_id:
        return {"success": False, "data": None, "error": "参数 'target_id' 不能为空"}

    # 优先尝试 HTTP 调用
    try:
        result = _call_topsis_http(target_id)
        if result["success"]:
            return result
        logger.warning(f"HTTP TOPSIS 调用失败，使用本地简化计算: {result.get('error', '')}")
    except Exception as e:
        logger.warning(f"HTTP TOPSIS 调用异常，使用本地简化计算: {e}")

    # 回退到本地简化 TOPSIS
    try:
        return _local_topsis_fallback(args)
    except Exception as e:
        logger.error(f"本地 TOPSIS 计算失败: {e}")
        return {
            "success": False,
            "data": None,
            "error": f"TOPSIS 计算完全失败: {e}",
        }


def _call_topsis_http(target_id: str) -> dict:
    """通过 HTTP 调用规则引擎的 TOPSIS 计算。"""
    url = f"{config.RULE_ENGINE_URL}/api/decision/topsis"

    try:
        with httpx.Client(timeout=8.0) as client:
            response = client.post(
                url,
                json={"target_id": target_id},
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()
            data = response.json()

            # 适配多种响应格式
            if isinstance(data, dict):
                result_data = data.get("result", data.get("data", data))
            else:
                result_data = data

            logger.info(f"HTTP TOPSIS 计算成功: target={target_id}, score={result_data.get('threat_score', 'N/A')}")
            return {"success": True, "data": result_data, "error": ""}

    except httpx.ConnectError:
        return {"success": False, "data": None, "error": f"无法连接规则引擎: {url}"}
    except httpx.TimeoutException:
        return {"success": False, "data": None, "error": "规则引擎 TOPSIS 请求超时"}
    except httpx.HTTPStatusError as e:
        return {"success": False, "data": None, "error": f"规则引擎返回错误: {e.response.status_code}"}
    except Exception as e:
        return {"success": False, "data": None, "error": f"HTTP 请求异常: {e}"}


def _local_topsis_fallback(args: dict) -> dict:
    """本地简化 TOPSIS 计算（回退方案）。

    基于多指标对目标进行简易威胁评估，使用加权归一化方法。
    在规则引擎不可用时提供基本评估能力。

    Args:
        args: 原始参数字典（可能包含更多上下文信息）。

    Returns:
        简化的 TOPSIS 计算结果。
    """
    # 尝试从参数中提取指标数据
    indicators_raw = args.get("indicators", args.get("indicator_scores", {}))

    # 默认指标：速度、距离、高度、信号强度、目标类型
    if indicators_raw:
        # 使用提供的指标数据
        indicator_names = list(indicators_raw.keys())[:6]
        indicator_values = [float(indicators_raw.get(k, 0)) for k in indicator_names]
    else:
        # 无指标数据时生成合理默认值
        indicator_names = [
            "speed_factor",
            "distance_factor",
            "altitude_factor",
            "signal_strength",
            "target_type_score",
        ]
        # 从 args 中提取目标属性
        speed = float(args.get("speed_ms", args.get("speed", 50)))
        distance = float(args.get("distance_m", args.get("distance", 5000)))
        altitude = float(args.get("altitude_m", args.get("altitude", 200)))
        signal = float(args.get("signal_strength", args.get("snr_db", 10)))
        target_type = str(args.get("target_type", "unknown"))

        # 归一化为 0-1
        speed_norm = min(1.0, speed / 100.0)  # 100m/s 为基准
        distance_norm = 1.0 - min(1.0, distance / 10000.0)  # 越近越高
        altitude_norm = min(1.0, altitude / 500.0)
        signal_norm = min(1.0, max(0.0, (signal + 20) / 60))  # -20 到 40 dB 范围
        type_score = 0.5 if target_type == "unknown" else 0.3

        indicator_values = [speed_norm, distance_norm, altitude_norm, signal_norm, type_score]

    # 权重（默认均匀，可根据场景调整）
    weights = args.get("weights", [0.25, 0.20, 0.15, 0.20, 0.20])
    if len(weights) != len(indicator_values):
        weights = [1.0 / len(indicator_values)] * len(indicator_values)

    n = len(indicator_values)

    # 归一化矩阵
    norm_values: list[float] = []
    sum_sq = math.sqrt(sum(v * v for v in indicator_values))
    if sum_sq > 0:
        norm_values = [v / sum_sq for v in indicator_values]
    else:
        norm_values = [0.0] * n

    # 加权归一化
    weighted = [w * v for w, v in zip(weights, norm_values)]

    # 正理想解和负理想解（所有指标均为正向（越大越危险）的简化假设）
    ideal_pos = [max(weighted)] * n
    ideal_neg = [0.0] * n

    # 计算距离
    d_pos = math.sqrt(sum((v - ip) ** 2 for v, ip in zip(weighted, ideal_pos)))
    d_neg = math.sqrt(sum((v - ineg) ** 2 for v, ineg in zip(weighted, ideal_neg)))

    # 相对贴近度 = 威胁评分
    if d_pos + d_neg > 0:
        threat_score = d_neg / (d_pos + d_neg)
    else:
        threat_score = 0.5

    # 威胁等级（1-5）
    if threat_score >= 0.8:
        threat_level = 5
    elif threat_score >= 0.6:
        threat_level = 4
    elif threat_score >= 0.4:
        threat_level = 3
    elif threat_score >= 0.2:
        threat_level = 2
    else:
        threat_level = 1

    indicator_scores = {
        name: round(val, 4) for name, val in zip(indicator_names, norm_values)
    }

    result = {
        "threat_score": round(threat_score, 4),
        "threat_level": threat_level,
        "indicator_scores": indicator_scores,
        "positive_ideal_distance": round(d_pos, 4),
        "negative_ideal_distance": round(d_neg, 4),
        "_source": "本地简化TOPSIS",
    }

    logger.info(f"本地简化 TOPSIS 计算完成: score={threat_score:.4f}, level={threat_level}")
    return {"success": True, "data": result, "error": ""}
