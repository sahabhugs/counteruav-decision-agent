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
 * 决策请求实体类
 * 表示一次完整的反无人机决策请求，包含目标列表、可用设备、防御区域和环境信息
 */
@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class DecisionRequest {

    /** 请求唯一标识 */
    @JsonProperty("request_id")
    private String requestId;

    /** 请求时间戳 */
    @JsonProperty("timestamp")
    @JsonFormat(shape = JsonFormat.Shape.STRING, pattern = "yyyy-MM-dd'T'HH:mm:ss")
    private LocalDateTime timestamp;

    /** 防御中心坐标 */
    @JsonProperty("defense_center")
    private LatLonAlt defenseCenter;

    /** 防护区域定义 */
    @JsonProperty("protected_zone")
    private GeoZone protectedZone;

    /** 待评估的目标列表 */
    @JsonProperty("targets")
    private List<Target> targets;

    /** 当前可用的反制设备列表 */
    @JsonProperty("available_devices")
    private List<Device> availableDevices;

    /** 环境数据 */
    @JsonProperty("environment")
    private EnvironmentalData environment;

    /** 决策模式：auto-全自动决策，manual-人工辅助决策 */
    @JsonProperty("mode")
    private String mode;

    // ==================== 内部类 ====================

    /**
     * 地理区域定义
     * 支持圆形区域和多边形区域两种定义方式
     */
    @Data
    @NoArgsConstructor
    @AllArgsConstructor
    @Builder
    public static class GeoZone {

        /** 区域唯一标识 */
        @JsonProperty("zone_id")
        private String zoneId;

        /** 区域中心点坐标 */
        @JsonProperty("center")
        private LatLonAlt center;

        /** 圆形区域半径（米），仅当zoneType为CIRCLE时有效 */
        @JsonProperty("radius_m")
        private double radiusM;

        /** 多边形区域顶点列表，仅当zoneType为POLYGON时有效 */
        @JsonProperty("vertices")
        private List<LatLonAlt> vertices;

        /** 区域类型：CIRCLE-圆形区域，POLYGON-多边形区域 */
        @JsonProperty("zone_type")
        private String zoneType;
    }

    /**
     * 环境数据
     * 描述当前作战环境的气象和电磁条件
     */
    @Data
    @NoArgsConstructor
    @AllArgsConstructor
    @Builder
    public static class EnvironmentalData {

        /** 风速（米/秒） */
        @JsonProperty("wind_speed_ms")
        private double windSpeedMs;

        /** 风向（度），0为正北，顺时针 */
        @JsonProperty("wind_direction_deg")
        private double windDirectionDeg;

        /** 环境温度（摄氏度） */
        @JsonProperty("temperature_c")
        private double temperatureC;

        /** 相对湿度（百分比） */
        @JsonProperty("humidity_percent")
        private double humidityPercent;

        /** 能见度（米） */
        @JsonProperty("visibility_m")
        private double visibilityM;

        /** 天气状况描述，如"晴"、"多云"、"小雨"、"大雾" */
        @JsonProperty("weather_condition")
        private String weatherCondition;

        /** 电磁环境描述，如"正常"、"复杂电磁环境"、"强干扰背景" */
        @JsonProperty("em_environment_desc")
        private String emEnvironmentDesc;

        /** 是否检测到GPS干扰信号 */
        @JsonProperty("gps_jamming_detected")
        private boolean gpsJammingDetected;
    }
}
