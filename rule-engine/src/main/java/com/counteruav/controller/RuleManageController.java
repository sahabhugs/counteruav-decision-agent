package com.counteruav.controller;

import com.counteruav.model.*;
import com.counteruav.config.DroolsConfig;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.time.LocalDateTime;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;

/**
 * 规则管理控制器
 * 提供规则的查看、修改、审批、版本管理等REST API
 */
@RestController
@RequestMapping("/api/rules")
public class RuleManageController {

    private static final Logger log = LoggerFactory.getLogger(RuleManageController.class);

    @Autowired
    private DroolsConfig droolsConfig;

    // 规则版本历史存储 (内存)
    private final ConcurrentHashMap<String, List<RuleInfo>> versionHistory = new ConcurrentHashMap<>();

    // 待审批L4规则提案
    private final ConcurrentHashMap<String, TargetDecision.RuleProposal> pendingProposals = new ConcurrentHashMap<>();

    /**
     * 强制重新加载所有规则
     * POST /api/rules/reload
     */
    @PostMapping("/reload")
    public ResponseEntity<?> reloadRules() {
        try {
            log.info("开始重新加载规则...");
            droolsConfig.reloadRules();

            Map<String, Object> result = new LinkedHashMap<>();
            result.put("status", "OK");
            result.put("message", "所有规则已重新加载");
            result.put("timestamp", LocalDateTime.now().toString());

            log.info("规则重新加载完成");
            return ResponseEntity.ok(result);
        } catch (Exception e) {
            log.error("规则重新加载失败", e);
            Map<String, Object> errorBody = new LinkedHashMap<>();
            errorBody.put("error", "规则重新加载失败: " + e.getMessage());
            return ResponseEntity.internalServerError().body(errorBody);
        }
    }

    /**
     * 获取所有规则列表
     * GET /api/rules
     */
    @GetMapping
    public ResponseEntity<?> listRules() {
        try {
            List<RuleInfo> rules = loadAllRuleInfos();

            Map<String, Object> result = new LinkedHashMap<>();
            result.put("total", rules.size());
            result.put("rules", rules);

            return ResponseEntity.ok(result);
        } catch (Exception e) {
            log.error("获取规则列表失败", e);
            Map<String, Object> errorBody = new LinkedHashMap<>();
            errorBody.put("error", "获取规则列表失败: " + e.getMessage());
            return ResponseEntity.internalServerError().body(errorBody);
        }
    }

    /**
     * 获取规则详情
     * GET /api/rules/{ruleId}
     */
    @GetMapping("/{ruleId}")
    public ResponseEntity<?> getRuleDetail(@PathVariable String ruleId) {
        try {
            List<RuleInfo> allRules = loadAllRuleInfos();
            Optional<RuleInfo> rule = allRules.stream()
                .filter(r -> r.getRuleId().equals(ruleId))
                .findFirst();

            if (rule.isPresent()) {
                return ResponseEntity.ok(rule.get());
            } else {
                return ResponseEntity.notFound().build();
            }
        } catch (Exception e) {
            log.error("获取规则详情失败", e);
            Map<String, Object> errorBody = new LinkedHashMap<>();
            errorBody.put("error", "获取规则详情失败: " + e.getMessage());
            return ResponseEntity.internalServerError().body(errorBody);
        }
    }

    /**
     * 更新规则内容
     * PUT /api/rules/{ruleId}
     */
    @PutMapping("/{ruleId}")
    public ResponseEntity<?> updateRule(@PathVariable String ruleId, @RequestBody Map<String, String> body) {
        try {
            String content = body.get("content");
            if (content == null || content.isEmpty()) {
                Map<String, Object> errorBody = new LinkedHashMap<>();
                errorBody.put("error", "规则内容不能为空");
                return ResponseEntity.badRequest().body(errorBody);
            }

            // 查找规则文件
            List<RuleInfo> rules = loadAllRuleInfos();
            Optional<RuleInfo> ruleOpt = rules.stream()
                .filter(r -> r.getRuleId().equals(ruleId))
                .findFirst();

            if (!ruleOpt.isPresent()) {
                return ResponseEntity.notFound().build();
            }

            RuleInfo rule = ruleOpt.get();
            Path filePath = Paths.get("src/main/resources/rules").resolve(rule.getFilePath());

            // 备份旧版本
            if (Files.exists(filePath)) {
                String oldContent = Files.readString(filePath);
                saveVersion(ruleId, rule, oldContent);
            }

            // 写入新内容
            Files.writeString(filePath, content, StandardCharsets.UTF_8);

            // 更新版本
            String newVersion = incrementVersion(rule.getVersion());
            rule.setVersion(newVersion);
            rule.setContent(content);
            rule.setUpdateTime(LocalDateTime.now());

            // 触发规则重新加载
            droolsConfig.reloadRules();

            Map<String, Object> result = new LinkedHashMap<>();
            result.put("status", "OK");
            result.put("message", "规则已更新并重新加载");
            result.put("ruleId", ruleId);
            result.put("version", newVersion);

            log.info("规则已更新: ruleId={}, version={}", ruleId, newVersion);
            return ResponseEntity.ok(result);

        } catch (IOException e) {
            log.error("规则文件写入失败", e);
            Map<String, Object> errorBody = new LinkedHashMap<>();
            errorBody.put("error", "规则文件写入失败: " + e.getMessage());
            return ResponseEntity.internalServerError().body(errorBody);
        } catch (Exception e) {
            log.error("规则更新失败", e);
            Map<String, Object> errorBody = new LinkedHashMap<>();
            errorBody.put("error", "规则更新失败: " + e.getMessage());
            return ResponseEntity.internalServerError().body(errorBody);
        }
    }

