package com.counteruav.model;

import com.fasterxml.jackson.annotation.JsonFormat;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;
import java.util.Map;

/**
 * 指挥员反馈请求实体类
 * 用于指挥员对规则引擎决策结果进行审核反馈，包括批准、驳回或修改后执行
 */
@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class FeedbackRequest {

    /** 关联的决策ID */
    @JsonProperty("decision_id")
    private String decisionId;

    /** 关联的目标ID */
    @JsonProperty("target_id")
    private String targetId;

    /** 指挥员唯一标识 */
    @JsonProperty("commander_id")
    private String commanderId;

    /** 反馈时间戳 */
    @JsonProperty("timestamp")
    @JsonFormat(shape = JsonFormat.Shape.STRING, pattern = "yyyy-MM-dd'T'HH:mm:ss")
    private LocalDateTime timestamp;

    /** 指挥员裁决结果 */
    @JsonProperty("verdict")
    private Verdict verdict;

    /** 指挥员指定的替代行动方案（当verdict为MODIFIED时有效） */
    @JsonProperty("override")
    private OverrideAction override;

    /** 驳回原因（当verdict为REJECTED时填写） */
    @JsonProperty("rejection_reason")
    private String rejectionReason;

    /** 指挥员备注/评论 */
    @JsonProperty("comments")
    private String comments;

    // ==================== 内部类 ====================

    /**
     * 指挥员替代行动方案
     * 当指挥员选择修改后执行时，提供自定义的主选和备选行动
     */
    @Data
    @NoArgsConstructor
    @AllArgsConstructor
    @Builder
    public static class OverrideAction {

        /** 主要行动类型 */
        @JsonProperty("primary_action_type")
        private String primaryActionType;

        /** 主要行动的执行设备ID */
        @JsonProperty("primary_device_id")
        private String primaryDeviceId;

        /** 主要行动参数 */
        @JsonProperty("primary_params")
        private Map<String, Object> primaryParams;

        /** 备选行动类型 */
        @JsonProperty("secondary_action_type")
        private String secondaryActionType;

        /** 备选行动的执行设备ID */
        @JsonProperty("secondary_device_id")
        private String secondaryDeviceId;

        /** 备选行动参数 */
        @JsonProperty("secondary_params")
        private Map<String, Object> secondaryParams;

        /** 修改原因说明 */
        @JsonProperty("reason")
        private String reason;
    }

    // ==================== 枚举 ====================

    /**
     * 指挥员裁决结果枚举
     */
    public enum Verdict {

        /** 批准 - 同意规则引擎的决策方案 */
        APPROVED("APPROVED", "批准"),

        /** 驳回 - 拒绝规则引擎的决策方案 */
        REJECTED("REJECTED", "驳回"),

        /** 修改后执行 - 对决策方案进行修改后批准执行 */
        MODIFIED("MODIFIED", "修改后执行");

        /** 英文代码 */
        private final String code;

        /** 中文标签 */
        private final String label;

        Verdict(String code, String label) {
            this.code = code;
            this.label = label;
        }

        public String getCode() {
            return code;
        }

        public String getLabel() {
            return label;
        }

        /**
         * 根据代码获取枚举值
         *
         * @param code 英文代码，不区分大小写
         * @return 对应的枚举值，未匹配时返回null
         */
        public static Verdict fromCode(String code) {
            for (Verdict v : values()) {
                if (v.code.equalsIgnoreCase(code)) {
                    return v;
                }
            }
            return null;
        }
    }
}
