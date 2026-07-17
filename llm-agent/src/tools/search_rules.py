"""
规则搜索工具
从规则引擎数据库搜索匹配的反无人机处置规则。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

import httpx

try:
    from ..config import config
except (ImportError, ValueError):
    from config import config  # type: ignore[no-redef]

logger = logging.getLogger(__name__)

# 本地规则文件缓存路径
_LOCAL_RULES_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "rules.json"


def search_rules(args: dict) -> dict:
    """搜索规则数据库。

    Args:
        args: 参数字典，包含:
            - query (str): 搜索关键词（必需）
            - layers (list[int], 可选): 规则层级过滤，如 [1,2,3]

    Returns:
        搜索结果字典：{"success": bool, "data": [...], "error": str}
    """
    query = args.get("query", "")
    layers = args.get("layers", None)

    if not query:
        return {"success": False, "data": None, "error": "搜索关键词 'query' 不能为空"}

    # 优先尝试 HTTP 查询
    try:
        result = _search_via_http(query, layers)
        if result["success"]:
            return result
        logger.warning(f"HTTP 规则搜索失败，切至本地搜索: {result.get('error', '')}")
    except Exception as e:
        logger.warning(f"HTTP 规则搜索异常，切至本地搜索: {e}")

    # 回退到本地文件搜索
    try:
        return _search_local(query, layers)
    except Exception as e:
        logger.error(f"本地规则搜索也失败: {e}")
        return {
            "success": False,
            "data": None,
            "error": f"规则搜索均失败: HTTP->本地，最终错误: {e}",
        }


def _search_via_http(query: str, layers: Optional[list[int]]) -> dict:
    """通过 HTTP 请求规则引擎搜索规则。"""
    url = f"{config.RULE_ENGINE_URL}/api/rules"
    params: dict = {"keyword": query}
    if layers:
        params["layers"] = ",".join(str(l) for l in layers)

    try:
        with httpx.Client(timeout=5.0) as client:
            response = client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            # 适应多种响应格式
            rules = data if isinstance(data, list) else data.get("rules", data.get("data", []))

            logger.info(f"HTTP 规则搜索成功: {len(rules)} 条匹配")
            return {"success": True, "data": rules, "error": ""}

    except httpx.ConnectError:
        return {"success": False, "data": None, "error": f"无法连接规则引擎: {url}"}
    except httpx.TimeoutException:
        return {"success": False, "data": None, "error": "规则引擎请求超时"}
    except httpx.HTTPStatusError as e:
        return {"success": False, "data": None, "error": f"规则引擎返回错误: {e.response.status_code}"}
    except Exception as e:
        return {"success": False, "data": None, "error": f"HTTP 请求异常: {e}"}


def _search_local(query: str, layers: Optional[list[int]]) -> dict:
    """从本地 JSON 文件搜索规则（回退方案）。"""
    if not _LOCAL_RULES_PATH.exists():
        logger.warning(f"本地规则文件不存在: {_LOCAL_RULES_PATH}")
        return {
            "success": True,
            "data": [],
            "error": f"本地规则文件未找到: {_LOCAL_RULES_PATH}",
        }

    try:
        with open(_LOCAL_RULES_PATH, "r", encoding="utf-8") as f:
            all_rules: list[dict] = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        return {"success": False, "data": None, "error": f"本地规则文件读取失败: {e}"}

    # 关键词模糊匹配
    query_lower = query.lower()
    matched: list[dict] = []
    for rule in all_rules:
        rule_name = str(rule.get("name", rule.get("title", ""))).lower()
        rule_content = str(rule.get("content", rule.get("description", ""))).lower()
        rule_tags = [str(t).lower() for t in rule.get("tags", rule.get("keywords", []))]

        score = 0
        if query_lower in rule_name:
            score += 3
        if query_lower in rule_content:
            score += 2
        if any(query_lower in tag for tag in rule_tags):
            score += 1

        if score > 0:
            rule_copy = dict(rule)
            rule_copy["_match_score"] = score
            matched.append(rule_copy)

    # 层级过滤
    if layers:
        matched = [
            r for r in matched
            if r.get("layer", r.get("level", 0)) in layers
        ]

    # 按匹配得分排序
    matched.sort(key=lambda r: r.get("_match_score", 0), reverse=True)

    logger.info(f"本地规则搜索成功: {len(matched)} 条匹配 (关键词: {query})")
    return {"success": True, "data": matched[:20], "error": ""}
