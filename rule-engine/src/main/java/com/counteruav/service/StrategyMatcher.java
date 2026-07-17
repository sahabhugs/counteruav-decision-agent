package com.counteruav.service;

import com.counteruav.model.Device;
import com.counteruav.model.Device.DeviceStatus;
import com.counteruav.model.Device.DeviceType;
import com.counteruav.model.LatLonAlt;
import com.counteruav.model.Target;
import com.counteruav.model.Target.StrategyType;
import com.counteruav.model.ThreatLevel;
import com.counteruav.model.TargetDecision;
import com.counteruav.service.ThreatEvaluator.ThreatScores;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 策略匹配与设备分配服务
 * <p>
 * 根据威胁评估结果，为每个目标匹配最优的对抗策略，
 * 并在可用设备池中进行设备分配。支持以下核心功能：
 * </p>
 * <ul>
 *   <li>基于威胁等级的分级响应策略（CRITICAL→全频段干扰+激光摧毁）</li>
 *   <li>设备资源的多目标分配（高威胁目标优先获取设备）</li>
 *   <li>交战规则(ROE)约束检查（民用区域禁致命武器）</li>
 *   <li>策略升级条件设定</li>
 * </ul>
 *
 * <h3>策略等级映射</h3>
 * <table border="1">
 *   <tr><th>威胁等级</th><th>优先级</th><th>主策略</th><th>辅助策略</th></tr>
 *   <tr><td>CRITICAL (L5)</td><td>10</td><td>全频段干扰</td><td>激光摧毁/GNSS欺骗</td></tr>
 *   <tr><td>VERY_HIGH (L4)</td><td>8</td><td>射频干扰</td><td>GNSS欺骗</td></tr>
 *   <tr><td>HIGH (L3)</td><td>5</td><td>射频干扰</td><td>GNSS欺骗(缓偏移)</td></tr>
 *   <tr><td>MEDIUM (L2)</td><td>3</td><td>声光警告</td><td>增强跟踪</td></tr>
 *   <tr><td>LOW (L1)</td><td>1</td><td>标准跟踪</td><td>无</td></tr>
 * </table>
 *
 * @author counteruav
 * @since 1.0.0
 */
@Slf4j
@Service
public class StrategyMatcher {

    @Value("${counteruav.llm.agent-url:http://localhost:8001}")
    private String llmAgentUrl;

    /**
     * 为每个目标匹配最优对抗策略并进行设备分配
     * <p>
     * 处理流程：
     * </p>
     * <ol>
     *   <li>按威胁评分降序排列目标（高威胁优先处理）</li>
     *   <li>根据威胁等级选择对应响应策略模板</li>
     *   <li>从可用设备池中分配设备</li>
     *   <li>应用ROE约束（民用区域限制、致命武器限制）</li>
     *   <li>设定策略执行时机和升级条件</li>
     * </ol>
     *
     * @param targets             待处理目标列表
     * @param threatScores        威胁评估结果Map (targetId → ThreatScores)
     * @param availableDevices    当前可用设备列表
     * @param defenseCenter       防御中心位置
     * @param isOverCivilianArea  是否位于民用区域上空
     * @return 目标ID到行动计划的映射，保持高威胁优先顺序
     */
    public Map<String, TargetDecision.ActionPlan> matchStrategies(
            List<Target> targets,
            Map<String, ThreatScores> threatScores,
            List<Device> availableDevices,
            LatLonAlt defenseCenter,
            boolean isOverCivilianArea) {

        Map<String, TargetDecision.ActionPlan> plans = new LinkedHashMap<>();

        if (targets == null || targets.isEmpty()) {
            log.warn("目标列表为空，跳过策略匹配");
            return plans;
        }

        // 按威胁评分降序排列（高威胁目标优先分配设备）
        List<Target> sortedTargets = new ArrayList<>(targets);
        sortedTargets.sort((a, b) -> {
            ThreatScores sa = threatScores.get(a.getTargetId());
            ThreatScores sb = threatScores.get(b.getTargetId());
            if (sa == null && sb == null) return 0;
            if (sa == null) return 1;
            if (sb == null) return -1;
            return Double.compare(sb.getThreatScore(), sa.getThreatScore());
        });

        // 可用设备列表（可修改副本，用于分配后移除已占设备）
        List<Device> available = new ArrayList<>(availableDevices);

        for (Target target : sortedTargets) {
            ThreatScores scores = threatScores.get(target.getTargetId());
            if (scores == null) {
                log.warn("目标[{}]缺少威胁评分，使用默认保守策略", target.getTargetId());
                scores = new ThreatScores();
                scores.setClosenessCoefficient(0.1);
                scores.setThreatScore(10.0);
                scores.setThreatLevel(ThreatLevel.LOW);
            }

            ThreatLevel level = scores.getThreatLevel();
            if (level == null) {
                level = ThreatLevel.LOW;
            }

            TargetDecision.ActionPlan plan;

            // 根据威胁等级选择响应策略
            switch (level) {
                case CRITICAL:
                    plan = buildCriticalResponse(target, available, defenseCenter);
                    break;
                case VERY_HIGH:
                    plan = buildAggressiveResponse(target, available, defenseCenter);
                    break;
                case HIGH:
                    plan = buildBalancedResponse(target, available, defenseCenter);
                    break;
                case MEDIUM:
                    plan = buildCautiousResponse(target, available, defenseCenter);
                    break;
                case LOW:
                default:
                    plan = buildConservativeResponse(target, available, defenseCenter);
                    break;
            }

            // 应用交战规则(ROE)约束
            plan = applyROEConstraints(plan, target, isOverCivilianArea);

            // 设置策略执行时机
            plan.setTiming(determineTiming(level));

            // 设置决策理由
            String reasoning = "基于威胁等级" + level.getLabel()
                    + "（贴近度系数=" + String.format("%.3f", scores.getClosenessCoefficient())
                    + "），匹配对应对抗策略";
            plan.setReasoning(reasoning);

            plans.put(target.getTargetId(), plan);
        }

        log.info("策略匹配完成: 处理目标数={}, 民用区域={}, 已分配设备剩余={}",
                sortedTargets.size(), isOverCivilianArea, available.size());
        return plans;
    }

