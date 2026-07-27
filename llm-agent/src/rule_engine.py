"""
规则引擎集成模块 — 置信度门控 + LLM Agent 辅助决策

模拟 Java 规则引擎（ConfidenceGate + LLMClientService）的 Python 实现，
提供威胁评估→置信度检测→Agent上报→决策合并的完整流水线。

核心流程：
1. 基于多维度加权计算规则引擎决策的综合置信度
2. 当置信度低于阈值（默认0.80）时触发 LLM Agent 上报
3. 调用 ReAct 引擎进行深度推理辅助决策
4. 合并规则引擎和 Agent 的结果，取最优决策

使用示例：
    from rule_engine import RuleEngineIntegration
    from react_engine import ReActEngine

    integration = RuleEngineIntegration(react_engine, confidence_threshold=0.80)
    result = integration.assess_with_agent_fallback(
        target=target_data,
        matched_rules=["L1-01", "L2-03"],
        sensor_status={"rf_sensor": 12.0},
        situation=situation_dict,
        task="对目标进行威胁评估",
    )
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

try:
    from .config import config
except (ImportError, ValueError):
    from config import config  # type: ignore[no-redef]

logger = logging.getLogger(__name__)


# ==================== 置信度计算（对标 Java ConfidenceGate） ====================

def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    """将值限定在 [lo, hi] 范围内。"""
    return max(lo, min(hi, value))


def calc_rule_consistency(matched_rules: Optional[List[str]]) -> float:
    """计算规则一致性得分 (权重 0.30)。

    规则数量反映决策的证据充分程度：
    - ≥5条 → 0.95
    - 3-4条 → 0.85
    - 2条 → 0.75
    - 1条 → 0.60
    - 0条 → 0.50
    """
    if not matched_rules:
        return 0.50
    n = len(matched_rules)
    if n >= 5:
        return 0.95
    elif n >= 3:
        return 0.85
    elif n >= 2:
        return 0.75
    else:
        return 0.60


def calc_sensor_quality(sensor_status: Optional[Dict[str, float]]) -> float:
    """计算传感器质量得分 (权重 0.25)。

    基于传感器 SNR 平均值映射：
    - SNR ≥ 20dB → 0.95
    - SNR ≥ 15dB → 0.85
    - SNR ≥ 10dB → 0.70
    - SNR ≥ 5dB  → 0.50
    - SNR < 5dB  → 0.30
    - 无数据     → 0.50
    """
    if not sensor_status:
        return 0.50
    values = [v for v in sensor_status.values() if isinstance(v, (int, float))]
    if not values:
        return 0.50
    avg_snr = sum(values) / len(values)
    if avg_snr >= 20:
        return 0.95
    elif avg_snr >= 15:
        return 0.85
    elif avg_snr >= 10:
        return 0.70
    elif avg_snr >= 5:
        return 0.50
    else:
        return 0.30


def calc_rule_coverage(matched_rules: Optional[List[str]]) -> float:
    """计算规则覆盖度得分 (权重 0.15)。

    检查规则来自哪些层级 (L1-L4)，覆盖越多得分越高。
    得分 = 覆盖层级数 / 4。
    """
    if not matched_rules:
        return 0.0
    prefixes = {"L1-", "L2-", "L3-", "L4-"}
    covered: set = set()
    for rule in matched_rules:
        for p in prefixes:
            if rule.startswith(p):
                covered.add(p)
                break
    if not covered:
        return 1.0 / 4.0  # 有规则但未匹配已知前缀，计为1层
    return len(covered) / 4.0


def calculate_confidence(
    matched_rules: Optional[List[str]],
    sensor_status: Optional[Dict[str, float]],
    classification_confidence: float,
    historical_accuracy: float,
) -> float:
    """计算规则引擎决策的综合置信度（5维度加权）。

    对标 Java ConfidenceGate.calculateConfidence()：
    置信度 = 0.30 * 规则一致性
           + 0.25 * 传感器质量
           + 0.20 * 分类置信度
           + 0.15 * 规则覆盖度
           + 0.10 * 历史准确率

    Args:
        matched_rules: 匹配到的规则ID列表（如 ["L1-01", "L2-03"]）
        sensor_status: 传感器SNR状态Map（sensorId → SNR_dB），可为None
        classification_confidence: 目标分类模型的置信度 (0.0-1.0)
        historical_accuracy: 相似场景历史决策的批准率 (0.0-1.0)

    Returns:
        综合置信度 (0.0-1.0)，值越高表示规则引擎决策越可信
    """
    rule_consistency = calc_rule_consistency(matched_rules)
    sensor_quality = calc_sensor_quality(sensor_status)
    class_conf = _clamp(classification_confidence)
    rule_coverage = calc_rule_coverage(matched_rules)
    historical = _clamp(historical_accuracy)

    confidence = (
        0.30 * rule_consistency
        + 0.25 * sensor_quality
        + 0.20 * class_conf
        + 0.15 * rule_coverage
        + 0.10 * historical
    )

    return _clamp(confidence)


# ==================== LLM 上报触发判断（对标 Java ConfidenceGate） ====================

# 特殊触发条件阈值
EVT_OPEN_SET_THRESHOLD = 0.65       # EVT开集识别分类置信度阈值
COMPLEX_THREAT_TAG_THRESHOLD = 3    # 复合威胁行为标签数量阈值


def get_trigger_reasons(
    classification_confidence: float,
    is_evt_open_set: bool = False,
    threat_behavior_tags: Optional[List[str]] = None,
    drone_category: str = "UNKNOWN",
    confidence: float = 0.0,
    confidence_threshold: float = 0.80,
) -> List[str]:
    """获取触发 LLM Agent 上报的具体原因列表。

    5个触发条件（与 Java ConfidenceGate.getTriggerReasons() 一致）：
    1. EVT开集识别：分类置信度低于0.65
    2. 规则冲突/不确定分类：EVT标记为开集
    3. 复合威胁：检测到3个及以上威胁行为标签
    4. 置信度不足：综合置信度低于阈值
    5. 未知机型：无法识别无人机类别

    Args:
        classification_confidence: 目标分类置信度
        is_evt_open_set: EVT是否标记为开集
        threat_behavior_tags: 威胁行为标签列表
        drone_category: 无人机类别（"UNKNOWN"表示未知）
        confidence: 已计算的综合置信度
        confidence_threshold: 置信度阈值

    Returns:
        触发原因描述列表（中文），无触发时为空列表
    """
    reasons: List[str] = []

    # 条件1：EVT开集识别
    if classification_confidence < EVT_OPEN_SET_THRESHOLD:
        reasons.append(
            f"EVT开集识别: 目标分类置信度低于阈值 "
            f"(当前: {classification_confidence:.2f} < {EVT_OPEN_SET_THRESHOLD})"
        )

    # 条件2：EVT开集标记
    if is_evt_open_set:
        reasons.append("存在规则冲突或不确定分类（EVT开集标记）")

    # 条件3：复合威胁
    if threat_behavior_tags and len(threat_behavior_tags) >= COMPLEX_THREAT_TAG_THRESHOLD:
        reasons.append(
            f"复合威胁: 检测到{len(threat_behavior_tags)}个威胁行为标签 "
            f"(阈值: {COMPLEX_THREAT_TAG_THRESHOLD}个)"
        )

    # 条件4：置信度不足
    if confidence < confidence_threshold:
        reasons.append(f"置信度低于阈值: {confidence:.4f} < {confidence_threshold}")

    # 条件5：未知机型
    if drone_category == "UNKNOWN":
        reasons.append("未知机型类别，无法通过规则引擎准确判断威胁，需要LLM辅助识别")

    return reasons


def should_escalate_to_llm(
    classification_confidence: float,
    is_evt_open_set: bool = False,
    threat_behavior_tags: Optional[List[str]] = None,
    drone_category: str = "UNKNOWN",
    confidence: float = 0.0,
    confidence_threshold: float = 0.80,
) -> Tuple[bool, List[str]]:
    """判断是否需要将决策上报至 LLM Agent 进行辅助决策。

    上报条件（任一满足即触发）：
    - 综合置信度低于阈值
    - 存在任一特殊触发条件

    Args:
        classification_confidence: 目标分类置信度
        is_evt_open_set: EVT是否标记为开集
        threat_behavior_tags: 威胁行为标签列表
        drone_category: 无人机类别
        confidence: 已计算的综合置信度
        confidence_threshold: 置信度阈值

    Returns:
        (should_escalate, trigger_reasons): 是否需要上报，以及触发原因列表
    """
    triggers = get_trigger_reasons(
        classification_confidence=classification_confidence,
        is_evt_open_set=is_evt_open_set,
        threat_behavior_tags=threat_behavior_tags,
        drone_category=drone_category,
        confidence=confidence,
        confidence_threshold=confidence_threshold,
    )

    should = len(triggers) > 0

    if should:
        logger.info(
            f"触发LLM Agent上报: 置信度={confidence:.4f}, "
            f"触发原因数={len(triggers)}, 原因={'; '.join(triggers)}"
        )
    else:
        logger.debug(f"规则引擎置信度充足 ({confidence:.4f} >= {confidence_threshold})，无需上报LLM")

    return should, triggers


# ==================== 规则引擎集成（主入口） ====================


class RuleEngineIntegration:
    """规则引擎集成层 — 置信度门控 + LLM Agent 辅助决策。

    模拟 Java RuleEngineService 中步骤6（置信度门控+LLM增强）的逻辑：
    1. 计算规则引擎的置信度
    2. 检测是否需要LLM上报
    3. 调用LLM Agent进行深度推理
    4. 合并结果（取最高置信度的决策）
    5. LLM不可用时回退到规则引擎决策

    使用方式：
        integration = RuleEngineIntegration(react_engine)
        result = integration.assess_with_agent_fallback(
            target_id="T001",
            matched_rules=["L1-01", "L2-03"],
            sensor_status={"rf_sensor": 12.0},
            classification_confidence=0.55,
            situation=situation_dict,
            task="对目标T001进行威胁评估",
        )
    """

    def __init__(
        self,
        react_engine: Any = None,
        confidence_threshold: float | None = None,
    ):
        """初始化规则引擎集成层。

        Args:
            react_engine: ReActEngine 实例（可选，用于Agent辅助决策）
            confidence_threshold: 置信度阈值，默认使用 config.CONFIDENCE_THRESHOLD
        """
        self._react_engine = react_engine
        self._confidence_threshold = (
            confidence_threshold
            if confidence_threshold is not None
            else config.CONFIDENCE_THRESHOLD
        )
        logger.info(
            "规则引擎集成层初始化完成: 置信度阈值=%.2f, Agent=%s",
            self._confidence_threshold,
            "可用" if react_engine is not None else "不可用（仅规则引擎模式）",
        )

    @property
    def confidence_threshold(self) -> float:
        """当前置信度阈值。"""
        return self._confidence_threshold

    @property
    def agent_available(self) -> bool:
        """LLM Agent是否可用。"""
        return self._react_engine is not None

    def assess_with_agent_fallback(
        self,
        target_id: str,
        matched_rules: Optional[List[str]],
        sensor_status: Optional[Dict[str, float]],
        classification_confidence: float,
        situation: dict,
        task: str,
        historical_accuracy: float = 0.80,
        is_evt_open_set: bool = False,
        threat_behavior_tags: Optional[List[str]] = None,
        drone_category: str = "UNKNOWN",
    ) -> dict:
        """执行威胁评估，置信度不足时自动调用 LLM Agent 辅助决策。

        这是核心方法，模拟 Java RuleEngineService.assessThreats() 中的
        步骤6（置信度门控 + LLM增强）。

        Args:
            target_id: 目标ID
            matched_rules: 匹配到的规则ID列表
            sensor_status: 传感器SNR状态
            classification_confidence: 目标分类置信度 (0.0-1.0)
            situation: 完整态势字典
            task: 任务描述文本
            historical_accuracy: 历史相似决策批准率 (默认0.80)
            is_evt_open_set: EVT是否标记为开集
            threat_behavior_tags: 威胁行为标签列表
            drone_category: 无人机类别

        Returns:
            {
                "decision": {...},           # 最终决策（来自规则引擎或Agent）
                "confidence": float,         # 最终置信度
                "source": str,              # 决策来源: "RULE_ENGINE" | "LLM_AGENT" | "HYBRID"
                "rule_engine_confidence": float,  # 规则引擎原始置信度
                "agent_confidence": float | None, # Agent置信度（如有）
                "triggered_escalation": bool,     # 是否触发了Agent上报
                "trigger_reasons": [str],        # 触发原因列表
                "agent_available": bool,          # Agent是否可用
                "agent_decision": dict | None,    # Agent原始决策（如有）
            }
        """
        result: dict = {
            "decision": None,
            "confidence": 0.0,
            "source": "RULE_ENGINE",
            "rule_engine_confidence": 0.0,
            "agent_confidence": None,
            "triggered_escalation": False,
            "trigger_reasons": [],
            "agent_available": self.agent_available,
            "agent_decision": None,
        }

        # Step 1: 计算规则引擎置信度
        rule_confidence = calculate_confidence(
            matched_rules=matched_rules,
            sensor_status=sensor_status,
            classification_confidence=classification_confidence,
            historical_accuracy=historical_accuracy,
        )
        result["rule_engine_confidence"] = rule_confidence
        result["confidence"] = rule_confidence

        logger.info(
            "目标[%s] 规则引擎置信度: %.4f (阈值=%.2f)",
            target_id, rule_confidence, self._confidence_threshold,
        )

        # Step 2: 检查是否需要LLM上报
        should_esc, triggers = should_escalate_to_llm(
            classification_confidence=classification_confidence,
            is_evt_open_set=is_evt_open_set,
            threat_behavior_tags=threat_behavior_tags,
            drone_category=drone_category,
            confidence=rule_confidence,
            confidence_threshold=self._confidence_threshold,
        )

        result["triggered_escalation"] = should_esc
        result["trigger_reasons"] = triggers

        # Step 3: 如果置信度充足，直接返回规则引擎决策
        if not should_esc:
            logger.info(
                "目标[%s] 规则引擎置信度充足 (%.4f)，无需LLM辅助",
                target_id, rule_confidence,
            )
            result["source"] = "RULE_ENGINE"
            result["decision"] = self._build_rule_engine_decision(
                target_id, rule_confidence, matched_rules, situation
            )
            return result

        # Step 4: 置信度不足，尝试调用LLM Agent
        logger.info(
            "目标[%s] 触发LLM上报: 原因=%s",
            target_id, "; ".join(triggers),
        )

        if not self.agent_available:
            # Agent不可用 → 回退
            logger.warning(
                "目标[%s] LLM Agent不可用，使用规则引擎回退决策", target_id
            )
            result["source"] = "RULE_ENGINE"
            result["trigger_reasons"].append("LLM_UNAVAILABLE: Agent未初始化")
            result["decision"] = self._build_rule_engine_decision(
                target_id, rule_confidence, matched_rules, situation,
                uncertainty_flags=["LLM_UNAVAILABLE"],
            )
            return result

        # Step 5: 调用Agent
        try:
            task_with_context = (
                f"{task}\n"
                f"【上报原因】规则引擎置信度不足 ({rule_confidence:.4f} < {self._confidence_threshold})。\n"
                f"触发条件: {'; '.join(triggers)}\n"
                f"请进行深度分析并提供高置信度的决策建议。"
            )

            agent_decision = self._react_engine.run(
                task=task_with_context,
                situation=situation,
            )

            result["agent_decision"] = agent_decision

            if agent_decision and isinstance(agent_decision, dict):
                agent_conf = (
                    agent_decision.get("threat_assessment", {}).get("confidence", 0.0)
                )
                result["agent_confidence"] = agent_conf

                # 合并置信度（取最大值，模拟 Java Math.max 逻辑）
                merged_confidence = max(rule_confidence, agent_conf)
                result["confidence"] = merged_confidence

                if agent_conf > rule_confidence:
                    result["source"] = "LLM_AGENT"
                    result["decision"] = agent_decision
                    logger.info(
                        "目标[%s] LLM Agent提升置信度: %.4f → %.4f",
                        target_id, rule_confidence, agent_conf,
                    )
                else:
                    result["source"] = "HYBRID"
                    # 使用规则引擎基础 + Agent推理链
                    result["decision"] = self._merge_decisions(
                        self._build_rule_engine_decision(
                            target_id, rule_confidence, matched_rules, situation
                        ),
                        agent_decision,
                    )
                    logger.info(
                        "目标[%s] LLM Agent未提升置信度 (%.4f ≤ %.4f)，使用混合决策",
                        target_id, agent_conf, rule_confidence,
                    )
            else:
                # Agent返回空结果
                logger.warning("目标[%s] LLM Agent返回空结果，使用规则引擎回退", target_id)
                result["source"] = "RULE_ENGINE"
                result["trigger_reasons"].append("LLM_UNAVAILABLE: Agent返回空结果")
                result["decision"] = self._build_rule_engine_decision(
                    target_id, rule_confidence, matched_rules, situation,
                    uncertainty_flags=["LLM_EMPTY_RESPONSE"],
                )

        except Exception as e:
            # Agent调用异常 → 回退
            logger.error(
                "目标[%s] LLM Agent调用异常: %s，使用规则引擎回退", target_id, e
            )
            result["source"] = "RULE_ENGINE"
            result["trigger_reasons"].append(f"LLM_UNAVAILABLE: Agent异常 - {str(e)[:100]}")
            result["decision"] = self._build_rule_engine_decision(
                target_id, rule_confidence, matched_rules, situation,
                uncertainty_flags=["LLM_EXCEPTION"],
            )

        return result

    # ==================== 辅助方法 ====================

    @staticmethod
    def _build_rule_engine_decision(
        target_id: str,
        confidence: float,
        matched_rules: Optional[List[str]],
        situation: dict,
        uncertainty_flags: Optional[List[str]] = None,
    ) -> dict:
        """构建规则引擎决策结构（当Agent不可用时的回退决策）。

        Args:
            target_id: 目标ID
            confidence: 规则引擎置信度
            matched_rules: 匹配的规则列表
            situation: 态势数据
            uncertainty_flags: 额外的不确定标记

        Returns:
            结构化决策字典
        """
        flags = list(uncertainty_flags or [])
        if confidence < 0.80:
            flags.append("LOW_CONFIDENCE")

        return {
            "decision_id": situation.get("task_id", f"task-{target_id}"),
            "target_id": target_id,
            "threat_assessment": {
                "threat_score": 0.70,
                "threat_level": 4 if confidence < 0.80 else 3,
                "confidence": confidence,
                "key_factors": [f"匹配规则{len(matched_rules or [])}条"],
                "uncertainty_flags": flags,
            },
            "recommended_action": {
                "action_type": "全频段压制" if confidence < 0.60 else "选择性干扰",
                "priority": 1 if confidence < 0.60 else 3,
                "devices": [],
                "parameters": {"source": "rule_engine_fallback"},
                "expected_effect": "规则引擎回退决策，建议人工审核",
                "alternative_actions": [],
            },
            "reasoning_chain": [
                f"规则引擎置信度: {confidence:.4f}",
                f"匹配规则: {matched_rules or '无'}",
                "Agent不可用或异常，使用规则引擎回退决策",
            ],
            "data_sources": ["rule_engine"],
            "rule_proposal": None,
            "remarks": (
                f"【注意】此决策由规则引擎在Agent不可用时自动生成，"
                f"置信度为 {confidence:.4f}。建议指挥员人工复核。"
            ),
            "uncertainty_flags": flags,
        }

    @staticmethod
    def _merge_decisions(
        rule_engine_decision: dict,
        agent_decision: dict,
    ) -> dict:
        """合并规则引擎决策和Agent决策（Agent未显著提升置信度时使用）。

        保留规则引擎的基础结构，追加Agent的推理链和关键发现。

        Args:
            rule_engine_decision: 规则引擎决策
            agent_decision: Agent决策

        Returns:
            合并后的决策
        """
        merged = dict(rule_engine_decision)

        # 追加Agent推理链
        agent_chain = agent_decision.get("reasoning_chain", [])
        if agent_chain:
            merged["reasoning_chain"] = (
                rule_engine_decision.get("reasoning_chain", [])
                + ["--- LLM Agent 辅助分析 ---"]
                + agent_chain
            )

        # 追加Agent数据来源
        agent_sources = agent_decision.get("data_sources", [])
        if agent_sources:
            existing_sources = set(merged.get("data_sources", []))
            for s in agent_sources:
                if s not in existing_sources:
                    merged.setdefault("data_sources", []).append(s)

        # 合并不确定标记
        agent_flags = agent_decision.get("uncertainty_flags", [])
        if agent_flags:
            existing_flags = set(merged.get("uncertainty_flags", []))
            for f in agent_flags:
                if f not in existing_flags:
                    merged.setdefault("uncertainty_flags", []).append(f)

        # 追加备注
        agent_remarks = agent_decision.get("remarks", "")
        if agent_remarks:
            merged["remarks"] = (
                merged.get("remarks", "")
                + f"\n\n【LLM Agent 补充分析】\n{agent_remarks}"
            )

        return merged


# ==================== 快速调用函数 ====================


def quick_assess(
    target_id: str,
    situation: dict,
    task: str,
    matched_rules: Optional[List[str]] = None,
    sensor_status: Optional[Dict[str, float]] = None,
    classification_confidence: float = 0.70,
    react_engine: Any = None,
) -> dict:
    """快速威胁评估（便捷函数）。

    一步完成：置信度计算 → 上报判断 → Agent调用 → 决策返回。

    Args:
        target_id: 目标ID
        situation: 态势数据
        task: 任务描述
        matched_rules: 匹配规则列表
        sensor_status: 传感器状态
        classification_confidence: 分类置信度
        react_engine: ReAct引擎实例（可选）

    Returns:
        评估结果字典
    """
    integration = RuleEngineIntegration(react_engine)
    return integration.assess_with_agent_fallback(
        target_id=target_id,
        matched_rules=matched_rules or [],
        sensor_status=sensor_status,
        classification_confidence=classification_confidence,
        situation=situation,
        task=task,
    )
