package com.counteruav.service;

import com.counteruav.model.DecisionResponse;
import com.counteruav.model.FeedbackRequest;
import com.counteruav.model.TargetDecision;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.stream.Collectors;

/**
 * 决策日志与反馈管理服务
 * <p>
 * 提供决策日志的持久化存储、查询和历史准确率统计功能。
 * 当前实现基于内存存储（ConcurrentHashMap），结构设计为便于后续迁移至数据库
 * （如MySQL + MyBatis-Plus或PostgreSQL）。
 * </p>
 *
 * <h3>存储设计</h3>
 * <ul>
 *   <li><b>决策存储</b>：以decisionId为键，存储完整DecisionResponse</li>
 *   <li><b>反馈存储</b>：以decisionId + "_" + targetId为复合键，存储FeedbackRequest</li>
 * </ul>
 *
 * <h3>迁移到数据库的注意事项</h3>
 * <ul>
 *   <li>{@link DecisionResponse} 对应 decision_log 表</li>
 *   <li>{@link TargetDecision} 对应 target_decision 表（一对多关联）</li>
 *   <li>{@link FeedbackRequest} 对应 decision_feedback 表</li>
 *   <li>建议使用MyBatis-Plus的BaseMapper简化CRUD操作</li>
 * </ul>
 *
 * @author counteruav
 * @since 1.0.0
 */
@Slf4j
@Service
public class DecisionLogService {

    /** 决策日志内存存储：decisionId → DecisionResponse */
    private final ConcurrentHashMap<String, DecisionResponse> decisionStore = new ConcurrentHashMap<>();

    /** 反馈记录内存存储：复合键(decisionId_targetId) → FeedbackRequest */
    private final ConcurrentHashMap<String, FeedbackRequest> feedbackStore = new ConcurrentHashMap<>();

    /** 日期格式化器（用于时间范围过滤） */
    private static final DateTimeFormatter DATE_FORMATTER =
            DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");

    /**
     * 保存决策日志
     * <p>
     * 将完整的决策响应对象存储到内存中。如果已存在相同decisionId的记录，
     * 将覆盖旧记录（幂等操作）。
     * </p>
     *
     * @param response 决策响应对象，不能为null
     */
    public void saveDecisionLog(DecisionResponse response) {
        if (response == null) {
            log.warn("尝试保存null决策日志，已忽略");
            return;
        }

        String decisionId = response.getDecisionId();
        if (decisionId == null || decisionId.trim().isEmpty()) {
            log.warn("决策ID为空，无法保存决策日志");
            return;
        }

        decisionStore.put(decisionId, response);

        int decisionCount = response.getDecisions() != null ? response.getDecisions().size() : 0;
        log.info("决策日志已保存: decisionId={}, 目标决策数={}, 存储总量={}",
                decisionId, decisionCount, decisionStore.size());
    }

    /**
     * 保存反馈记录
     * <p>
     * 将操作员对决策的反馈存储到内存中。反馈用于后续的历史准确率计算
     * 和策略优化。
     * </p>
     *
     * @param feedback 反馈请求对象，不能为null
     */
    public void saveFeedback(FeedbackRequest feedback) {
        if (feedback == null) {
            log.warn("尝试保存null反馈记录，已忽略");
            return;
        }

        String decisionId = feedback.getDecisionId();
        String targetId = feedback.getTargetId();

        if (decisionId == null || decisionId.trim().isEmpty()) {
            log.warn("反馈记录的决策ID为空，已忽略");
            return;
        }
        if (targetId == null || targetId.trim().isEmpty()) {
            log.warn("反馈记录的目标ID为空，已忽略");
            return;
        }

        String key = buildFeedbackKey(decisionId, targetId);
        feedbackStore.put(key, feedback);

        String verdictLabel = feedback.getVerdict() != null ? feedback.getVerdict().name() : "UNKNOWN";
        log.info("反馈记录已保存: decisionId={}, targetId={}, verdict={}, 反馈总量={}",
                decisionId, targetId, verdictLabel, feedbackStore.size());
    }

    /**
     * 获取历史决策列表
     * <p>
     * 支持按目标ID和时间范围过滤。当所有过滤器参数均为null时返回全部历史决策。
     * </p>
     *
     * @param targetId  目标ID过滤条件（可选，为null时不按目标过滤）
     * @param startTime 开始时间过滤条件（可选，格式"yyyy-MM-dd HH:mm:ss"）
     * @param endTime   结束时间过滤条件（可选，格式"yyyy-MM-dd HH:mm:ss"）
     * @return 符合条件的决策响应列表，按创建时间降序排列
     */
    public List<DecisionResponse> getDecisionHistory(String targetId, String startTime, String endTime) {
        return decisionStore.values().stream()
                .filter(d -> matchesTargetId(d, targetId))
                .filter(d -> matchesTimeRange(d, startTime, endTime))
                .sorted(Comparator.comparing(
                        DecisionResponse::getTimestamp,
                        Comparator.nullsLast(Comparator.reverseOrder())))
                .collect(Collectors.toList());
    }