    // ======================== 分级响应策略构建 ========================

    /**
     * CRITICAL等级响应：最高威胁 - 全频段干扰 + 激光摧毁
     * <p>
     * 适用于距离极近、高速抵近或明确攻击意图的蜂群/军用目标。
     * 优先分配全频段干扰机和激光武器，激光不可用时退化为GNSS欺骗。
     * </p>
     */
    private TargetDecision.ActionPlan buildCriticalResponse(Target target, List<Device> available,
                                                            LatLonAlt defenseCenter) {
        TargetDecision.ActionPlan plan = new TargetDecision.ActionPlan();
        Device jammer = findDevice(available, DeviceType.RF_JAMMER);
        Device laser = findDevice(available, DeviceType.LASER_WEAPON);

        plan.setPrimary(buildAction(StrategyType.FULL_BAND_JAMMING.getCode(), jammer,
                buildParams("mode", "full_band", "power_percent", 100)));

        if (laser != null) {
            plan.setSecondary(buildAction(StrategyType.LASER_DESTRUCTION.getCode(), laser,
                    buildParams("mode", "track_and_destroy")));
            available.remove(laser);
        } else {
            // 激光不可用时退化为GNSS欺骗
            Device spoofer = findDevice(available, DeviceType.GNSS_SPOOFER);
            plan.setSecondary(buildAction(StrategyType.GNSS_SPOOFING.getCode(), spoofer,
                    buildParams("mode", "push_off")));
            if (spoofer != null) {
                available.remove(spoofer);
            }
        }

        plan.setPriority(10);
        plan.setEscalationCondition("目标持续接近且无响应，升级至动能拦截");

        if (jammer != null) {
            available.remove(jammer);
        }

        log.info("目标[{}]分配CRITICAL级响应: 全频段干扰{}激光",
                target.getTargetId(), laser != null ? "+激光摧毁, " : "(无可用激光), ");
        return plan;
    }

