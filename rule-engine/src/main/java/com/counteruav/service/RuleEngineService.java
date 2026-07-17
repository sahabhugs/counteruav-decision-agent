package com.counteruav.service;


import com.counteruav.model.*;
import com.counteruav.model.Target.DroneCategory;
import org.kie.api.KieServices;
import org.kie.api.runtime.KieContainer;
import org.kie.api.runtime.KieSession;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import javax.annotation.PostConstruct;
import java.time.LocalDateTime;
import java.util.*;
import java.util.stream.Collectors;

/**
 * 规则引擎核心服务
 * 负责协调完整的决策流水线: 数据预处理 - 规则匹配 - 威胁评估 - 策略匹配 - 置信度门控 - LLM增强
 */
@Service
public class RuleEngineService {

    private static final Logger log = LoggerFactory.getLogger(RuleEngineService.class);

    @Autowired
    private KieContainer kieContainer;  
    // Drools规则容器，加载所有DRL规则文件

    @Autowired
    private ThreatEvaluator threatEvaluator;
    // 威胁评估服务，负责根据Drools规则和IFN-TOPSIS模型评估目标威胁等级

    @Autowired
    private StrategyMatcher strategyMatcher;
    // 策略匹配服务，负责根据Drools规则匹配对抗策略

    @Autowired
    private ConfidenceGate confidenceGate;
    // 置信度门控服务，负责根据Drools规则判断目标置信度是否需要上报LLM

    @Autowired
    private LLMClientService llmClientService;
    // LLM客户端服务，负责与LLM模型交互，获取目标信息

    @Autowired
    private DecisionLogService decisionLogService;
    // 决策日志服务，负责记录决策过程中的关键事件和结果

    @Value("${counteruav.llm.agent-url:http://localhost:8001}")
    private String llmAgentUrl;
    // LLM模型代理URL，用于与LLM模型交互

    /**
     * 处理决策请求 - 完整的7步决策流水线
     *
     * 步骤:
     * 1. 验证请求数据
     * 2. 创建Drools KieSession并插入事实
     * 3. 按议程组顺序执行规则: threat-classification - threat-escalation - roe - strategy-match
     * 4. 执行IFN-TOPSIS威胁评估
     * 5. 匹配对抗策略
     * 6. 信心度门控，低置信度目标上报LLM
     * 7. 组装响应并记录日志
     */
    public DecisionResponse assessThreats(DecisionRequest request) {
        long startTime = System.currentTimeMillis();
        log.info("开始处理决策请求: requestId={}, 目标数量={}, 可用设备={}",
            request.getRequestId(),
            request.getTargets() != null ? request.getTargets().size() : 0,
            request.getAvailableDevices() != null ? request.getAvailableDevices().size() : 0);

        // 步骤1: 验证请求
        validateRequest(request);

        // 步骤2-3: 运行Drools规则引擎
        List<Target> processedTargets = runDroolsRules(request);

        // 步骤4: IFN-TOPSIS威胁评估
        LatLonAlt defenseCenter = request.getDefenseCenter();
        Map<String, ThreatEvaluator.ThreatScores> threatScores = threatEvaluator.evaluate(processedTargets, defenseCenter);

        // 更新目标的威胁等级和分数（Drools规则结果优先，TOPSIS作为补充）
        for (Target target : processedTargets) {
            ThreatEvaluator.ThreatScores scores = threatScores.get(target.getTargetId());
            if (scores != null) {
                // 仅当Drools规则未设置威胁等级时，使用TOPSIS结果
                if (target.getThreatLevel() == null) {
                    target.setThreatLevel(scores.getThreatLevel());
                    target.setThreatScore(scores.getThreatScore());
                    log.debug("目标[{}]未被Drools规则定级，采用TOPSIS评估结果: 等级={}, 分数={}",
                        target.getTargetId(),
                        scores.getThreatLevel().getLabel(),
                        String.format("%.2f", scores.getThreatScore()));
                } else {
                    // Drools已定级：等级以规则为准，但补全缺失的威胁分数
                    if (target.getThreatScore() <= 0.0) {
                        target.setThreatScore(scores.getThreatScore());
                    }
                    log.debug("目标[{}]已被Drools规则定级为[{}]，保留规则结果，TOPSIS参考等级={}, 参考分数={}",
                        target.getTargetId(),
                        target.getThreatLevel().getLabel(),
                        scores.getThreatLevel().getLabel(),
                        String.format("%.2f", scores.getThreatScore()));
                }

                // 保留TOPSIS详细指标得分作为补充信息（通过日志记录，便于回溯分析）
                log.debug("目标[{}] TOPSIS详细指标: 贴近度系数={}, 分项得分={}",
                    target.getTargetId(),
                    String.format("%.3f", scores.getClosenessCoefficient()),
                    scores.getIndicatorScores());
            }
        }

        // 步骤5: 策略匹配
        boolean isOverCivilianArea = processedTargets.stream().anyMatch(Target::isOverCivilianArea);
        Map<String, TargetDecision.ActionPlan> plans = strategyMatcher.matchStrategies(
            processedTargets, threatScores, request.getAvailableDevices(), defenseCenter, isOverCivilianArea);

        // 步骤6: 置信度门控 + LLM增强
        List<TargetDecision> decisions = new ArrayList<>();
        for (Target target : processedTargets) {
            TargetDecision decision = buildTargetDecision(target, threatScores, plans);

            // 计算置信度
            Map<String, Double> sensorStatus = extractSensorStatus(request, target);
            double historicalAccuracy = decisionLogService.getHistoricalAccuracy(determineTargetProfile(target));
            double confidence = confidenceGate.calculateConfidence(
                target, target.getMatchedRules(), sensorStatus, historicalAccuracy);

            // 检查是否需要LLM
            if (confidenceGate.shouldEscalateToLLM(target, confidence)) {
                List<String> triggers = confidenceGate.getTriggerReasons(target, confidence);
                log.info("目标[{}]置信度{}低于阈值，触发LLM增强: {}",
                    target.getTargetId(), String.format("%.2f", confidence), triggers);

                LLMClientService.LLMDecisionResponse llmResponse = llmClientService.sendToLLMAgent(
                    request, target.getTargetId(), triggers);

                if (llmResponse != null && "FALLBACK_RULE_ENGINE".equals(llmResponse.getSource())) {
                    // LLM不可用，使用规则引擎回退
                    decision.getThreatAssessment().setConfidence(confidence);
                    decision.setRuleProposal(null);
                    decision.getUncertaintyFlags().add("LLM_UNAVAILABLE: " + llmResponse.getFallbackReason());
                } else if (llmResponse != null) {
                    // 使用LLM增强结果
                    decision.getThreatAssessment().setConfidence(
                        Math.max(confidence, llmResponse.getConfidence()));
                    decision.setRuleProposal(buildRuleProposalFromLLM(llmResponse));
                    decision.getUncertaintyFlags().addAll(triggers);
                }
            } else {
                decision.getThreatAssessment().setConfidence(confidence);
            }

            decisions.add(decision);
        }

        // 步骤7: 组装响应
        DecisionResponse response = new DecisionResponse();
        response.setRequestId(request.getRequestId());
        response.setDecisionId(UUID.randomUUID().toString());
        response.setTimestamp(LocalDateTime.now());
        response.setSource("RULE_ENGINE");
        response.setProcessingTimeMs(System.currentTimeMillis() - startTime);
        response.setDecisions(decisions);

        // 记录决策日志
        decisionLogService.saveDecisionLog(response);

        log.info("决策请求处理完成: requestId={}, decisionId={}, 耗时={}ms",
            request.getRequestId(), response.getDecisionId(), response.getProcessingTimeMs());

        return response;
    }