    /**
     * 获取待审批的L4规则提案
     * GET /api/rules/pending
     */
    @GetMapping("/pending")
    public ResponseEntity<?> listPendingProposals() {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("total", pendingProposals.size());
        result.put("proposals", new ArrayList<>(pendingProposals.values()));
        return ResponseEntity.ok(result);
    }

    /**
     * 审批通过L4规则提案
     * POST /api/rules/pending/{proposalId}/approve
     */
    @PostMapping("/pending/{proposalId}/approve")
    public ResponseEntity<?> approveProposal(@PathVariable String proposalId, @RequestBody(required = false) Map<String, String> body) {
        try {
            TargetDecision.RuleProposal proposal = pendingProposals.remove(proposalId);
            if (proposal == null) {
                return ResponseEntity.notFound().build();
            }

            // 保存为L4规则文件
            String fileName = "L4-" + proposalId + ".drl";
            Path l4Dir = Paths.get("src/main/resources/rules/l4-learning");
            if (!Files.exists(l4Dir)) {
                Files.createDirectories(l4Dir);
            }

            String ruleContent = proposal.getRuleContent();
            if (ruleContent == null || ruleContent.isEmpty()) {
                ruleContent = "// L4规则提案 " + proposalId + "\n// 来源: " + proposal.getSource() + "\n// 置信度: " + proposal.getConfidence();
            }

            Path filePath = l4Dir.resolve(fileName);
            Files.writeString(filePath, ruleContent, StandardCharsets.UTF_8);

            // 重新加载规则
            droolsConfig.reloadRules();

            Map<String, Object> result = new LinkedHashMap<>();
            result.put("status", "OK");
            result.put("message", "L4规则已审批通过并保存");
            result.put("ruleFile", fileName);

            log.info("L4规则提案已审批通过: proposalId={}, file={}", proposalId, fileName);
            return ResponseEntity.ok(result);

        } catch (Exception e) {
            log.error("规则审批失败", e);
            Map<String, Object> errorBody = new LinkedHashMap<>();
            errorBody.put("error", "规则审批失败: " + e.getMessage());
            return ResponseEntity.internalServerError().body(errorBody);
        }
    }

    /**
     * 拒绝L4规则提案
     * POST /api/rules/pending/{proposalId}/reject
     */
    @PostMapping("/pending/{proposalId}/reject")
    public ResponseEntity<?> rejectProposal(@PathVariable String proposalId, @RequestBody Map<String, String> body) {
        TargetDecision.RuleProposal proposal = pendingProposals.remove(proposalId);
        if (proposal == null) {
            return ResponseEntity.notFound().build();
        }

        String reason = body != null ? body.getOrDefault("reason", "未提供原因") : "未提供原因";
        log.info("L4规则提案已拒绝: proposalId={}, reason={}", proposalId, reason);

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("status", "OK");
        result.put("message", "规则提案已拒绝");
        result.put("reason", reason);

        return ResponseEntity.ok(result);
    }

    /**
     * 获取规则版本历史
     * GET /api/rules/versions
     */
    @GetMapping("/versions")
    public ResponseEntity<?> listVersions() {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("total", versionHistory.size());
        result.put("versions", new HashMap<>(versionHistory));
        return ResponseEntity.ok(result);
    }

    // ========== 公共方法 ==========

    /**
     * 提交规则提案
     * 供RuleEngineService等外部服务调用，将L4规则提案加入待审批队列
     *
     * @param proposalId 提案唯一标识
     * @param proposal   规则提案对象
     */
    public void submitProposal(String proposalId, TargetDecision.RuleProposal proposal) {
        pendingProposals.put(proposalId, proposal);
        log.info("L4规则提案已提交: proposalId={}, confidence={}", proposalId, proposal.getConfidence());
    }

    // ========== 辅助方法 ==========

