package com.counteruav.model;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.List;
import java.util.Map;

/**
 * 目标决策实体类
 * 包含对单个目标的完整决策输出：威胁评估结果、推荐行动方案和规则优化建议
 */
@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class TargetDecision {

    /** 关联的目标ID */
    @JsonProperty("target_id")
    private String targetId;

    /** 威胁评估结果 */
    @JsonProperty("threat_assessment")
    private ThreatAssessment threatAssessment;

    /** 推荐行动方案 */
    @JsonProperty("recommended_action")
    private ActionPlan recommendedAction;

    /** 规则优化建议 */
    @JsonProperty("rule_proposal")
    private RuleProposal ruleProposal;

    /** 不确定性标识列表，如"低置信度分类"、"传感器数据不一致"、"行为模式异常" */
    @JsonProperty("uncertainty_flags")
    private List<String> uncertaintyFlags;

    /** 是否需要人工复核 */
    @JsonProperty("needs_human_review")
    private boolean needsHumanReview;

    /** 需要人工复核的原因描述 */
    @JsonProperty("review_reason")
    private String reviewReason;

    // ==================== 内部类 ====================

    /**
     * 威胁评估结果
     * 综合多维度指标评分得出目标威胁等级和处置建议
     */
    @Data
    @NoArgsConstructor
    @AllArgsConstructor
    public static class ThreatAssessment {

        /** 威胁等级数值（1-5） */
        @JsonProperty("level")
        private int level;

        /** 威胁等级中文标签 */
        @JsonProperty("label")
        private String label;

        /** 威胁综合评分（0-100） */
        @JsonProperty("score")
        private double score;

        /** 评估置信度（0.0-1.0） */
        @JsonProperty("confidence")
        private double confidence;

        /** 威胁评估推理过程描述 */
        @JsonProperty("reasoning")
        private String reasoning;

        /** 各评估指标的得分，键为指标名称，值为得分 */
        @JsonProperty("indicator_scores")
        private Map<String, Double> indicatorScores;

        /** 匹配到的规则ID列表 */
        @JsonProperty("matched_rules")
        private List<String> matchedRules;

        /** 规则匹配置信度（0.0-1.0） */
        @JsonProperty("rule_confidence")
        private double ruleConfidence;
    }

    /**
     * 行动方案
     * 包含主选/备选行动、应避免的行动及执行时序
     */
    @Data
    @NoArgsConstructor
    @AllArgsConstructor
    public static class ActionPlan {

        /** 首选行动 */
        @JsonProperty("primary")
        private Action primary;

        /** 备选行动（首选失败或不可用时启用） */
        @JsonProperty("secondary")
        private Action secondary;

        /** 应避免的行动列表（可能造成附带损伤或与当前态势冲突） */
        @JsonProperty("avoid")
        private List<Action> avoid;

        /** 行动优先级（1-10，10为最高优先级） */
        @JsonProperty("priority")
        private int priority;

        /**
         * 行动执行时机：
         * IMMEDIATE-立即执行
         * WITHIN_30S-30秒内执行
         * WITHIN_60S-60秒内执行
         * WITHIN_5MIN-5分钟内执行
         * MONITOR-持续监视，暂不行动
         */
        @JsonProperty("timing")
        private String timing;

        /** 行动方案推理过程描述 */
        @JsonProperty("reasoning")
        private String reasoning;

        /** 升级条件描述，满足此条件时自动升级处置手段 */
        @JsonProperty("escalation_condition")
        private String escalationCondition;

        /** 是否需要人工复核（ROE约束可能标记此字段） */
        @JsonProperty("needs_human_review")
        private boolean needsHumanReview;
    }

    /**
     * 具体行动指令
     * 描述单一反制行动的类型、执行设备和参数
     */
    @Data
    @NoArgsConstructor
    @AllArgsConstructor
    public static class Action {

        /** 行动类型，如"RF_JAMMING"、"LASER_DESTRUCTION" */
        @JsonProperty("action_type")
        private String actionType;

        /** 执行该行动的设备ID */
        @JsonProperty("device_id")
        private String deviceId;

        /** 执行该行动的设备类型 */
        @JsonProperty("device_type")
        private String deviceType;

        /** 行动参数，如{"frequency_band": "2.4GHz", "power_percent": 80} */
        @JsonProperty("params")
        private Map<String, Object> params;
    }

    /**
     * 规则优化建议
     * 当规则引擎置信度不足或出现规则未覆盖的新场景时，建议生成或优化规则
     */
    @Data
    @NoArgsConstructor
    @AllArgsConstructor
    public static class RuleProposal {

        /** 是否有规则建议 */
        @JsonProperty("proposed")
        private boolean proposed;

        /** 建议的规则名称 */
        @JsonProperty("rule_name")
        private String ruleName;

        /** 建议的规则内容（自然语言或规则表达式） */
        @JsonProperty("rule_content")
        private String ruleContent;

        /** 建议置信度（0.0-1.0） */
        @JsonProperty("confidence")
        private double confidence;

        /** 建议推理过程描述 */
        @JsonProperty("reasoning")
        private String reasoning;

        /** 建议来源，如"L2_DOCTRINE"、"L3_TACTICAL"、"L4_LEARNED" */
        @JsonProperty("source")
        private String source;
    }
}
