"""
规则提案工具
当 LLM 推理发现新的有效处置模式时，可向规则引擎提交新规则提案。
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any

import httpx

try:
    from ..config import config
except (ImportError, ValueError):
    from config import config  # type: ignore[no-redef]

logger = logging.getLogger(__name__)

# 本地备份路径
_BACKUP_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "pending_rules_backup.json"


def propose_rule(args: dict) -> dict:
    """向规则引擎提交新的处置规则提案。

    Args:
        args: 参数字典，包含:
            - rule_text (str): 规则文本（必需）
            - reason (str): 提案原因（必需）
            - source_decision_id (str): 来源决策 ID（必需）

    Returns:
        提案结果字典：
        {
            "success": bool,
            "data": {
                "proposal_id": str,
                "status": str,
            },
            "error": str,
        }
    """
    rule_text = args.get("rule_text", "")
    reason = args.get("reason", "")
    source_decision_id = args.get("source_decision_id", "")

    # 参数校验
    if not rule_text:
        return {"success": False, "data": None, "error": "参数 'rule_text' 不能为空"}
    if not reason:
        return {"success": False, "data": None, "error": "参数 'reason' 不能为空"}
    if not source_decision_id:
        return {"success": False, "data": None, "error": "参数 'source_decision_id' 不能为空"}

    proposal_id = f"llm-prop-{uuid.uuid4().hex[:8]}"

    # 优先尝试 HTTP 提交
    try:
        result = _propose_via_http(proposal_id, rule_text, reason, source_decision_id)
        if result["success"]:
            return result
        logger.warning(f"HTTP 规则提案提交失败，保存到本地: {result.get('error', '')}")
    except Exception as e:
        logger.warning(f"HTTP 规则提案提交异常，保存到本地: {e}")

    # 回退到本地保存
    try:
        return _save_locally(proposal_id, rule_text, reason, source_decision_id)
    except Exception as e:
        logger.error(f"本地规则提案保存也失败: {e}")
        return {
            "success": False,
            "data": None,
            "error": f"规则提案提交均失败: {e}",
        }


def _propose_via_http(
    proposal_id: str,
    rule_text: str,
    reason: str,
    source_decision_id: str,
) -> dict:
    """通过 HTTP 向规则引擎提交规则提案。"""
    url = f"{config.RULE_ENGINE_URL}/api/rules/pending"

    payload = {
        "proposal_id": proposal_id,
        "rule_text": rule_text,
        "reason": reason,
        "source_decision_id": source_decision_id,
        "source": "llm_agent",
        "timestamp": time.time(),
    }

    try:
        with httpx.Client(timeout=8.0) as client:
            response = client.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()
            data = response.json()

            status = data.get("status", "submitted")
            server_proposal_id = data.get("proposal_id", proposal_id)

            logger.info(f"规则提案提交成功: {server_proposal_id}, status={status}")
            return {
                "success": True,
                "data": {
                    "proposal_id": server_proposal_id,
                    "status": status,
                },
                "error": "",
            }

    except httpx.ConnectError:
        return {"success": False, "data": None, "error": f"无法连接规则引擎: {url}"}
    except httpx.TimeoutException:
        return {"success": False, "data": None, "error": "规则提案请求超时"}
    except httpx.HTTPStatusError as e:
        return {"success": False, "data": None, "error": f"规则引擎返回错误: {e.response.status_code}"}
    except Exception as e:
        return {"success": False, "data": None, "error": f"HTTP 请求异常: {e}"}


def _save_locally(
    proposal_id: str,
    rule_text: str,
    reason: str,
    source_decision_id: str,
) -> dict:
    """将规则提案保存到本地 JSON 文件（回退方案）。"""
    # 确保目录存在
    _BACKUP_PATH.parent.mkdir(parents=True, exist_ok=True)

    proposal = {
        "proposal_id": proposal_id,
        "rule_text": rule_text,
        "reason": reason,
        "source_decision_id": source_decision_id,
        "source": "llm_agent",
        "status": "pending_local",
        "submitted_at": time.time(),
        "submitted_at_iso": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
    }

    # 读取已有数据
    existing: list[dict] = []
    if _BACKUP_PATH.exists():
        try:
            with open(_BACKUP_PATH, "r", encoding="utf-8") as f:
                existing = json.load(f)
                if not isinstance(existing, list):
                    existing = []
        except (json.JSONDecodeError, IOError):
            logger.warning("本地规则备份文件损坏，将重新创建")
            existing = []

    existing.append(proposal)

    # 写入文件
    with open(_BACKUP_PATH, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    logger.info(f"规则提案已保存到本地: {proposal_id} (共 {len(existing)} 条待处理提案)")
    return {
        "success": True,
        "data": {
            "proposal_id": proposal_id,
            "status": "pending_local",
            "backup_path": str(_BACKUP_PATH),
        },
        "error": "",
    }
