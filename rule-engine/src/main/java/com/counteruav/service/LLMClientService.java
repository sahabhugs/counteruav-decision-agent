package com.counteruav.service;

import com.counteruav.model.DecisionRequest;
import com.counteruav.model.ThreatLevel;
import com.counteruav.util.LLMCallRateLimiter;
import lombok.Data;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Service;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.HttpServerErrorException;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestTemplate;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * LLM Agent HTTP客户端服务
 * <p>
 * 负责与Python LLM Agent（大语言模型智能体）的HTTP通信，
 * 提供辅助决策请求的发送、回退处理和健康检查功能。
 * </p>
 *
 * <h3>核心机制</h3>
 * <ul>
 *   <li><b>熔断器(Circuit Breaker)</b>：连续失败3次后熔断60秒，保护LLM服务</li>
 *   <li><b>速率限制(Rate Limiting)</b>：通过 {@link LLMCallRateLimiter} 控制每分钟调用次数</li>
 *   <li><b>回退策略(Fallback)</b>：LLM不可用时返回规则引擎决策作为回退方案</li>
 *   <li><b>超时处理</b>：通过RestTemplate配置的连接和读取超时</li>
 * </ul>
 *
 * <h3>熔断器状态转换</h3>
 * <pre>
 * CLOSED ──(连续失败≥3次)──> OPEN ──(60秒后)──> HALF-OPEN
 *                                                    │
 *                                              (成功/失败)
 *                                           ┌──────┴──────┐
 *                                        CLOSED          OPEN
 * </pre>
 *
 * @author counteruav
 * @since 1.0.0
 */
@Slf4j
@Service
public class LLMClientService {

    @Autowired
    private RestTemplate restTemplate;

    @Autowired
    private LLMCallRateLimiter rateLimiter;

    /** LLM Agent服务URL */
    @Value("${counteruav.llm.agent-url:http://localhost:8001}")
    private String llmAgentUrl;

    /** 熔断器：连续失败计数 */
    private volatile int consecutiveFailures = 0;

    /** 熔断器：恢复时间戳（毫秒），0表示未熔断 */
    private volatile long circuitOpenUntil = 0;

    /** 熔断触发阈值：连续失败次数 */
    private static final int MAX_CONSECUTIVE_FAILURES = 3;

    /** 熔断恢复时间：60秒 */
    private static final long CIRCUIT_RESET_MS = 60_000;

    /** LLM决策API路径 */
    private static final String DECIDE_API_PATH = "/api/llm/decide";

    /** LLM健康检查API路径 */
    private static final String HEALTH_API_PATH = "/api/llm/health";