    /**
     * VERY_HIGH等级响应：激进响应 - 射频干扰 + GNSS欺骗
     * <p>
     * 适用于高威胁目标（快速抵近、可疑意图）。
     * 使用定向射频干扰和GNSS推送偏移。
     * 禁止使用激光和动能武器（威胁等级不足）。
     * </p>
     */
    private TargetDecision.ActionPlan buildAggressiveResponse(Target target, List<Device> available,
                                                              LatLonAlt defenseCenter) {
        TargetDecision.ActionPlan plan = new TargetDecision.ActionPlan();
        Device jammer = findDevice(available, DeviceType.RF_JAMMER);
        Device spoofer = findDevice(available, DeviceType.GNSS_SPOOFER);

        plan.setPrimary(buildAction(StrategyType.RF_JAMMING.getCode(), jammer,
                buildParams("mode", "targeted", "bands", buildList("2.4GHz", "5.8GHz"))));

        plan.setSecondary(buildAction(StrategyType.GNSS_SPOOFING.getCode(), spoofer,
                buildParams("mode", "push_off")));

        plan.setPriority(8);
        plan.setEscalationCondition("干扰无效或目标切换控制模式，升级至激光摧毁");

        // 禁止使用的策略（威胁等级不足或风险过高）
        List<TargetDecision.Action> avoidList = new ArrayList<>();
        avoidList.add(buildAction(StrategyType.LASER_DESTRUCTION.getCode(), null,
                buildParams("reason", "威胁等级不足，且激光可能造成附带损伤")));
        avoidList.add(buildAction(StrategyType.KINETIC_INTERCEPT.getCode(), null,
                buildParams("reason", "威胁等级不足，动能拦截成本过高")));
        plan.setAvoid(avoidList);

        if (jammer != null) {
            available.remove(jammer);
        }
        if (spoofer != null) {
            available.remove(spoofer);
        }

        log.info("目标[{}]分配VERY_HIGH级响应: 定向射频干扰+GNSS推送偏移", target.getTargetId());
        return plan;
    }

    /**
     * HIGH等级响应：平衡响应 - 单频段射频干扰 + GNSS缓偏移
     * <p>
     * 适用于中等威胁目标。使用针对性单频段干扰（根据目标射频特征选择频段），
     * GNSS欺骗使用渐进偏移模式以降低被目标检测的风险。
     * 禁止使用致命性武器。
     * </p>
     */
    private TargetDecision.ActionPlan buildBalancedResponse(Target target, List<Device> available,
                                                            LatLonAlt defenseCenter) {
        TargetDecision.ActionPlan plan = new TargetDecision.ActionPlan();
        Device jammer = findDevice(available, DeviceType.RF_JAMMER);
        Device spoofer = findDevice(available, DeviceType.GNSS_SPOOFER);

        // 根据目标射频特征确定干扰频段
        String targetBand = "2.4GHz";
        if (target.getRfSignature() != null) {
            targetBand = determineBand(target.getRfSignature().getFrequencyHz());
        }

        plan.setPrimary(buildAction(StrategyType.RF_JAMMING.getCode(), jammer,
                buildParams("mode", "single_band", "band", targetBand)));

        if (spoofer != null) {
            plan.setSecondary(buildAction(StrategyType.GNSS_SPOOFING.getCode(), spoofer,
                    buildParams("mode", "gradual_offset")));
            available.remove(spoofer);
        }

        plan.setPriority(5);
        plan.setEscalationCondition("目标持续接近防御区域核心，且单频段干扰无效");

        // 禁止使用致命武器
        List<TargetDecision.Action> avoidList = new ArrayList<>();
        avoidList.add(buildAction(StrategyType.LASER_DESTRUCTION.getCode(), null,
                buildParams("reason", "威胁等级不满足致命武器使用条件")));
        avoidList.add(buildAction(StrategyType.KINETIC_INTERCEPT.getCode(), null,
                buildParams("reason", "威胁等级不满足动能拦截使用条件")));
        plan.setAvoid(avoidList);

        if (jammer != null) {
            available.remove(jammer);
        }

        log.info("目标[{}]分配HIGH级响应: 单频段({})射频干扰", target.getTargetId(), targetBand);
        return plan;
    }