    /**
     * 运行Drools规则引擎
     * 按议程组顺序执行
     */
    private List<Target> runDroolsRules(DecisionRequest request) {
        List<Target> targets = new ArrayList<>(request.getTargets());

        KieSession kieSession = null;
        try {
            // 获取有状态会话（支持规则间状态传递）
            kieSession = kieContainer.newKieSession("L2StatefulSession");
            if (kieSession == null) {
                log.warn("无法获取KieSession，跳过规则引擎，直接进行威胁评估");
                return targets;   // 降级处理：跳过规则，直接用TOPSIS评估
            }

            // 插入所有事实（规则匹配的数据源）
            for (Target target : targets) {
                kieSession.insert(target);
            }
            // 插入设备和环境信息
            kieSession.insert(request);
            if (request.getAvailableDevices() != null) {
                request.getAvailableDevices().forEach(kieSession::insert);
            }

            // 按议程组顺序执行规则（关键：确保规则执行顺序）
            /*
             * 1. threat-classification:威胁分类,判断无人机类型、意图识别
             * 2. threat-escalation:威胁升级, 根据行为模式提升威胁等级
             * 3. roe:ROE匹配, 根据ROE判断是否需要升级
             * 4. strategy-match:策略匹配, 根据ROE和威胁等级匹配策略
             */
            // 数组和规则文件中的 agenda-group 属性是 一一对应的
            String[] agendaGroups = {"threat-classification", "threat-escalation", "roe", "strategy-match"};
            for (String group : agendaGroups) {
                kieSession.getAgenda().getAgendaGroup(group).setFocus();
                int fired = kieSession.fireAllRules();
                log.debug("议程组[{}]: 触发{}条规则", group, fired);
            }

            // 收集匹配的规则
            // 注意: 在实际实现中，匹配的规则会通过全局变量或监听器收集
            // 当前设计中，matchedRules由Drools规则自身在Target对象上设置

        } catch (Exception e) {
            log.error("规则引擎执行异常: {}", e.getMessage(), e);
        } finally {  // 资源管理 ： finally 块确保会话正确释放
            if (kieSession != null) {
                kieSession.dispose();
            }
        }

        return targets;
    }

