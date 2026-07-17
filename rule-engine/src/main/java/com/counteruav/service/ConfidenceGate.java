package com.counteruav.service;

import com.counteruav.model.Target;
import com.counteruav.model.Target.DroneCategory;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * 置信度评估与LLM上报门控服务
 * <p>
 * 对规则引擎的决策进行多维度置信度评估，当置信度不足或触发特殊条件时，
 * 将决策请求上报至LLM Agent进行辅助决策。
 * </p>
 *
 * <h3>五个置信度评估维度</h3>
 * <ol>
 *   <li><b>规则一致性</b> (权重 0.30)：匹配规则的数量和一致性</li>
 *   <li><b>传感器质量</b> (权重 0.25)：传感器信噪比(SNR)反映的数据质量</li>
 *   <li><b>分类置信度</b> (权重 0.20)：目标分类模型的置信度</li>
 *   <li><b>规则覆盖度</b> (权重 0.15)：规则来自不同层级的覆盖情况</li>
 *   <li><b>历史准确率</b> (权重 0.10)：相似场景历史决策的批准率</li>
 * </ol>
 *
 * <h3>LLM上报触发条件（5个）</h3>
 * <ol>
 *   <li>EVT开集识别：目标分类置信度低于0.65</li>
 *   <li>规则冲突：多个规则相同优先级但不同结论</li>
 *   <li>复合威胁：检测到3个及以上威胁行为标签</li>
 *   <li>置信度不足：综合置信度低于阈值(默认0.80)</li>
 *   <li>未知机型：无法识别无人机类别</li>
 * </ol>
 *
 * @author counteruav
 * @since 1.0.0
 */
@Slf4j
@Service
public class ConfidenceGate {

    /** 默认置信度阈值，低于此值时触发LLM上报 */
    @Value("${counteruav.confidence.threshold:0.80}")
    private double confidenceThreshold;

    /** 规则一致性维度权重 */
    private static final double W_RULE_CONSISTENCY = 0.30;

    /** 传感器质量维度权重 */
    private static final double W_SENSOR_QUALITY = 0.25;

    /** 分类置信度维度权重 */
    private static final double W_CLASSIFICATION = 0.20;

    /** 规则覆盖度维度权重 */
    private static final double W_RULE_COVERAGE = 0.15;

    /** 历史准确率维度权重 */
    private static final double W_HISTORICAL = 0.10;

    /** EVT开集识别分类置信度阈值 */
    private static final double EVT_OPEN_SET_THRESHOLD = 0.65;

    /** 复合威胁行为标签数量阈值 */
    private static final int COMPLEX_THREAT_TAG_THRESHOLD = 3;

    /** 规则覆盖的层级标识前缀 */
    private static final String[] RULE_LAYER_PREFIXES = {"L1-", "L2-", "L3-", "L4-"};

    /** 总层级数 */
    private static final int TOTAL_RULE_LAYERS = 4;

    /**
     * 计算规则引擎决策的综合置信度
     * <p>
     * 置信度 = 0.30 * 规则一致性 + 0.25 * 传感器质量 + 0.20 * 分类置信度
     *        + 0.15 * 规则覆盖度 + 0.10 * 历史准确率
     * </p>
     * <p>
     * 所有权重之和为1.0，各维度得分范围均为[0.0, 1.0]。
     * 结果值越接近1.0表示规则引擎决策越可信。
     * </p>
     *
     * @param target             待评估目标
     * @param matchedRules       匹配到的规则ID列表（如["L1-01", "L2-03", "L3-07"]）
     * @param sensorStatus       传感器状态Map（sensorId → SNR(dB)），可为null或空
     * @param historicalAccuracy 历史相似决策批准率（0.0-1.0）
     * @return 综合置信度 (0.0-1.0)
     */
    public double calculateConfidence(Target target, List<String> matchedRules,
                                      Map<String, Double> sensorStatus,
                                      double historicalAccuracy) {
        // 各维度独立计算
        double ruleConsistency = calcRuleConsistency(matchedRules);
        double sensorQuality = calcSensorQuality(sensorStatus);
        double classificationConf = clamp(target.getMaxClassConfidence(), 0.0, 1.0);
        double ruleCoverage = calcRuleCoverage(matchedRules);
        double historical = clamp(historicalAccuracy, 0.0, 1.0);

        // 加权求和
        double confidence = W_RULE_CONSISTENCY * ruleConsistency
                + W_SENSOR_QUALITY * sensorQuality
                + W_CLASSIFICATION * classificationConf
                + W_RULE_COVERAGE * ruleCoverage
                + W_HISTORICAL * historical;

        // 确保结果在有效范围内
        confidence = clamp(confidence, 0.0, 1.0);

        if (log.isDebugEnabled()) {
            log.debug("目标[{}]置信度计算: 规则一致性={}, 传感器质量={}, 分类置信度={}, 规则覆盖={}, 历史准确率={} → 综合={}",
                    target.getTargetId(),
                    String.format("%.4f", ruleConsistency), String.format("%.4f", sensorQuality),
                    String.format("%.4f", classificationConf), String.format("%.4f", ruleCoverage),
                    String.format("%.4f", historical), String.format("%.4f", confidence));
        }

        return confidence;
    }

