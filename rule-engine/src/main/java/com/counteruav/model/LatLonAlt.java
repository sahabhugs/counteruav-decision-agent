package com.counteruav.model;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * 地理坐标位置类
 * 包含纬度、经度、海拔高度，并提供Haversine距离和方位角计算
 */
@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class LatLonAlt {

    /** 纬度（度） */
    @JsonProperty("lat")
    private double lat;

    /** 经度（度） */
    @JsonProperty("lon")
    private double lon;

    /** 海拔高度（米） */
    @JsonProperty("alt_m")
    private double altM;

    /** 地球平均半径（米） */
    private static final double EARTH_RADIUS_M = 6371000.0;

    /**
     * 使用Haversine公式计算到另一点的地面距离（米）
     *
     * @param other 目标坐标点
     * @return 两点之间的地面距离，单位：米
     */
    public double distanceTo(LatLonAlt other) {
        double dLat = Math.toRadians(other.lat - this.lat);
        double dLon = Math.toRadians(other.lon - this.lon);
        double a = Math.sin(dLat / 2) * Math.sin(dLat / 2)
                + Math.cos(Math.toRadians(this.lat)) * Math.cos(Math.toRadians(other.lat))
                        * Math.sin(dLon / 2) * Math.sin(dLon / 2);
        double c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
        return EARTH_RADIUS_M * c;
    }

    /**
     * 计算从当前点到目标点的方位角（度）
     * 0度为正北方向，顺时针增加
     *
     * @param other 目标坐标点
     * @return 方位角，范围[0, 360)，单位：度
     */
    public double bearingTo(LatLonAlt other) {
        double lat1 = Math.toRadians(this.lat);
        double lat2 = Math.toRadians(other.lat);
        double dLon = Math.toRadians(other.lon - this.lon);

        double y = Math.sin(dLon) * Math.cos(lat2);
        double x = Math.cos(lat1) * Math.sin(lat2)
                - Math.sin(lat1) * Math.cos(lat2) * Math.cos(dLon);
        double bearing = Math.toDegrees(Math.atan2(y, x));
        return (bearing + 360) % 360;
    }

    @Override
    public String toString() {
        return String.format("(%.6f, %.6f, %.1fm)", lat, lon, altM);
    }
}