    /**
     * MEDIUM等级响应：谨慎响应 - 声光警告 + 增强跟踪
     * <p>
     * 适用于低威胁目标，以威慑和监视为主，不使用主动对抗手段。
     * 避免不必要的设备消耗和电磁环境干扰。
     * </p>
     */
    private TargetDecision.ActionPlan buildCautiousResponse(Target target, List<Device> available,
                                                            LatLonAlt defenseCenter) {
        TargetDecision.ActionPlan plan = new TargetDecision.ActionPlan();

        plan.setPrimary(buildAction(StrategyType.WARN.getCode(), null,
                buildParams("mode", "audio_visual_warning")));
        plan.setSecondary(buildAction(StrategyType.MONITOR.getCode(), null,
                buildParams("mode", "enhanced_tracking")));

        plan.setPriority(3);
        plan.setEscalationCondition("目标无视警告继续接近，且距离小于警戒阈值");

        // 此时不应使用任何主动对抗手段
        List<TargetDecision.Action> avoidList = new ArrayList<>();
        avoidList.add(buildAction(StrategyType.RF_JAMMING.getCode(), null,
                buildParams("reason", "威胁等级不足，优先非对抗手段")));
        avoidList.add(buildAction(StrategyType.GNSS_SPOOFING.getCode(), null,
                buildParams("reason", "威胁等级不足，优先非对抗手段")));
        avoidList.add(buildAction(StrategyType.LASER_DESTRUCTION.getCode(), null,
                buildParams("reason", "威胁等级不足")));
        avoidList.add(buildAction(StrategyType.KINETIC_INTERCEPT.getCode(), null,
                buildParams("reason", "威胁等级不足")));
        plan.setAvoid(avoidList);

        log.info("目标[{}]分配MEDIUM级响应: 声光警告+增强跟踪", target.getTargetId());
        return plan;
    }

    /**
     * LOW等级响应：保守响应 - 标准跟踪 + 无主动对抗
     * <p>
     * 适用于极低威胁目标（如远处经过的消费级无人机）。
     * 仅进行标准跟踪监视，不做任何主动对抗。
     * </p>
     */
    private TargetDecision.ActionPlan buildConservativeResponse(Target target, List<Device> available,
                                                                LatLonAlt defenseCenter) {
        TargetDecision.ActionPlan plan = new TargetDecision.ActionPlan();

        plan.setPrimary(buildAction(StrategyType.MONITOR.getCode(), null,
                buildParams("mode", "standard_tracking")));
        plan.setSecondary(buildAction(StrategyType.NONE.getCode(), null, null));

        plan.setPriority(1);
        plan.setEscalationCondition("目标改变航向直指防御区域，或出现威胁行为标签");

        log.debug("目标[{}]分配LOW级响应: 标准跟踪", target.getTargetId());
        return plan;
    }

    // ======================== ROE约束处理 ========================

    /**
     * 应用交战规则(ROE)约束
     * <p>
     * ROE规则检查包括：
     * </p>
     * <ol>
     *   <li>民用区域上空禁止使用致命性武器（激光、动能拦截、HPM）</li>
     *   <li>民用区域高威胁目标需人工审核</li>
     *   <li>设备状态检查：已分配设备必须在线</li>
     * </ol>
     *
     * @param plan               原始行动计划
     * @param target             目标对象
     * @param isOverCivilianArea 是否位于民用区域上空
     * @return 应用约束后的行动计划
     */
    private TargetDecision.ActionPlan applyROEConstraints(TargetDecision.ActionPlan plan, Target target,
                                                          boolean isOverCivilianArea) {
        if (!isOverCivilianArea) {
            return plan;
        }

        // 民用区域上空：禁止使用致命性武器
        if (plan.getPrimary() != null) {
            String primaryType = plan.getPrimary().getActionType();
            if (primaryType != null && (primaryType.contains("LASER")
                    || primaryType.contains("KINETIC")
                    || primaryType.contains("HPM"))) {
                log.warn("ROE约束触发: 目标[{}]位于民用区域上空，阻止使用致命武器: {}",
                        target.getTargetId(), primaryType);

                // 降级为射频干扰
                plan.getPrimary().setActionType(StrategyType.RF_JAMMING.getCode());
                plan.getPrimary().setDeviceType(DeviceType.RF_JAMMER.getCode());

                String existingReasoning = plan.getReasoning() != null ? plan.getReasoning() : "";
                plan.setReasoning(existingReasoning + "；因民用区域上空限制，致命武器已降级为非致命手段");
            }
        }

        // 同样检查辅助策略
        if (plan.getSecondary() != null) {
            String secondaryType = plan.getSecondary().getActionType();
            if (secondaryType != null && (secondaryType.contains("LASER")
                    || secondaryType.contains("KINETIC")
                    || secondaryType.contains("HPM"))) {
                log.warn("ROE约束触发: 目标[{}]辅助策略{}位于民用区域上空，已移除",
                        target.getTargetId(), secondaryType);
                plan.setSecondary(buildAction(StrategyType.GNSS_SPOOFING.getCode(), null,
                        buildParams("mode", "gradual_offset", "reason", "ROE约束替代")));
            }
        }

        // 民用区域高威胁目标（等级>=4）需要人工审核
        if (target.getThreatLevel() != null && target.getThreatLevel().getLevel() >= 4) {
            plan.setNeedsHumanReview(true);
            log.info("ROE: 民用区域高威胁目标[{}]标记为需要人工审核", target.getTargetId());
        }

        return plan;
    }

