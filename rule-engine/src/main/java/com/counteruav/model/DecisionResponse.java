package com.counteruav.model;

import com.fasterxml.jackson.annotation.JsonFormat;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;
import java.util.List;

/**
 * 决策响应实体类
 * 表示规则引擎对一次决策请求的完整响应，包含所有目标的决策结果
 */
@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class DecisionResponse {

    /** 关联的请求ID */
    @JsonProperty("request_id")
    private String requestId;

    /** 决策唯一标识 */
    @JsonProperty("decision_id")
    private String decisionId;

    /** 决策生成时间戳 */
    @JsonProperty("timestamp")
    @JsonFormat(shape = JsonFormat.Shape.STRING, pattern = "yyyy-MM-dd'T'HH:mm:ss")
    private LocalDateTime timestamp;

    /**
     * 决策来源：
     * RULE_ENGINE-纯规则引擎决策
     * LLM_AGENT-大语言模型智能体决策
     * HYBRID-混合决策（规则+LLM协同）
     */
    @JsonProperty("source")
    private String source;

    /** 决策耗时（毫秒） */
    @JsonProperty("processing_time_ms")
    private long processingTimeMs;

    /** 各目标的决策结果列表 */
    @JsonProperty("decisions")
    private List<TargetDecision> decisions;
}
