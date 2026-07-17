package com.counteruav.util;

import com.counteruav.model.RateLimitStatus;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.time.Instant;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * LLM调用速率限制器
 * <p>
 * 管理全局和每目标的LLM调用频率，防止LLM服务过载。
 * 采用两层限流策略：
 * </p>
 * <ol>
 *   <li><b>全局分钟限流</b> - 限制每分钟所有目标的LLM调用总次数</li>
 *   <li><b>每目标分钟限流</b> - 限制每分钟对单个目标的LLM调用次数</li>
 *   <li><b>全局冷却</b> - 达到全局限制后触发冷却期，期间拒绝所有调用</li>
 * </ol>
 * <p>
 * 所有计数器使用分钟级滑动窗口，窗口到期后自动重置。
 * 线程安全设计：使用 {@link ConcurrentHashMap} 和 {@link AtomicInteger} 保证并发安全。
 * </p>
 *
 * @author counteruav
 * @since 1.0.0
 */
@Component
public class LLMCallRateLimiter {

    private static final Logger log = LoggerFactory.getLogger(LLMCallRateLimiter.class);

    /** 分钟窗口长度（毫秒） */
    private static final long MINUTE_WINDOW_MS = 60_000L;

    @Value("${counteruav.llm.rate-limit.max-calls-per-minute:10}")
    private int maxCallsPerMinute;

    @Value("${counteruav.llm.rate-limit.cooldown-ms:5000}")
    private long cooldownMs;

    @Value("${counteruav.llm.rate-limit.max-calls-per-target:3}")
    private int maxCallsPerTarget;

    /** 全局分钟窗口计数器 */
    private final AtomicInteger globalMinuteCount = new AtomicInteger(0);

    /** 全局窗口起始时间戳（毫秒） */
    private volatile long currentMinuteStart = System.currentTimeMillis();

    /** 每目标滑动窗口映射 */
    private final ConcurrentHashMap<String, TargetRateWindow> targetWindows = new ConcurrentHashMap<>();

    /** 全局冷却截止时间戳（毫秒），0表示未在冷却中 */
    private volatile long globalCooldownUntil = 0;

    /**
     * 尝试获取LLM调用许可。
     * <p>
     * 按顺序检查以下条件：
     * </p>
     * <ol>
     *   <li>全局冷却状态 - 在冷却期内拒绝所有调用</li>
     *   <li>全局分钟计数 - 达到上限时触发冷却并拒绝</li>
     *   <li>每目标分钟计数 - 达到上限时拒绝该目标调用</li>
     * </ol>
     * <p>
     * 所有检查通过后，同时递增全局计数和目标计数，返回 true。
     * </p>
     * <p>
     * 注意：此方法使用 synchronized 确保检查和计数的原子性，
     * 在高并发场景下可能成为瓶颈。如需更高性能，可考虑使用
     * {@link java.util.concurrent.Semaphore} 或令牌桶算法替代。
     * </p>
     *
     * @param targetId 目标唯一标识，不能为null或空字符串
     * @return true 允许调用；false 被限流拒绝
     */
    public synchronized boolean tryAcquire(String targetId) {
        if (targetId == null || targetId.trim().isEmpty()) {
            log.warn("目标ID为空，拒绝LLM调用");
            return false;
        }

        long now = System.currentTimeMillis();

        // 1. 检查全局冷却状态
        if (now < globalCooldownUntil) {
            long remainingSeconds = (globalCooldownUntil - now) / 1000;
            log.warn("LLM调用被全局冷却限制，剩余冷却时间: {}秒", remainingSeconds);
            return false;
        }

        // 2. 检查并重置全局分钟窗口
        checkAndResetGlobalWindow(now);
        if (globalMinuteCount.get() >= maxCallsPerMinute) {
            log.warn("LLM调用达到全局速率限制 ({}次/分钟)，触发冷却 {}毫秒",
                    maxCallsPerMinute, cooldownMs);
            globalCooldownUntil = now + cooldownMs;
            return false;
        }

        // 3. 检查每目标限制
        TargetRateWindow targetWindow = targetWindows.computeIfAbsent(
                targetId, k -> new TargetRateWindow());
        synchronized (targetWindow) {
            checkAndResetTargetWindow(targetWindow, now);
            if (targetWindow.count.get() >= maxCallsPerTarget) {
                log.warn("目标[{}]的LLM调用达到限制 ({}次/分钟)", targetId, maxCallsPerTarget);
                return false;
            }
            targetWindow.count.incrementAndGet();
        }

        // 4. 递增全局计数
        globalMinuteCount.incrementAndGet();
        log.debug("LLM调用许可已授予，目标: {}, 全局计数: {}/{}",
                targetId, globalMinuteCount.get(), maxCallsPerMinute);
        return true;
    }

