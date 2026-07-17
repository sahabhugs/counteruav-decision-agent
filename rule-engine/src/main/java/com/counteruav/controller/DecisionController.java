package com.counteruav.controller;

import com.counteruav.model.*;
import com.counteruav.service.*;
import com.counteruav.util.LLMCallRateLimiter;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;

import javax.validation.Valid;
import java.time.LocalDateTime;
import java.util.*;

/**
 * 决策控制器
 * 提供威胁评估、反馈收集、历史查询等REST API
 */
@RestController
@RequestMapping("/api/decision")
public class DecisionController {

    private static final Logger log = LoggerFactory.getLogger(DecisionController.class);

    @Autowired
    private RuleEngineService ruleEngineService;

    @Autowired
    private DecisionLogService decisionLogService;

    @Autowired
    private LLMCallRateLimiter rateLimiter;

    @Autowired
    private LLMClientService llmClientService;

    /**
     * 威胁评估接口
     * POST /api/decision/assess
     */
    @PostMapping("/assess")
    public ResponseEntity<?> assessThreats(@Valid @RequestBody DecisionRequest request) {
        try {
            log.info("收到威胁评估请求: requestId={}", request.getRequestId());
            DecisionResponse response = ruleEngineService.assessThreats(request);
            return ResponseEntity.ok(response);
        } catch (IllegalArgumentException e) {
            log.warn("请求参数验证失败: {}", e.getMessage());
            Map<String, Object> errorBody = new LinkedHashMap<>();
            errorBody.put("error", e.getMessage());
            return ResponseEntity.badRequest().body(errorBody);
        } catch (Exception e) {
            log.error("威胁评估处理异常", e);
            Map<String, Object> errorBody = new LinkedHashMap<>();
            errorBody.put("error", "评估处理失败: " + e.getMessage());
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).body(errorBody);
        }
    }

    /**
     * 提交指挥员反馈
     * POST /api/decision/feedback
     */
    @PostMapping("/feedback")
    public ResponseEntity<?> submitFeedback(@Valid @RequestBody FeedbackRequest feedback) {
        try {
            log.info("收到指挥员反馈: decisionId={}, targetId={}, verdict={}",
                feedback.getDecisionId(), feedback.getTargetId(), feedback.getVerdict());

            if (feedback.getTimestamp() == null) {
                feedback.setTimestamp(LocalDateTime.now());
            }

            decisionLogService.saveFeedback(feedback);

            Map<String, Object> result = new LinkedHashMap<>();
            result.put("status", "OK");
            result.put("message", "反馈已成功提交");
            result.put("decisionId", feedback.getDecisionId());
            result.put("targetId", feedback.getTargetId());

            return ResponseEntity.ok(result);
        } catch (Exception e) {
            log.error("反馈提交失败", e);
            Map<String, Object> errorBody = new LinkedHashMap<>();
            errorBody.put("error", "反馈提交失败: " + e.getMessage());
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).body(errorBody);
        }
    }

    /**
     * 查询历史决策
     * GET /api/decision/history?targetId=&start=&end=
     */
    @GetMapping("/history")
    public ResponseEntity<?> getDecisionHistory(
            @RequestParam(required = false) String targetId,
            @RequestParam(required = false) String start,
            @RequestParam(required = false) String end) {
        try {
            log.info("查询历史决策: targetId={}, start={}, end={}", targetId, start, end);
            List<DecisionResponse> history = decisionLogService.getDecisionHistory(targetId, start, end);

            Map<String, Object> result = new LinkedHashMap<>();
            result.put("total", history.size());
            result.put("decisions", history);

            return ResponseEntity.ok(result);
        } catch (Exception e) {
            log.error("查询历史决策失败", e);
            Map<String, Object> errorBody = new LinkedHashMap<>();
            errorBody.put("error", "查询失败: " + e.getMessage());
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).body(errorBody);
        }
    }

    /**
     * 获取决策详情
     * GET /api/decision/{decisionId}
     */
    @GetMapping("/{decisionId}")
    public ResponseEntity<?> getDecisionDetail(@PathVariable String decisionId) {
        try {
            log.info("查询决策详情: decisionId={}", decisionId);
            DecisionResponse decision = decisionLogService.getDecisionById(decisionId);

            if (decision == null) {
                Map<String, Object> errorBody = new LinkedHashMap<>();
                errorBody.put("error", "决策记录未找到: " + decisionId);
                return ResponseEntity.status(HttpStatus.NOT_FOUND).body(errorBody);
            }

            return ResponseEntity.ok(decision);
        } catch (Exception e) {
            log.error("查询决策详情失败", e);
            Map<String, Object> errorBody = new LinkedHashMap<>();
            errorBody.put("error", "查询失败: " + e.getMessage());
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).body(errorBody);
        }
    }

    /**
     * 获取系统状态
     * GET /api/decision/status
     */
    @GetMapping("/status")
    public ResponseEntity<?> getSystemStatus() {
        try {
            Map<String, Object> status = new LinkedHashMap<>();

            // 速率限制器状态
            RateLimitStatus rateStatus = rateLimiter.getStatus();
            status.put("rateLimiter", rateStatus);

            // LLM健康状态
            boolean llmHealthy = llmClientService.isLLMHealthy();
            Map<String, Object> llmStatus = new LinkedHashMap<>();
            llmStatus.put("healthy", llmHealthy);
            llmStatus.put("status", llmHealthy ? "正常" : "不可用");
            status.put("llmAgent", llmStatus);

            // 系统信息
            status.put("timestamp", LocalDateTime.now().toString());
            status.put("mode", "RULE_ENGINE");

            return ResponseEntity.ok(status);
        } catch (Exception e) {
            log.error("获取系统状态失败", e);
            Map<String, Object> errorBody = new LinkedHashMap<>();
            errorBody.put("error", "获取状态失败: " + e.getMessage());
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).body(errorBody);
        }
    }
}