    // ======================== 辅助方法 ========================

    /**
     * 根据威胁等级确定策略执行时机
     *
     * @param level 威胁等级
     * @return 执行时机描述字符串
     */
    private String determineTiming(ThreatLevel level) {
        if (level == null) {
            return "MONITOR";
        }
        switch (level) {
            case CRITICAL:
                return "IMMEDIATE";
            case VERY_HIGH:
                return "WITHIN_30S";
            case HIGH:
                return "WITHIN_60S";
            case MEDIUM:
                return "WITHIN_5MIN";
            case LOW:
            default:
                return "MONITOR";
        }
    }

    /**
     * 从设备列表中查找指定类型的在线设备
     *
     * @param devices 设备列表
     * @param type    需要的设备类型
     * @return 找到的第一个匹配设备，未找到返回null
     */
    private Device findDevice(List<Device> devices, DeviceType type) {
        if (devices == null || type == null) {
            return null;
        }
        return devices.stream()
                .filter(d -> d.getType() == type && d.getStatus() == DeviceStatus.ONLINE)
                .findFirst()
                .orElse(null);
    }

    /**
     * 构建行动对象
     *
     * @param actionType 策略类型代码
     * @param device     分配的设备（可为null）
     * @param params     策略参数Map（可为null）
     * @return 行动对象
     */
    private TargetDecision.Action buildAction(String actionType, Device device,
                                              Map<String, Object> params) {
        TargetDecision.Action action = new TargetDecision.Action();
        action.setActionType(actionType);
        if (device != null) {
            action.setDeviceId(device.getDeviceId());
            action.setDeviceType(device.getType().getCode());
        }
        if (params != null) {
            action.setParams(new LinkedHashMap<>(params));
        } else {
            action.setParams(new LinkedHashMap<>());
        }
        return action;
    }

    /**
     * 根据频率值确定对应的频段名称
     *
     * @param freqHz 频率值（Hz）
     * @return 频段名称字符串
     */
    private String determineBand(double freqHz) {
        if (freqHz >= 2.4e9 && freqHz <= 2.5e9) {
            return "2.4GHz";
        }
        if (freqHz >= 5.7e9 && freqHz <= 5.9e9) {
            return "5.8GHz";
        }
        if (freqHz >= 900e6 && freqHz <= 930e6) {
            return "900MHz";
        }
        if (freqHz >= 1.5e9 && freqHz <= 1.6e9) {
            return "1.5GHz";
        }
        if (freqHz >= 1.2e9 && freqHz <= 1.3e9) {
            return "1.2GHz";
        }
        if (freqHz >= 433e6 && freqHz <= 435e6) {
            return "433MHz";
        }
        // 默认使用2.4GHz（消费级无人机最常用频段）
        return "2.4GHz";
    }

    /**
     * 便捷方法：构建参数Map
     *
     * @param keysAndValues 键值对（偶数个参数，交替key1, value1, key2, value2, ...）
     * @return 参数Map
     */
    private Map<String, Object> buildParams(Object... keysAndValues) {
        Map<String, Object> params = new LinkedHashMap<>();
        if (keysAndValues != null) {
            for (int i = 0; i < keysAndValues.length - 1; i += 2) {
                params.put(String.valueOf(keysAndValues[i]), keysAndValues[i + 1]);
            }
        }
        return params;
    }

    /**
     * 便捷方法：构建字符串列表
     *
     * @param values 字符串值
     * @return 字符串列表
     */
    private List<String> buildList(String... values) {
        List<String> list = new ArrayList<>();
        if (values != null) {
            for (String v : values) {
                list.add(v);
            }
        }
        return list;
    }
}