    /**
     * 获取当前限流器运行状态。
     * <p>
     * 返回的状态信息包括当前分钟窗口已调用次数、最大限制和冷却剩余时间，
     * 可用于监控面板展示或健康检查端点。
     * </p>
     *
     * @return 当前限流状态快照，不会为null
     */
    public RateLimitStatus getStatus() {
        long now = System.currentTimeMillis();
        checkAndResetGlobalWindow(now);
        long cooldownRemaining = Math.max(0, globalCooldownUntil - now) / 1000;

        RateLimitStatus status = new RateLimitStatus();
        status.setCurrentMinuteCount(globalMinuteCount.get());
        status.setMaxPerMinute(maxCallsPerMinute);
        status.setCooldownRemainingSeconds(cooldownRemaining);
        return status;
    }

    /**
     * 手动触发全局冷却。
     * <p>
     * 在某些异常场景下（如LLM服务返回大量5xx错误），
     * 可通过此方法主动进入冷却期以保护LLM服务。
     * 冷却时长使用配置的 cooldown-ms 值。
     * </p>
     */
    public void triggerCooldown() {
        globalCooldownUntil = System.currentTimeMillis() + cooldownMs;
        log.info("手动触发LLM全局冷却，持续{}毫秒，冷却至 {}",
                cooldownMs, Instant.ofEpochMilli(globalCooldownUntil));
    }

    /**
     * 重置所有计数器。
     * <p>
     * 清除全局计数、目标窗口计数和冷却状态。
     * 主要用于测试环境重置或紧急情况下的人工干预。
     * </p>
     */
    public void reset() {
        globalMinuteCount.set(0);
        currentMinuteStart = System.currentTimeMillis();
        globalCooldownUntil = 0;
        targetWindows.clear();
        log.info("LLM速率限制器已完全重置");
    }

    /**
     * 清理过期的目标窗口。
     * <p>
     * 移除超过2分钟未活动的目标窗口记录，防止内存泄漏。
     * 建议通过定时任务（如 @Scheduled）定期调用，例如每5分钟执行一次。
     * </p>
     *
     * @return 清理的目标窗口数量
     */
    public int cleanupStaleWindows() {
        long now = System.currentTimeMillis();
        long staleThreshold = 2 * MINUTE_WINDOW_MS; // 超过2分钟未活动视为过期
        int removedCount = 0;

        for (Map.Entry<String, TargetRateWindow> entry : targetWindows.entrySet()) {
            TargetRateWindow window = entry.getValue();
            if (now - window.windowStart > staleThreshold
                    && window.count.get() == 0) {
                targetWindows.remove(entry.getKey());
                removedCount++;
            }
        }

        if (removedCount > 0) {
            log.info("清理了{}个过期的目标速率窗口", removedCount);
        }
        return removedCount;
    }

    /**
     * 获取当前活跃的目标窗口数量。
     *
     * @return 活跃目标窗口数
     */
    public int getActiveTargetCount() {
        return targetWindows.size();
    }

    // ======================== 内部方法 ========================

    /**
     * 检查并重置全局分钟窗口。
     * 如果当前时间已超出当前窗口的60秒范围，重置计数器并更新窗口起始时间。
     *
     * @param now 当前时间戳（毫秒）
     */
    private void checkAndResetGlobalWindow(long now) {
        if (now - currentMinuteStart > MINUTE_WINDOW_MS) {
            globalMinuteCount.set(0);
            currentMinuteStart = now;
            log.debug("全局分钟窗口已重置");
        }
    }

    /**
     * 检查并重置目标分钟窗口。
     *
     * @param window 目标速率窗口
     * @param now    当前时间戳（毫秒）
     */
    private void checkAndResetTargetWindow(TargetRateWindow window, long now) {
        if (now - window.windowStart > MINUTE_WINDOW_MS) {
            window.count.set(0);
            window.windowStart = now;
            log.debug("目标速率窗口已重置");
        }
    }

    // ======================== 内部类 ========================

    /**
     * 单个目标的速率窗口。
     * 每个目标独立维护自己的分钟级滑动窗口计数器。
     */
    private static class TargetRateWindow {

        /** 窗口内调用计数 */
        final AtomicInteger count = new AtomicInteger(0);

        /** 当前窗口起始时间戳（毫秒） */
        volatile long windowStart = System.currentTimeMillis();
    }
}