    /**
     * 判断是否需要将决策上报至LLM Agent进行辅助决策
     * <p>
     * 上报条件：
     * </p>
     * <ul>
     *   <li>综合置信度低于阈值</li>
     *   <li>存在任一特殊触发条件（EVT开集、规则冲突、复合威胁、未知机型）</li>
     * </ul>
     *
     * @param target     待评估目标
     * @param confidence 已计算的综合置信度
     * @return true表示需要上报LLM，false表示规则引擎决策足够可靠
     */
    public boolean shouldEscalateToLLM(Target target, double confidence) {
        // 置信度低于阈值：直接上报
        if (confidence < confidenceThreshold) {
            log.info("目标[{}]置信度({})低于阈值({})，上报LLM",
                    target.getTargetId(), String.format("%.4f", confidence), confidenceThreshold);
            return true;
        }

        // 检查特殊触发条件
        List<String> triggers = getTriggerReasons(target, confidence);
        if (!triggers.isEmpty()) {
            log.info("目标[{}]触发{}个LLM上报条件: {}",
                    target.getTargetId(), triggers.size(),
                    String.join("; ", triggers));
            return true;
        }

        return false;
    }

    /**
     * 获取触发LLM上报的具体原因列表
     * <p>
     * 对5个触发条件逐一检查，返回所有满足条件的原因描述。
     * 当所有条件均不满足时返回空列表。
     * </p>
     *
     * @param target     待评估目标
     * @param confidence 已计算的综合置信度
     * @return 触发原因描述列表（中文），无触发时为空列表
     */
    public List<String> getTriggerReasons(Target target, double confidence) {
        List<String> reasons = new ArrayList<>();

        // 条件1：EVT开集识别 - 分类置信度低于0.65
        double classConf = target.getMaxClassConfidence();
        if (classConf < EVT_OPEN_SET_THRESHOLD) {
            reasons.add("EVT开集识别: 目标分类置信度低于阈值 (当前: "
                    + String.format("%.2f", classConf)
                    + " < " + EVT_OPEN_SET_THRESHOLD + ")");
        }

        // 条件2：规则冲突 - EVT标记为开集（简化判断：实际系统需检查规则salience冲突）
        if (target.isEvtOpenSet()) {
            reasons.add("存在规则冲突或不确定分类（EVT开集标记）");
        }

        // 条件3：复合威胁 - 检测到3个及以上威胁行为标签
        List<String> tags = target.getThreatBehaviorTags();
        if (tags != null && tags.size() >= COMPLEX_THREAT_TAG_THRESHOLD) {
            reasons.add("复合威胁: 检测到" + tags.size() + "个威胁行为标签 (阈值: "
                    + COMPLEX_THREAT_TAG_THRESHOLD + "个)");
        }

        // 条件4：置信度低于阈值
        if (confidence < confidenceThreshold) {
            reasons.add("置信度低于阈值: "
                    + String.format("%.4f", confidence) + " < " + confidenceThreshold);
        }

        // 条件5：未知机型
        if (target.getDroneCategory() == DroneCategory.UNKNOWN) {
            reasons.add("未知机型类别，无法通过规则引擎准确判断威胁，需要LLM辅助识别");
        }

        return reasons;
    }

    /**
     * 获取当前配置的置信度阈值
     *
     * @return 置信度阈值
     */
    public double getConfidenceThreshold() {
        return confidenceThreshold;
    }

    // ======================== 各维度计算方法 ========================

