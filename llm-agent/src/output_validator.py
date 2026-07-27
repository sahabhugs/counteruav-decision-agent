"""
输出校验器模块
使用 Pydantic 模型对 LLM 输出的决策 JSON 进行结构校验。
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any, List, Optional, Tuple

from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)


# ==================== 枚举定义 ====================

class ThreatLevelEnum(int, Enum):
    """威胁等级枚举：1=极低, 2=低, 3=中, 4=高, 5=极高"""
    LEVEL_1 = 1
    LEVEL_2 = 2
    LEVEL_3 = 3
    LEVEL_4 = 4
    LEVEL_5 = 5


class ActionTypeEnum(str, Enum):
    """处置动作类型枚举"""
    MONITOR = "监测"
    JAM_FULL_BAND = "全频段压制"
    JAM_SELECTIVE = "选择性干扰"
    GNSS_SPOOFING = "导航诱骗"
    LASER_DESTROY = "激光摧毁"
    NET_CAPTURE = "网捕"
    MICROWAVE = "微波毁伤"
    KINETIC = "硬杀伤"
    WAIT = "待命"
    NEGOTIATE = "协商"


class UncertaintyFlagEnum(str, Enum):
    """不确定标记类型"""
    LOW_SNR = "低信噪比"
    SIGNAL_ANOMALY = "信号异常"
    UNKNOWN_MODEL = "未知型号"
    CIVILIAN_PROXIMITY = "平民区临近"
    MULTI_TARGET = "多目标"
    SENSOR_CONFLICT = "传感器冲突"
    INCOMPLETE_DATA = "数据不完整"


# ==================== Pydantic 子模型 ====================

class ThreatAssessmentOutput(BaseModel):
    """威胁评估子结构"""
    threat_score: float = Field(..., ge=0.0, le=1.0, description="威胁评分 0.0-1.0")
    threat_level: int = Field(..., ge=1, le=5, description="威胁等级 1-5")
    confidence: float = Field(..., ge=0.0, le=1.0, description="置信度 0.0-1.0")
    key_factors: List[str] = Field(default_factory=list, description="关键威胁因素")
    uncertainty_flags: List[str] = Field(default_factory=list, description="不确定标记")

    @field_validator("key_factors")
    @classmethod
    def key_factors_not_empty(cls, v: list) -> list:
        if not v:
            raise ValueError("key_factors 不能为空")
        return v


class RecommendedActionOutput(BaseModel):
    """推荐动作子结构"""
    action_type: str = Field(..., description="处置动作类型")
    priority: int = Field(..., ge=1, le=10, description="优先级 1-10")
    devices: List[str] = Field(default_factory=list, description="推荐使用的设备 ID 列表")
    parameters: dict = Field(default_factory=dict, description="动作参数")
    expected_effect: str = Field(default="", description="预期效果")
    alternative_actions: List[dict] = Field(default_factory=list, description="备选动作")

    @field_validator("action_type")
    @classmethod
    def action_type_valid(cls, v: str) -> str:
        valid_actions = {a.value for a in ActionTypeEnum}
        if v not in valid_actions:
            logger.warning(f"动作类型 '{v}' 不在标准枚举中，但仍接受")
        return v


class RuleProposalOutput(BaseModel):
    """规则提案子结构（可选，战后批处理生成）"""
    rule_text: str = Field(default="", description="提案规则文本")
    reason: str = Field(default="", description="提案原因")
    priority: str = Field(default="normal", description="建议优先级: low/normal/high/urgent")


class OperationRiskLevel(str, Enum):
    """操作风险等级"""
    REVERSIBLE = "L-可逆"
    SEMI_REVERSIBLE = "M-半可逆"
    IRREVERSIBLE = "H-不可逆"


class LLMDecisionOutput(BaseModel):
    """LLM 决策输出主结构"""
    decision_id: str = Field(..., min_length=1, description="决策 ID（与 task_id 相关）")
    target_id: str = Field(..., min_length=1, description="目标 ID")
    threat_assessment: ThreatAssessmentOutput = Field(..., description="威胁评估")
    recommended_action: RecommendedActionOutput = Field(..., description="推荐动作")
    reasoning_chain: List[str] = Field(default_factory=list, description="推理链（步骤列表）")
    data_sources: List[str] = Field(default_factory=list, description="数据来源（工具调用记录）")
    risk_level: str = Field(default="M-半可逆", description="操作风险等级: L-可逆 | M-半可逆 | H-不可逆")
    rule_proposal: Optional[RuleProposalOutput] = Field(default=None, description="规则提案（可选，战后批处理）")
    remarks: str = Field(default="", description="附注说明")
    uncertainty_flags: List[str] = Field(default_factory=list, description="不确定性标记列表")

    @field_validator("reasoning_chain")
    @classmethod
    def reasoning_chain_not_empty(cls, v: list) -> list:
        if not v:
            raise ValueError("reasoning_chain 不能为空，必须包含推理步骤")
        return v


# ==================== 校验器 ====================

class OutputValidator:
    """LLM 决策输出的 JSON Schema 校验器。"""

    def __init__(self):
        self._errors: List[str] = []

    def validate(self, data: dict) -> Tuple[bool, List[str]]:
        """校验 LLM 输出的决策数据。

        Args:
            data: 待校验的决策字典。

        Returns:
            (is_valid, errors): 是否有效，以及错误信息列表。
        """
        self._errors = []

        try:
            # 使用 Pydantic 模型进行校验
            decision = LLMDecisionOutput(**data)

            # 额外业务规则校验
            self._validate_business_rules(decision)

        except Exception as e:
            self._errors.append(f"结构校验失败: {str(e)}")

        if self._errors:
            logger.warning(f"LLM 输出校验发现 {len(self._errors)} 个问题: {self._errors}")

        return len(self._errors) == 0, self._errors

    def _validate_business_rules(self, decision: LLMDecisionOutput) -> None:
        """执行额外的业务规则校验（含 ROE 硬约束）。"""
        ta = decision.threat_assessment

        # 置信度检查
        if ta.confidence < 0.3:
            self._errors.append(
                f"置信度过低 ({ta.confidence:.2f})，决策可靠性不足"
            )

        # 威胁等级与评分一致性检查
        expected_level_min = int(ta.threat_score * 5)
        if abs(ta.threat_level - expected_level_min) > 1:
            self._errors.append(
                f"威胁等级 ({ta.threat_level}) 与评分 ({ta.threat_score:.2f}) 不一致"
            )

        # 不确定标记与置信度的关联
        if ta.uncertainty_flags and ta.confidence > 0.9:
            self._errors.append(
                "存在不确定标记但置信度高于 0.9，逻辑矛盾"
            )

        # ROE 硬约束: 低威胁等级禁止硬杀伤
        ra = decision.recommended_action
        irreversible_actions = ("激光摧毁", "微波毁伤", "硬杀伤", "kinetic_impact",
                               "laser_destruction", "high_power_microwave")
        if ta.threat_level <= 1 and ra.action_type in irreversible_actions:
            self._errors.append(
                f"ROE 硬约束: 威胁等级≤1 禁止使用不可逆杀伤手段，当前: {ra.action_type}"
            )

        # ROE 硬约束: 民用区域 + 威胁<5 禁止硬杀伤
        # 从 uncertainty_flags 或 remarks 推断是否涉及平民区域
        civilian_indicators = ("平民区临近", "平民", "civilian", "CIVILIAN_AREA")
        has_civilian_flag = any(
            ind in str(ta.uncertainty_flags) for ind in civilian_indicators
        )
        if has_civilian_flag and ta.threat_level < 5 and ra.action_type in irreversible_actions:
            self._errors.append(
                f"ROE 硬约束: 平民区域 + 威胁等级<5 禁止硬杀伤，当前: {ra.action_type}"
            )

        # 数据来源不为空
        if not decision.data_sources:
            self._errors.append("data_sources 不能为空，必须至少引用一个工具调用结果")

    def quick_validate(self, data: dict) -> bool:
        """快速校验（只返回 bool 不含详细错误）。

        Args:
            data: 待校验的决策字典。

        Returns:
            是否有效。
        """
        valid, _ = self.validate(data)
        return valid

    @staticmethod
    def extract_and_validate_json(raw_text: str) -> Tuple[Optional[dict], List[str]]:
        """从原始文本中提取 JSON 并校验。

        Args:
            raw_text: 可能包含 JSON 的原始文本。

        Returns:
            (parsed_dict, errors): 解析后的字典（失败时为 None）和错误列表。
        """
        import json
        import re

        errors: List[str] = []
        validator = OutputValidator()

        # 尝试多种方式提取 JSON
        candidates: list[str] = []

        # 方式 1: ```json ... ``` 代码块
        json_blocks = re.findall(r"```json\s*(.*?)\s*```", raw_text, re.DOTALL)
        candidates.extend(json_blocks)

        # 方式 2: ``` ... ``` 代码块
        code_blocks = re.findall(r"```\s*(\{.*?\})\s*```", raw_text, re.DOTALL)
        candidates.extend(code_blocks)

        # 方式 3: 直接匹配最外层 { ... }
        brace_matches = re.findall(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", raw_text, re.DOTALL)
        candidates.extend(brace_matches)

        # 方式 4: 整段文本尝试
        candidates.append(raw_text)

        for candidate in candidates:
            candidate = candidate.strip()
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict) and "decision_id" in parsed:
                    valid, errs = validator.validate(parsed)
                    if valid:
                        return parsed, []
                    else:
                        errors.extend(errs)
                else:
                    errors.append("JSON 解析成功但缺少 decision_id 字段")
            except json.JSONDecodeError:
                continue

        return None, errors