    private TargetDecision buildTargetDecision(Target target,
            Map<String, ThreatEvaluator.ThreatScores> threatScores,
            Map<String, TargetDecision.ActionPlan> plans) {

        TargetDecision decision = new TargetDecision();
        decision.setTargetId(target.getTargetId());
        decision.setNeedsHumanReview(false);
        decision.setUncertaintyFlags(new ArrayList<>());

        // 威胁评估
        ThreatEvaluator.ThreatScores scores = threatScores.get(target.getTargetId());
        TargetDecision.ThreatAssessment assessment = new TargetDecision.ThreatAssessment();
        if (scores != null) {
            assessment.setLevel(scores.getThreatLevel().getLevel());
            assessment.setLabel(scores.getThreatLevel().getLabel());
            assessment.setScore(scores.getThreatScore());
            assessment.setIndicatorScores(scores.getIndicatorScores());
            assessment.setReasoning(buildThreatReasoning(target, scores));
        }
        assessment.setMatchedRules(target.getMatchedRules() != null ? target.getMatchedRules() : new ArrayList<>());
        decision.setThreatAssessment(assessment);

        // 行动计划
        TargetDecision.ActionPlan plan = plans.get(target.getTargetId());
        if (plan != null) {
            decision.setRecommendedAction(plan);
            // 传播ROE约束中标记的人工审核需求
            if (plan.isNeedsHumanReview()) {
                decision.setNeedsHumanReview(true);
                if (decision.getReviewReason() == null || decision.getReviewReason().isEmpty()) {
                    decision.setReviewReason("ROE约束: 民用区域高威胁目标需人工审核");
                }
            }
        }

        // 人工审核标记
        if (target.getThreatLevel() != null && target.getThreatLevel().getLevel() >= 4 && target.isOverCivilianArea()) {
            decision.setNeedsHumanReview(true);
            decision.setReviewReason("高威胁目标位于民用区域上空，需指挥官审核");
        }
        if (target.getDroneCategory() == DroneCategory.UNKNOWN && target.getThreatLevel() != null && target.getThreatLevel().getLevel() >= 3) {
            decision.setNeedsHumanReview(true);
            decision.setReviewReason("未知机型高威胁目标");
        }

        return decision;
    }

    private String buildThreatReasoning(Target target, ThreatEvaluator.ThreatScores scores) {
        StringBuilder sb = new StringBuilder();
        sb.append("IFN-TOPSIS评估完成，贴近度系数=").append(String.format("%.3f", scores.getClosenessCoefficient()));
        sb.append("，威胁等级=").append(scores.getThreatLevel().getLabel());
        if (target.getEscalationReason() != null && !target.getEscalationReason().isEmpty()) {
            sb.append("，升级原因: ").append(target.getEscalationReason());
        }
        return sb.toString();
    }

    private Map<String, Double> extractSensorStatus(DecisionRequest request, Target target) {
        Map<String, Double> status = new LinkedHashMap<>();
        if (target.getRfSignature() != null) {
            status.put("rf_sensor", target.getRfSignature().getSnrDb());
        }
        // 可在此处添加其他传感器状态提取逻辑
        return status;
    }

    private String determineTargetProfile(Target target) {
        return target.getDroneCategory() != null ? target.getDroneCategory().getCode() : "UNKNOWN";
    }

    private TargetDecision.RuleProposal buildRuleProposalFromLLM(LLMClientService.LLMDecisionResponse llmResponse) {
        TargetDecision.RuleProposal proposal = new TargetDecision.RuleProposal();
        proposal.setProposed(true);
        proposal.setSource("LLM_AGENT");
        proposal.setConfidence(llmResponse.getConfidence());
        proposal.setReasoning(llmResponse.getReasoning());
        return proposal;
    }

    private void validateRequest(DecisionRequest request) {
        // 验证请求数据:
        // - 目标列表和防御中心是 必需字段 ，缺失时抛出异常
        // - 请求ID缺失时 自动补全 ，避免空指针问题
        if (request.getTargets() == null || request.getTargets().isEmpty()) {
            throw new IllegalArgumentException("决策请求必须包含至少一个目标");
        }
        if (request.getDefenseCenter() == null) {
            throw new IllegalArgumentException("决策请求必须包含防御中心位置");
        }
        if (request.getRequestId() == null || request.getRequestId().isEmpty()) {
            request.setRequestId(UUID.randomUUID().toString());
            // 为新请求生成随机ID
        }
    }

    @PostConstruct
    public void init() {
        log.info("规则引擎服务初始化完成");
        log.info("LLM Agent URL: {}", llmAgentUrl);
    }
}