    /**
     * 发送决策请求到LLM Agent进行辅助决策
     * <p>
     * 执行流程：
     * </p>
     * <ol>
     *   <li>检查熔断器状态，熔断中直接返回回退响应</li>
     *   <li>检查速率限制，超限直接返回回退响应</li>
     *   <li>构建HTTP请求并发送到LLM Agent</li>
     *   <li>成功则重置熔断器计数器</li>
     *   <li>失败则记录失败并返回回退响应</li>
     * </ol>
     *
     * @param request        原始决策请求
     * @param targetId       目标ID
     * @param triggerReasons 触发LLM上报的原因列表
     * @return LLM决策响应（成功时来自LLM，失败时来自回退方案）
     */
    public LLMDecisionResponse sendToLLMAgent(DecisionRequest request, String targetId,
                                              List<String> triggerReasons) {
        // 1. 检查熔断器
        if (isCircuitOpen()) {
            long remainingSec = (circuitOpenUntil - System.currentTimeMillis()) / 1000;
            log.warn("LLM熔断器开启（剩余{}秒），跳过LLM调用，使用规则引擎回退决策", remainingSec);
            return buildFallbackResponse(targetId, "LLM服务熔断保护（剩余" + remainingSec + "秒恢复）");
        }

        // 2. 检查速率限制
        if (!rateLimiter.tryAcquire(targetId)) {
            log.warn("LLM调用被限流拒绝，目标: {}", targetId);
            return buildFallbackResponse(targetId, "LLM调用速率限制（超过每分钟调用上限）");
        }

        // 3. 发送请求
        try {
            String url = llmAgentUrl + DECIDE_API_PATH;

            // 构建符合Python DecideRequest Pydantic模型的请求载荷
            Map<String, Object> situation = new LinkedHashMap<>();
            situation.put("task_id", request.getRequestId());
            situation.put("target_id", targetId);
            situation.put("targets", request.getTargets());
            situation.put("devices", request.getAvailableDevices());
            situation.put("environment", request.getEnvironment());

            Map<String, Object> payload = new LinkedHashMap<>();
            payload.put("task_id", request.getRequestId());
            payload.put("trigger_reason", triggerReasons != null && !triggerReasons.isEmpty()
                    ? triggerReasons.get(0) : "low_confidence");
            payload.put("trigger_detail", triggerReasons != null
                    ? String.join("; ", triggerReasons) : "");
            payload.put("situation", situation);
            payload.put("task_description",
                    "对目标 " + targetId + " 进行深度威胁评估并推荐反制策略。触发原因: "
                    + (triggerReasons != null ? String.join(", ", triggerReasons) : "置信度不足"));

            // 设置HTTP头
            HttpHeaders headers = new HttpHeaders();
            headers.setContentType(MediaType.APPLICATION_JSON);
            HttpEntity<Map<String, Object>> entity = new HttpEntity<>(payload, headers);

            log.info("发送LLM决策请求: targetId={}, 触发原因={}, 载荷大小={}bytes",
                    targetId, triggerReasons != null ? triggerReasons.size() : 0,
                    estimatePayloadSize(payload));

            long start = System.currentTimeMillis();

            ResponseEntity<Map> response = restTemplate.exchange(
                    url, HttpMethod.POST, entity, Map.class);

            long elapsed = System.currentTimeMillis() - start;
            log.info("LLM响应成功: targetId={}, 耗时={}ms, 状态码={}",
                    targetId, elapsed, response.getStatusCodeValue());

            // 成功：重置熔断器
            resetCircuitBreaker();

            Map<String, Object> body = response.getBody();
            if (body != null) {
                return parseLLMResponse(body, targetId);
            }

            // 响应体为空
            return buildFallbackResponse(targetId, "LLM返回空响应");

        } catch (HttpClientErrorException e) {
            // 4xx客户端错误
            log.error("LLM HTTP客户端错误: targetId={}, status={}, message={}",
                    targetId, e.getStatusCode(), e.getResponseBodyAsString());
            recordFailure();
            return buildFallbackResponse(targetId,
                    "LLM客户端错误: HTTP " + e.getStatusCode().value());

        } catch (HttpServerErrorException e) {
            // 5xx服务端错误
            log.error("LLM HTTP服务端错误: targetId={}, status={}, message={}",
                    targetId, e.getStatusCode(), e.getResponseBodyAsString());
            recordFailure();
            return buildFallbackResponse(targetId,
                    "LLM服务端错误: HTTP " + e.getStatusCode().value());

        } catch (ResourceAccessException e) {
            // 连接超时或拒绝
            log.error("LLM连接异常: targetId={}, message={}", targetId, e.getMessage());
            recordFailure();
            return buildFallbackResponse(targetId,
                    "LLM连接异常: " + extractShortMessage(e.getMessage()));

        } catch (Exception e) {
            // 其他未预期异常
            log.error("LLM调用未知异常: targetId={}", targetId, e);
            recordFailure();
            return buildFallbackResponse(targetId,
                    "LLM调用异常: " + extractShortMessage(e.getMessage()));
        }
    }