    /**
     * 根据决策ID获取单个决策详情
     *
     * @param decisionId 决策唯一标识
     * @return 决策响应对象，未找到返回null
     */
    public DecisionResponse getDecisionById(String decisionId) {
        if (decisionId == null) {
            return null;
        }
        return decisionStore.get(decisionId);
    }

    /**
     * 获取相似目标的历史决策批准率
     * <p>
     * 基于所有反馈记录计算操作员批准决策的比例。
     * 用于置信度评估中的历史准确率维度。
     * </p>
     * <p>
     * 当无反馈记录时返回默认值0.80（假设规则引擎基线准确率为80%）。
     * </p>
     *
     * @param targetProfile 目标特征描述（当前版本未使用，预留用于按类别统计）
     * @return 历史批准率 (0.0-1.0)
     */
    public double getHistoricalAccuracy(String targetProfile) {
        if (feedbackStore.isEmpty()) {
            log.debug("无历史反馈记录，返回默认准确率0.80");
            return 0.80;
        }

        long total = feedbackStore.size();
        long approved = feedbackStore.values().stream()
                .filter(f -> f.getVerdict() == FeedbackRequest.Verdict.APPROVED)
                .count();

        double accuracy = (double) approved / total;
        log.debug("历史准确率计算: 总反馈={}, 批准={}, 驳回={}, 准确率={}",
                total, approved, total - approved, String.format("%.4f", accuracy));
        return accuracy;
    }

    /**
     * 获取所有反馈记录的统计信息
     *
     * @return 统计信息Map (key: "total", "approved", "rejected", "accuracy")
     */
    public Map<String, Object> getFeedbackStatistics() {
        long total = feedbackStore.size();
        long approved = feedbackStore.values().stream()
                .filter(f -> f.getVerdict() == FeedbackRequest.Verdict.APPROVED)
                .count();
        long rejected = total - approved;
        double accuracy = total > 0 ? (double) approved / total : 0.0;

        Map<String, Object> stats = new ConcurrentHashMap<>();
        stats.put("total", total);
        stats.put("approved", approved);
        stats.put("rejected", rejected);
        stats.put("accuracy", String.format("%.2f%%", accuracy * 100));
        return stats;
    }

    /**
     * 获取决策存储的当前记录数
     *
     * @return 决策记录数量
     */
    public int getDecisionCount() {
        return decisionStore.size();
    }

    /**
     * 获取反馈存储的当前记录数
     *
     * @return 反馈记录数量
     */
    public int getFeedbackCount() {
        return feedbackStore.size();
    }

    /**
     * 清除所有历史数据（用于测试或系统重置）
     */
    public void clearAll() {
        int decisionCount = decisionStore.size();
        int feedbackCount = feedbackStore.size();
        decisionStore.clear();
        feedbackStore.clear();
        log.warn("已清除所有历史数据: 决策{}条, 反馈{}条", decisionCount, feedbackCount);
    }

    // ======================== 内部过滤方法 ========================

    /**
     * 检查决策响应是否包含指定目标ID
     *
     * @param response 决策响应
     * @param targetId 目标ID（为null时始终匹配）
     * @return true表示匹配
     */
    private boolean matchesTargetId(DecisionResponse response, String targetId) {
        if (targetId == null || targetId.trim().isEmpty()) {
            return true;
        }
        if (response.getDecisions() == null) {
            return false;
        }
        return response.getDecisions().stream()
                .anyMatch(td -> targetId.equals(td.getTargetId()));
    }

    /**
     * 检查决策响应是否在指定时间范围内
     *
     * @param response  决策响应
     * @param startTime 开始时间字符串（为null时不限制下限）
     * @param endTime   结束时间字符串（为null时不限制上限）
     * @return true表示在范围内
     */
    private boolean matchesTimeRange(DecisionResponse response, String startTime, String endTime) {
        if (startTime == null && endTime == null) {
            return true;
        }

        LocalDateTime decisionTime = response.getTimestamp();
        if (decisionTime == null) {
            // 无时间信息的记录在仅指定时间范围时排除
            return false;
        }

        try {
            if (startTime != null && !startTime.trim().isEmpty()) {
                LocalDateTime start = LocalDateTime.parse(startTime, DATE_FORMATTER);
                if (decisionTime.isBefore(start)) {
                    return false;
                }
            }
            if (endTime != null && !endTime.trim().isEmpty()) {
                LocalDateTime end = LocalDateTime.parse(endTime, DATE_FORMATTER);
                if (decisionTime.isAfter(end)) {
                    return false;
                }
            }
        } catch (Exception e) {
            log.warn("时间范围解析失败: startTime={}, endTime={}, 错误: {}",
                    startTime, endTime, e.getMessage());
            // 解析失败时返回true（不过滤）
            return true;
        }

        return true;
    }

    /**
     * 构建反馈存储的复合键
     *
     * @param decisionId 决策ID
     * @param targetId   目标ID
     * @return 复合键字符串
     */
    private String buildFeedbackKey(String decisionId, String targetId) {
        return decisionId + "_" + targetId;
    }
}
