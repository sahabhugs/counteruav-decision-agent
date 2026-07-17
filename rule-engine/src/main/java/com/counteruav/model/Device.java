package com.counteruav.model;

import com.fasterxml.jackson.annotation.JsonFormat;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDate;
import java.util.List;

/**
 * 反制设备实体类
 * 表示可用于反无人机作战的各类设备，包含设备状态、性能参数和健康指标
 */
@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class Device {

    /** 设备唯一标识 */
    @JsonProperty("device_id")
    private String deviceId;

    /** 设备类型 */
    @JsonProperty("type")
    private DeviceType type;

    /** 设备当前状态 */
    @JsonProperty("status")
    private DeviceStatus status;

    /** 设备部署位置 */
    @JsonProperty("position")
    private LatLonAlt position;

    /** 有效作用范围（米） */
    @JsonProperty("effective_range_m")
    private double effectiveRangeM;

    /** 频率覆盖范围，如["2.4GHz", "5.8GHz", "1.5GHz"] */
    @JsonProperty("frequency_coverage")
    private List<String> frequencyCoverage;

    /** 最大等效全向辐射功率（瓦） */
    @JsonProperty("max_erp_w")
    private int maxErpW;

    /** 当前正在处置的目标ID，空闲时为null */
    @JsonProperty("current_target_id")
    private String currentTargetId;

    /** 设备健康指标 */
    @JsonProperty("health_metrics")
    private HealthMetrics healthMetrics;

    /** 支持的导航星座列表（用于GNSS诱骗设备），如["GPS_L1", "GPS_L2", "GLONASS", "BEIDOU", "GALILEO"] */
    @JsonProperty("supported_constellations")
    private List<String> supportedConstellations;

    // ==================== 内部类 ====================

    /**
     * 设备健康指标
     * 描述设备的运行状态和维护信息
     */
    @Data
    @NoArgsConstructor
    @AllArgsConstructor
    @Builder
    public static class HealthMetrics {

        /** 累计运行时长（小时） */
        @JsonProperty("uptime_hours")
        private double uptimeHours;

        /** 最近一次维护日期 */
        @JsonProperty("last_maintenance_date")
        @JsonFormat(shape = JsonFormat.Shape.STRING, pattern = "yyyy-MM-dd")
        private LocalDate lastMaintenanceDate;

        /** 累计故障次数 */
        @JsonProperty("error_count")
        private int errorCount;

        /** 校准状态，如"CALIBRATED"、"NEEDS_CALIBRATION"、"UNCALIBRATED" */
        @JsonProperty("calibration_status")
        private String calibrationStatus;

        /** 当前功率输出百分比（相对于额定功率） */
        @JsonProperty("power_output_percent")
        private double powerOutputPercent;
    }

    // ==================== 枚举 ====================

    /**
     * 反制设备类型枚举
     */
    public enum DeviceType {

        /** 射频干扰器 - 发射干扰信号阻断无人机通信 */
        RF_JAMMER("RF_JAMMER", "射频干扰器"),

        /** 导航诱骗设备 - 发射虚假卫星导航信号 */
        GNSS_SPOOFER("GNSS_SPOOFER", "导航诱骗设备"),

        /** 激光武器 - 高能激光定向毁伤 */
        LASER_WEAPON("LASER_WEAPON", "激光武器"),

        /** 动能拦截器 - 发射弹丸或拦截弹 */
        KINETIC_INTERCEPTOR("KINETIC_INTERCEPTOR", "动能拦截器"),

        /** 光学传感器 - 光电探测与跟踪 */
        OPTICAL_SENSOR("OPTICAL_SENSOR", "光学传感器"),

        /** 雷达 - 无线电探测与测距 */
        RADAR("RADAR", "雷达"),

        /** 高功率微波装置 - 微波脉冲毁伤电子设备 */
        HPM_DEVICE("HPM_DEVICE", "高功率微波装置"),

        /** 网捕枪 - 发射捕网物理捕获无人机 */
        NET_GUN("NET_GUN", "网捕枪");

        /** 英文代码 */
        private final String code;

        /** 中文标签 */
        private final String label;

        DeviceType(String code, String label) {
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
        public static DeviceType fromCode(String code) {
            for (DeviceType dt : values()) {
                if (dt.code.equalsIgnoreCase(code)) {
                    return dt;
                }
            }
            return null;
        }
    }

    /**
     * 设备状态枚举
     */
    public enum DeviceStatus {

        /** 在线待命，可随时接受任务 */
        ONLINE("ONLINE", "在线"),

        /** 离线不可用 */
        OFFLINE("OFFLINE", "离线"),

        /** 已分配任务，正在执行反制行动 */
        ENGAGED("ENGAGED", "已分配"),

        /** 维护保养中 */
        MAINTENANCE("MAINTENANCE", "维护中"),

        /** 故障状态，需维修 */
        FAULT("FAULT", "故障");

        /** 英文代码 */
        private final String code;

        /** 中文标签 */
        private final String label;

        DeviceStatus(String code, String label) {
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
         * @return 对应的枚举值，未匹配时返回OFFLINE
         */
        public static DeviceStatus fromCode(String code) {
            for (DeviceStatus ds : values()) {
                if (ds.code.equalsIgnoreCase(code)) {
                    return ds;
                }
            }
            return OFFLINE;
        }
    }
}
