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
 * 目标实体类
 * 表示探测到的无人机目标，包含位置、运动参数、射频特征、分类结果及威胁评估等完整信息
 */
@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class Target {

    /** 目标唯一标识 */
    @JsonProperty("target_id")
    private String targetId;

    /** 航迹号，用于与雷达/探测系统关联 */
    @JsonProperty("track_id")
    private String trackId;

    /** 探测发现时间 */
    @JsonProperty("detection_time")
    @JsonFormat(shape = JsonFormat.Shape.STRING, pattern = "yyyy-MM-dd'T'HH:mm:ss")
    private LocalDateTime detectionTime;

    /** 目标当前位置（经纬度+海拔） */
    @JsonProperty("position")
    private LatLonAlt position;

    /** 飞行速度（米/秒） */
    @JsonProperty("velocity_ms")
    private double velocityMs;

    /** 航向角（度），0为正北，顺时针 */
    @JsonProperty("heading_deg")
    private double headingDeg;

    /** 径向速度（米/秒），相对于防御中心的径向分量 */
    @JsonProperty("radial_speed_ms")
    private double radialSpeedMs;

    /** 无人机型号/类型描述 */
    @JsonProperty("drone_type")
    private String droneType;

    /** 无人机类别 */
    @JsonProperty("drone_category")
    private DroneCategory droneCategory;

    /** 最高分类置信度 */
    @JsonProperty("max_class_confidence")
    private double maxClassConfidence;

    /** 是否为开放集检测识别（即模型未见过的新类别） */
    @JsonProperty("is_evt_open_set")
    private boolean isEvtOpenSet;

    /** 分类结果Top-3列表 */
    @JsonProperty("top3_classes")
    private List<Classification> top3Classes;

    /** 威胁行为标签列表，如"高速抵近"、"低空突防"、"蜂群编队" */
    @JsonProperty("threat_behavior_tags")
    private List<String> threatBehaviorTags;

    /** 射频信号特征 */
    @JsonProperty("rf_signature")
    private RfSignature rfSignature;

    /** 是否位于居民区/人员密集区域上空 */
    @JsonProperty("is_over_civilian_area")
    private boolean isOverCivilianArea;

    /** 在防御区域内停留时间（秒） */
    @JsonProperty("dwell_time_s")
    private int dwellTimeS;

    /** 威胁等级 */
    @JsonProperty("threat_level")
    private ThreatLevel threatLevel;

    /** 威胁评分（0-100） */
    @JsonProperty("threat_score")
    private double threatScore;

    /** 威胁升级原因描述 */
    @JsonProperty("escalation_reason")
    private String escalationReason;

    /** 决策来源标识，如"RULE_ENGINE"、"LLM_AGENT"、"HYBRID" */
    @JsonProperty("decision_source")
    private String decisionSource;

    /** 主要反制策略 */
    @JsonProperty("primary_strategy")
    private StrategyType primaryStrategy;

    /** 备选反制策略 */
    @JsonProperty("secondary_strategy")
    private StrategyType secondaryStrategy;

    /** 匹配到的规则ID列表 */
    @JsonProperty("matched_rules")
    private List<String> matchedRules;

    // ==================== 内部类 ====================

    /**
     * 目标分类结果
     * 包含分类名称及置信度
     */
    @Data
    @NoArgsConstructor
    @AllArgsConstructor
    @Builder
    public static class Classification {

        /** 分类名称，如"DJI Mavic 3"、"DIY FPV 5inch" */
        @JsonProperty("class_name")
        private String className;

        /** 分类置信度，范围[0.0, 1.0] */
        @JsonProperty("confidence")
        private double confidence;
    }

    /**
     * 射频信号特征
     * 描述无人机通信/图传链路的射频参数
     */
    @Data
    @NoArgsConstructor
    @AllArgsConstructor
    @Builder
    public static class RfSignature {

        /** 信号中心频率（Hz） */
        @JsonProperty("frequency_hz")
        private double frequencyHz;

        /** 信号带宽（Hz） */
        @JsonProperty("bandwidth_hz")
        private double bandwidthHz;

        /** 调制方式，如"OFDM"、"FHSS"、"DSSS"、"FSK" */
        @JsonProperty("modulation_type")
        private String modulationType;

        /** 信号功率（dBm） */
        @JsonProperty("signal_power_dbm")
        private double signalPowerDbm;

        /** 信噪比（dB） */
        @JsonProperty("snr_db")
        private double snrDb;
    }

    // ==================== 枚举 ====================

    /**
     * 无人机类别枚举
     * 根据无人机构型和应用场景进行分类
     */
    public enum DroneCategory {

        /** 消费级四旋翼，如DJI系列民用航拍无人机 */
        CONSUMER_QUADCOPTER("CONSUMER_QUADCOPTER", "消费级四旋翼"),

        /** DIY穿越机，速度快、机动性强，常用于竞速或改装 */
        DIY_FPV("DIY_FPV", "DIY穿越机"),

        /** 军用固定翼无人机，航程远、载荷大 */
        MILITARY_FIXED_WING("MILITARY_FIXED_WING", "军用固定翼"),

        /** 集群/蜂群无人机，多机协同编队 */
        CLUSTER_SWARM("CLUSTER_SWARM", "集群蜂群"),

        /** 未知类型 */
        UNKNOWN("UNKNOWN", "未知");

        /** 英文代码 */
        private final String code;

        /** 中文标签 */
        private final String label;

        DroneCategory(String code, String label) {
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
         * @return 对应的枚举值，未匹配时返回UNKNOWN
         */
        public static DroneCategory fromCode(String code) {
            for (DroneCategory dc : values()) {
                if (dc.code.equalsIgnoreCase(code)) {
                    return dc;
                }
            }
            return UNKNOWN;
        }
    }

    /**
     * 反制策略类型枚举
     * 定义可用的反无人机手段，按杀伤链阶段和强度排列
     */
    public enum StrategyType {

        /** 不采取任何行动 */
        NONE("NONE", "无行动"),

        /** 持续监视跟踪，不进行干预 */
        MONITOR("MONITOR", "持续监视"),

        /** 发出声光警告驱离 */
        WARN("WARN", "警告驱离"),

        /** 发射射频干扰信号，切断无人机通信链路 */
        RF_JAMMING("RF_JAMMING", "射频干扰"),

        /** 发射欺骗式导航信号，诱导无人机偏离航线 */
        GNSS_SPOOFING("GNSS_SPOOFING", "导航诱骗"),

        /** 使用强光致盲无人机光电传感器 */
        OPTICAL_BLINDING("OPTICAL_BLINDING", "光学致盲"),

        /** 使用高能激光摧毁无人机 */
        LASER_DESTRUCTION("LASER_DESTRUCTION", "激光摧毁"),

        /** 发射动能弹丸或拦截弹进行物理摧毁 */
        KINETIC_INTERCEPT("KINETIC_INTERCEPT", "动能拦截"),

        /** 全频段阻塞干扰，覆盖所有常见无人机频段 */
        FULL_BAND_JAMMING("FULL_BAND_JAMMING", "全频段干扰"),

        /** 发射捕网进行物理捕获 */
        NET_CAPTURE("NET_CAPTURE", "网捕拦截"),

        /** 高功率微波脉冲，烧毁无人机电子元件 */
        HPM_PULSE("HPM_PULSE", "高功率微波脉冲");

        /** 英文代码 */
        private final String code;

        /** 中文标签 */
        private final String label;

        StrategyType(String code, String label) {
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
         * @return 对应的枚举值，未匹配时返回NONE
         */
        public static StrategyType fromCode(String code) {
            for (StrategyType st : values()) {
                if (st.code.equalsIgnoreCase(code)) {
                    return st;
                }
            }
            return NONE;
        }
    }

    /**
     * 无人机意图枚举
     * 根据目标运动特征和行为模式推断其作战意图
     */
    public enum Intent {

        /** 无法判断意图 */
        UNKNOWN("UNKNOWN", "未知"),

        /** 侦察探测，通常在防区外围徘徊 */
        RECONNAISSANCE("RECONNAISSANCE", "侦察"),

        /** 快速抵近目标区域 */
        RAPID_APPROACH("RAPID_APPROACH", "快速抵近"),

        /** 在目标上空盘旋侦察/监视 */
        LOITERING("LOITERING", "盘旋侦察"),

        /** 确认的攻击行为 */
        ATTACK("ATTACK", "攻击"),

        /** 规避机动，试图摆脱跟踪或反制 */
        EVASIVE("EVASIVE", "规避机动");

        /** 英文代码 */
        private final String code;

        /** 中文标签 */
        private final String label;

        Intent(String code, String label) {
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
         * @return 对应的枚举值，未匹配时返回UNKNOWN
         */
        public static Intent fromCode(String code) {
            for (Intent intent : values()) {
                if (intent.code.equalsIgnoreCase(code)) {
                    return intent;
                }
            }
            return UNKNOWN;
        }
    }
}
