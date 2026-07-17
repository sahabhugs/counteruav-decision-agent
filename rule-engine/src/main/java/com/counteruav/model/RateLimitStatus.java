package com.counteruav.model;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * 速率限制状态实体类
 * 用于跟踪规则引擎或API接口的调用频率限制状态，支持限流监控和诊断
 */
@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class RateLimitStatus {

    /** 当前时间窗口（1分钟）内的调用次数 */
    @JsonProperty("current_minute_count")
    private int currentMinuteCount;

    /** 每分钟最大允许调用次数 */
    @JsonProperty("max_per_minute")
    private int maxPerMinute;

    /** 冷却剩余时间（秒），冷却期间拒绝新请求，0表示未在冷却中 */
    @JsonProperty("cooldown_remaining_seconds")
    private long cooldownRemainingSeconds;

    /**
     * 判断当前是否达到速率上限
     *
     * @return true表示已达速率上限，需等待冷却
     */
    public boolean isRateLimited() {
        return currentMinuteCount >= maxPerMinute;
    }

    /**
     * 判断冷却是否已结束
     *
     * @return true表示冷却期已过，可接受新请求
     */
    public boolean isCooldownExpired() {
        return cooldownRemainingSeconds <= 0;
    }

    /**
     * 判断当前是否处于冷却状态
     *
     * @return true表示处于冷却中
     */
    public boolean isInCooldown() {
        return cooldownRemainingSeconds > 0;
    }
}