    /**
     * 检查LLM Agent健康状态
     * <p>
     * 执行HTTP GET请求到LLM Agent的健康检查端点。
     * 熔断器开启时直接返回false。
     * </p>
     *
     * @return true表示LLM服务健康可用，false表示不可用
     */
    public boolean isLLMHealthy() {
        if (isCircuitOpen()) {
            return false;
        }

        try {
            String url = llmAgentUrl + HEALTH_API_PATH;
            ResponseEntity<Map> response = restTemplate.getForEntity(url, Map.class);
            boolean healthy = response.getStatusCode().is2xxSuccessful();
            if (healthy) {
                log.debug("LLM健康检查通过: {}", url);
            } else {
                log.warn("LLM健康检查失败: status={}", response.getStatusCodeValue());
            }
            return healthy;
        } catch (Exception e) {
            log.warn("LLM健康检查异常: {}", e.getMessage());
            return false;
        }
    }

    /**
     * 获取当前熔断器状态
     *
     * @return 熔断器状态描述
     */
    public String getCircuitBreakerStatus() {
        if (isCircuitOpen()) {
            long remaining = (circuitOpenUntil - System.currentTimeMillis()) / 1000;
            return "OPEN (剩余" + Math.max(0, remaining) + "秒)";
        }
        return "CLOSED (连续失败: " + consecutiveFailures + "/" + MAX_CONSECUTIVE_FAILURES + ")";
    }

    /**
     * 手动重置熔断器
     */
    public void manualResetCircuit() {
        consecutiveFailures = 0;
        circuitOpenUntil = 0;
        log.info("手动重置LLM熔断器");
    }

    // ======================== 熔断器实现 ========================

    /**
     * 检查熔断器是否处于开路状态
     * <p>
     * 熔断器开路条件：
     * </p>
     * <ol>
     *   <li>连续失败次数达到阈值</li>
     *   <li>恢复时间尚未到达</li>
     * </ol>
     * <p>
     * 当恢复时间到达后，熔断器进入半开状态（允许尝试），
     * 此时连续失败计数清零。
     * </p>
     *
     * @return true表示熔断器开路（拒绝所有调用）
     */
    private boolean isCircuitOpen() {
        if (consecutiveFailures >= MAX_CONSECUTIVE_FAILURES) {
            if (System.currentTimeMillis() < circuitOpenUntil) {
                return true; // 仍在熔断期内
            }
            // 熔断期已过，进入半开状态
            consecutiveFailures = 0;
            log.info("LLM熔断器进入半开状态，允许尝试调用");
        }
        return false;
    }

    /**
     * 记录一次调用失败
     * <p>
     * 连续失败计数递增，达到阈值时触发熔断。
     * 使用synchronized保证线程安全。
     * </p>
     */
    private synchronized void recordFailure() {
        consecutiveFailures++;
        if (consecutiveFailures >= MAX_CONSECUTIVE_FAILURES) {
            circuitOpenUntil = System.currentTimeMillis() + CIRCUIT_RESET_MS;
            log.error("LLM熔断器触发! 连续失败{}次（阈值={}），熔断{}秒",
                    consecutiveFailures, MAX_CONSECUTIVE_FAILURES,
                    CIRCUIT_RESET_MS / 1000);
        }
    }

    /**
     * 重置熔断器（调用成功后调用）
     */
    private void resetCircuitBreaker() {
        consecutiveFailures = 0;
    }

    // ======================== 回退处理 ========================

