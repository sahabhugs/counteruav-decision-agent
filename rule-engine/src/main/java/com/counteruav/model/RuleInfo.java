package com.counteruav.model;

import com.fasterxml.jackson.annotation.JsonFormat;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

/**
 * 规则信息实体类
 * 描述规则引擎中的单条规则，包含规则的层级、内容、状态和版本信息
 */
@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class RuleInfo {

    /** 规则唯一标识 */
    @JsonProperty("rule_id")
    private String ruleId;

    /** 规则名称 */
    @JsonProperty("name")
    private String name;

    /**
     * 规则层级：
     * 1-L1态势感知层
     * 2-L2条令规则层
     * 3-L3战术规则层
     * 4-L4学习规则层
     */
    @JsonProperty("layer")
    private int layer;

    /** 规则内容（自然语言或规则表达式） */
    @JsonProperty("content")
    private String content;

    /** 规则触发的行动类型 */
    @JsonProperty("action_type")
    private String actionType;

    /** 规则置信度（0.0-1.0） */
    @JsonProperty("confidence")
    private double confidence;

    /**
     * 规则来源：
     * L2_DOCTRINE-条令规则
     * L3_TACTICAL-战术规则
     * L4_LEARNED-学习规则
     */
    @JsonProperty("source")
    private String source;

    /**
     * 规则状态：
     * ACTIVE-生效中
     * PENDING-待审核
     * DEPRECATED-已弃用
     * DISABLED-已禁用
     */
    @JsonProperty("status")
    private String status;

    /** 规则版本号 */
    @JsonProperty("version")
    private String version;

    /** 规则文件路径（DRL文件或规则配置文件） */
    @JsonProperty("file_path")
    private String filePath;

    /** 规则创建时间 */
    @JsonProperty("create_time")
    @JsonFormat(shape = JsonFormat.Shape.STRING, pattern = "yyyy-MM-dd'T'HH:mm:ss")
    private LocalDateTime createTime;

    /** 规则最后更新时间 */
    @JsonProperty("update_time")
    @JsonFormat(shape = JsonFormat.Shape.STRING, pattern = "yyyy-MM-dd'T'HH:mm:ss")
    private LocalDateTime updateTime;
}