    /**
     * 加载所有规则信息
     */
    private List<RuleInfo> loadAllRuleInfos() {
        List<RuleInfo> rules = new ArrayList<>();

        try {
            Path rulesDir = Paths.get("src/main/resources/rules");
            if (!Files.exists(rulesDir)) {
                return rules;
            }

            // 遍历所有.drl文件
            Files.walk(rulesDir)
                .filter(Files::isRegularFile)
                .filter(p -> p.toString().endsWith(".drl"))
                .forEach(p -> {
                    try {
                        String content = Files.readString(p, StandardCharsets.UTF_8);
                        List<RuleInfo> fileRules = parseRuleInfos(content, p);
                        rules.addAll(fileRules);
                    } catch (IOException e) {
                        log.warn("读取规则文件失败: {}", p, e);
                    }
                });
        } catch (IOException e) {
            log.error("遍历规则目录失败", e);
        }

        return rules;
    }

    /**
     * 从DRL文件内容解析规则信息
     */
    private List<RuleInfo> parseRuleInfos(String drlContent, Path filePath) {
        List<RuleInfo> rules = new ArrayList<>();

        // 简单解析: 查找 "rule" 声明
        String[] lines = drlContent.split("\n");
        String currentRuleName = null;
        StringBuilder currentRuleContent = new StringBuilder();
        boolean inRule = false;

        for (String line : lines) {
            String trimmed = line.trim();
            if (trimmed.matches("(?i)rule\\s+\"[^\"]+\"")) {
                // 提取规则名称
                currentRuleName = trimmed.replaceAll("(?i)rule\\s+\"([^\"]+)\".*", "$1");
                currentRuleContent = new StringBuilder();
                currentRuleContent.append(line).append("\n");
                inRule = true;
            } else if (trimmed.equals("end") && inRule) {
                currentRuleContent.append(line).append("\n");

                RuleInfo info = new RuleInfo();
                info.setRuleId(currentRuleName);
                info.setName(extractRuleDescription(drlContent, currentRuleName));
                info.setContent(currentRuleContent.toString());
                info.setLayer(determineLayer(filePath));
                info.setSource(determineSource(filePath));
                info.setStatus("ACTIVE");
                info.setVersion("1.0");
                info.setFilePath(filePath.toString());
                info.setActionType(extractActionType(currentRuleContent.toString()));
                info.setConfidence(0.85);

                rules.add(info);
                inRule = false;
            } else if (inRule) {
                currentRuleContent.append(line).append("\n");
            }
        }

        return rules;
    }

    private int determineLayer(Path filePath) {
        String pathStr = filePath.toString().replace('\\', '/');
        if (pathStr.contains("l2-doctrine")) return 2;
        if (pathStr.contains("l3-tactical")) return 3;
        if (pathStr.contains("l4-learning")) return 4;
        return 1;
    }

    private String determineSource(Path filePath) {
        String pathStr = filePath.toString().replace('\\', '/');
        if (pathStr.contains("l2-doctrine")) return "L2_DOCTRINE";
        if (pathStr.contains("l3-tactical")) return "L3_TACTICAL";
        if (pathStr.contains("l4-learning")) return "L4_LEARNED";
        return "UNKNOWN";
    }

    private String extractRuleDescription(String drlContent, String ruleName) {
        // 尝试在规则声明附近查找注释行
        for (String line : drlContent.split("\n")) {
            if (line.contains(ruleName) && line.contains("//")) {
                return line.substring(line.indexOf("//") + 2).trim();
            }
        }
        return ruleName;
    }

    private String extractActionType(String ruleContent) {
        // 从规则动作中提取行动类型
        if (ruleContent.contains("setThreatLevel")) return "THREAT_CLASSIFICATION";
        if (ruleContent.contains("setPrimaryStrategy") || ruleContent.contains("strategy")) return "STRATEGY_MATCH";
        if (ruleContent.contains("BLOCK") || ruleContent.contains("WARN")) return "ROE_CONSTRAINT";
        if (ruleContent.contains("escalat")) return "THREAT_ESCALATION";
        return "UNKNOWN";
    }

    private void saveVersion(String ruleId, RuleInfo currentRule, String oldContent) {
        RuleInfo version = new RuleInfo();
        version.setRuleId(ruleId);
        version.setContent(oldContent);
        version.setVersion(currentRule.getVersion());
        version.setUpdateTime(LocalDateTime.now());

        versionHistory.computeIfAbsent(ruleId, k -> new ArrayList<>()).add(version);

        // 最多保留10个版本
        List<RuleInfo> versions = versionHistory.get(ruleId);
        if (versions.size() > 10) {
            versions.remove(0);
        }
    }

    private String incrementVersion(String currentVersion) {
        try {
            String[] parts = currentVersion.split("\\.");
            int major = Integer.parseInt(parts[0]);
            int minor = parts.length > 1 ? Integer.parseInt(parts[1]) : 0;
            return major + "." + (minor + 1);
        } catch (Exception e) {
            return "1.1";
        }
    }
}