    /**
     * 解析Python LLM Agent返回的DecideResponse格式
     * <p>
     * Python返回格式：{"task_id":..., "status":..., "decision":{...}, "metadata":{...}, "errors":[...]}
     * 从嵌套的decision对象中提取威胁评估和推荐动作。
     * </p>
     */
    @SuppressWarnings("unchecked")
    private LLMDecisionResponse parseLLMResponse(Map<String, Object> body, String targetId) {
        LLMDecisionResponse result = new LLMDecisionResponse();
        result.setTargetId(targetId);
        result.setSource("LLM_AGENT");

        String status = (String) body.getOrDefault("status", "error");
        Map<String, Object> decision = (Map<String, Object>) body.get("decision");

        if (decision != null) {
            // 提取威胁评估
            Map<String, Object> threatAssess = (Map<String, Object>) decision.get("threat_assessment");
            if (threatAssess != null) {
                Object level = threatAssess.get("threat_level");
                if (level instanceof Number) {
                    result.setRecommendedLevel(ThreatLevel.fromLevel(((Number) level).intValue()));
                }
                Object confidence = threatAssess.get("confidence");
                if (confidence instanceof Number) {
                    result.setConfidence(((Number) confidence).doubleValue());
                }
            }

            // 提取推荐动作
            Map<String, Object> recAction = (Map<String, Object>) decision.get("recommended_action");
            if (recAction != null) {
                result.setRecommendedAction((String) recAction.get("action_type"));
            }

            // 提取推理链
            Object reasoningChain = decision.get("reasoning_chain");
            if (reasoningChain instanceof List) {
                result.setReasoning(String.join(" → ", (List<String>) reasoningChain));
            }
        }

        // 从metadata提取耗时
        Map<String, Object> metadata = (Map<String, Object>) body.get("metadata");
        if (metadata != null && metadata.get("elapsed_seconds") instanceof Number) {
            log.info("LLM Agent推理耗时: {}s", metadata.get("elapsed_seconds"));
        }

        // status=error 时降低置信度
        if ("error".equals(status)) {
            result.setConfidence(Math.min(result.getConfidence(), 0.3));
            log.warn("LLM Agent返回error状态，置信度降为{}", result.getConfidence());
        }

        return result;
    }

    /**
     * 构建回退响应
     * <p>
     * 当LLM服务不可用时，返回规则引擎的决策作为回退方案。
     * 回退响应的source字段标记为"FALLBACK_RULE_ENGINE"。
     * </p>
     *
     * @param targetId 目标ID
     * @param reason   回退原因
     * @return 回退LLM响应
     */
    private LLMDecisionResponse buildFallbackResponse(String targetId, String reason) {
        LLMDecisionResponse response = new LLMDecisionResponse();
        response.setTargetId(targetId);
        response.setSource("FALLBACK_RULE_ENGINE");
        response.setFallbackReason(reason);
        response.setConfidence(0.0);
        log.info("构建LLM回退响应: targetId={}, reason={}", targetId, reason);
        return response;
    }

    // ======================== 工具方法 ========================

    /**
     * 估算载荷大小（用于日志记录）
     *
     * @param payload 请求载荷
     * @return 估算字节数
     */
    private int estimatePayloadSize(Map<String, Object> payload) {
        if (payload == null) {
            return 0;
        }
        // 简单估算：每个entry约100字节 + 字符串长度
        int size = 0;
        for (Map.Entry<String, Object> entry : payload.entrySet()) {
            size += 100 + (entry.getKey() != null ? entry.getKey().length() * 2 : 0);
            Object value = entry.getValue();
            if (value instanceof String) {
                size += ((String) value).length() * 2;
            } else if (value instanceof List) {
                size += ((List<?>) value).size() * 200;
            }
        }
        return size;
    }

    /**
     * 提取异常消息的简短描述（截断过长消息）
     *
     * @param message 原始消息
     * @return 截断后的消息（最多100字符）
     */
    private String extractShortMessage(String message) {
        if (message == null) {
            return "未知错误";
        }
        if (message.length() <= 100) {
            return message;
        }
        return message.substring(0, 97) + "...";
    }

    // ======================== 内部类 ========================

    /**
     * LLM Agent决策响应
     * <p>
     * 封装LLM Agent返回的辅助决策结果。当LLM不可用时，
     * source字段为"FALLBACK_RULE_ENGINE"表示使用规则引擎回退。
     * </p>
     */
    @Data
    public static class LLMDecisionResponse {

        /** 目标ID */
        private String targetId;

        /** 决策来源：LLM_AGENT 或 FALLBACK_RULE_ENGINE */
        private String source;

        /** 回退原因（仅当source=FALLBACK_RULE_ENGINE时有值） */
        private String fallbackReason;

        /** LLM推荐的威胁等级 */
        private ThreatLevel recommendedLevel;

        /** LLM推荐的对抗策略 */
        private String recommendedAction;

        /** LLM的推理过程说明 */
        private String reasoning;

        /** LLM决策的置信度 (0.0-1.0) */
        private double confidence;
    }
}