    /**
     * 计算规则一致性得分
     * <p>
     * 规则数量反映了决策的证据充分程度：
     * </p>
     * <ul>
     *   <li>≥5条规则匹配 → 高一致性 (0.95)</li>
     *   <li>3-4条规则匹配 → 较高一致性 (0.85)</li>
     *   <li>2条规则匹配 → 中等一致性 (0.75)</li>
     *   <li>1条规则匹配 → 较低一致性 (0.60)</li>
     *   <li>0条规则匹配 → 低一致性 (0.50)</li>
     * </ul>
     * <p>
     * 注意：此处规则数量作为一致性的代理指标。严格的一致性分析需要
     * 检查规则间是否存在相同salience但不同action的冲突。
     * </p>
     *
     * @param matchedRules 匹配到的规则ID列表
     * @return 一致性得分 (0.0-1.0)
     */
    private double calcRuleConsistency(List<String> matchedRules) {
        if (matchedRules == null || matchedRules.isEmpty()) {
            return 0.50;
        }

        int count = matchedRules.size();
        if (count >= 5) {
            return 0.95;
        }
        if (count >= 3) {
            return 0.85;
        }
        if (count >= 2) {
            return 0.75;
        }
        return 0.60;
    }

    /**
     * 计算传感器质量得分
     * <p>
     * 基于各传感器的信噪比(SNR)平均值映射到质量得分：
     * </p>
     * <ul>
     *   <li>SNR ≥ 20dB → 0.95 (优秀)</li>
     *   <li>SNR ≥ 15dB → 0.85 (良好)</li>
     *   <li>SNR ≥ 10dB → 0.70 (一般)</li>
     *   <li>SNR ≥ 5dB  → 0.50 (较差)</li>
     *   <li>SNR &lt; 5dB → 0.30 (很差)</li>
     * </ul>
     * <p>
     * 当无传感器数据时返回默认值0.50。
     * </p>
     *
     * @param sensorStatus 传感器状态Map (sensorId → SNR_dB)
     * @return 传感器质量得分 (0.0-1.0)
     */
    private double calcSensorQuality(Map<String, Double> sensorStatus) {
        if (sensorStatus == null || sensorStatus.isEmpty()) {
            return 0.50;
        }

        double avgSnr = sensorStatus.values().stream()
                .mapToDouble(Double::doubleValue)
                .average()
                .orElse(0.0);

        if (avgSnr >= 20) {
            return 0.95;
        }
        if (avgSnr >= 15) {
            return 0.85;
        }
        if (avgSnr >= 10) {
            return 0.70;
        }
        if (avgSnr >= 5) {
            return 0.50;
        }
        return 0.30;
    }

    /**
     * 计算规则覆盖度得分
     * <p>
     * 检查匹配到的规则来自哪些推理层级（L1-L4）：
     * </p>
     * <ul>
     *   <li>L1：物理层 - 传感器数据直接推理</li>
     *   <li>L2：条令层 - 战术条令规则</li>
     *   <li>L3：战术层 - 战术态势分析</li>
     *   <li>L4：学习层 - 历史案例类比</li>
     * </ul>
     * <p>
     * 覆盖层级越多说明决策依据越全面。得分 = 覆盖层级数 / 总层级数。
     * </p>
     *
     * @param matchedRules 匹配到的规则ID列表
     * @return 覆盖度得分 (0.0-1.0)
     */
    private double calcRuleCoverage(List<String> matchedRules) {
        if (matchedRules == null || matchedRules.isEmpty()) {
            return 0.0;
        }

        // 统计规则覆盖的层级
        Set<String> coveredLayers = new HashSet<>();
        for (String rule : matchedRules) {
            for (int i = 0; i < RULE_LAYER_PREFIXES.length; i++) {
                if (rule.startsWith(RULE_LAYER_PREFIXES[i])) {
                    coveredLayers.add(RULE_LAYER_PREFIXES[i]);
                    break;
                }
            }
        }

        // 至少覆盖一层（兜底：若有规则但均未匹配已知前缀，计为1层）
        if (coveredLayers.isEmpty()) {
            return 1.0 / TOTAL_RULE_LAYERS;
        }

        return (double) coveredLayers.size() / TOTAL_RULE_LAYERS;
    }

    // ======================== 工具方法 ========================

    /**
     * 将值限定在指定范围内
     *
     * @param value 原始值
     * @param min   最小值
     * @param max   最大值
     * @return 限定后的值
     */
    private double clamp(double value, double min, double max) {
        if (value < min) return min;
        if (value > max) return max;
        return value;
    }
}
