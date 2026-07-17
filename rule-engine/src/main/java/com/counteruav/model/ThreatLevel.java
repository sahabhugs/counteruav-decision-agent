package com.counteruav.model;

/**
 * 威胁等级枚举
 * 从低到高分为五级，对应不同的威胁程度和处置紧迫性
 */
public enum ThreatLevel {

    /** 低危 - 常规民用无人机，无威胁行为 */
    LOW(1, "低危"),

    /** 中危 - 可疑行为，需持续关注 */
    MEDIUM(2, "中危"),

    /** 高危 - 明确威胁行为，需立即评估 */
    HIGH(3, "高危"),

    /** 极高 - 严重威胁，需立即处置 */
    VERY_HIGH(4, "极高"),

    /** 极危 - 最高威胁等级，可能造成重大损失 */
    CRITICAL(5, "极危");

    /** 威胁等级数值 */
    private final int level;

    /** 威胁等级中文标签 */
    private final String label;

    ThreatLevel(int level, String label) {
        this.level = level;
        this.label = label;
    }

    /**
     * 获取威胁等级数值
     *
     * @return 等级数值（1-5）
     */
    public int getLevel() {
        return level;
    }

    /**
     * 获取威胁等级中文标签
     *
     * @return 中文标签
     */
    public String getLabel() {
        return label;
    }

    /**
     * 根据等级数值获取对应的威胁等级枚举
     *
     * @param level 等级数值（1-5）
     * @return 对应的威胁等级，无效值时返回LOW
     */
    public static ThreatLevel fromLevel(int level) {
        for (ThreatLevel tl : values()) {
            if (tl.level == level) {
                return tl;
            }
        }
        return LOW;
    }

    /**
     * 将TOPSIS相对贴近度映射为威胁等级
     * 映射规则：0.0-0.2 → LOW, 0.2-0.4 → MEDIUM, 0.4-0.6 → HIGH,
     *          0.6-0.8 → VERY_HIGH, 0.8-1.0 → CRITICAL
     *
     * @param cc 相对贴近度，范围[0.0, 1.0]
     * @return 对应的威胁等级
     */
    public static ThreatLevel fromClosenessCoefficient(double cc) {
        if (cc >= 0.8) {
            return CRITICAL;
        }
        if (cc >= 0.6) {
            return VERY_HIGH;
        }
        if (cc >= 0.4) {
            return HIGH;
        }
        if (cc >= 0.2) {
            return MEDIUM;
        }
        return LOW;
    }
}
