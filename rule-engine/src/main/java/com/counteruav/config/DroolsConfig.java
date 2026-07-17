package com.counteruav.config;

import lombok.extern.slf4j.Slf4j;
import org.kie.api.KieBase;
import org.kie.api.KieServices;
import org.kie.api.builder.KieBuilder;
import org.kie.api.builder.KieFileSystem;
import org.kie.api.builder.KieRepository;
import org.kie.api.builder.Message;
import org.kie.api.builder.Results;
import org.kie.api.io.Resource;
import org.kie.api.io.ResourceType;
import org.kie.api.runtime.KieContainer;
import org.kie.api.runtime.KieSession;
import org.kie.api.runtime.StatelessKieSession;
import org.kie.internal.io.ResourceFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ResourceLoader;
import org.springframework.core.io.support.PathMatchingResourcePatternResolver;
import org.springframework.core.io.support.ResourcePatternResolver;

import javax.annotation.PostConstruct;
import java.io.IOException;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.locks.ReentrantReadWriteLock;

/**
 * Drools 规则引擎配置
 * <p>
 * 管理 KieContainer 生命周期，提供 L1-L4 各级规则会话的工厂方法，
 * 并支持运行时规则热加载。
 * </p>
 *
 * @author counteruav
 * @since 1.0.0
 */
@Slf4j
@Configuration
public class DroolsConfig {

    /**
     * L2 条令层规则文件路径模式
     */
    @Value("${drools.rule.l2-path:classpath:rules/l2-doctrine/}")
    private String l2RulesPath;

    /**
     * L3 战术层规则文件路径模式
     */
    @Value("${drools.rule.l3-path:classpath:rules/l3-tactical/}")
    private String l3RulesPath;

    /**
     * L1 物理层规则文件路径模式
     */
    @Value("${drools.rule.l1-path:classpath:rules/l1-physics/}")
    private String l1RulesPath;

    /**
     * L4 学习层规则文件路径模式
     */
    @Value("${drools.rule.l4-path:classpath:rules/l4-learning/}")
    private String l4RulesPath;

    /**
     * 是否启用规则热加载
     */
    @Value("${drools.rule.hot-reload-enabled:true}")
    private boolean hotReloadEnabled;

    private final KieServices kieServices;
    private volatile KieContainer kieContainer;
    private final ReentrantReadWriteLock reloadLock = new ReentrantReadWriteLock();

    /**
     * 规则分组配置，定义各组规则对应的路径和资源类型
     */
    private static class RuleGroup {
        final String name;
        final String[] paths;
        final ResourceType resourceType;

        RuleGroup(String name, String[] paths, ResourceType resourceType) {
            this.name = name;
            this.paths = paths;
            this.resourceType = resourceType;
        }
    }

    public DroolsConfig() {
        this.kieServices = KieServices.Factory.get();
        log.info("Drools KieServices 实例化完成");
    }

    /**
     * 应用启动后验证规则文件并初始化 KieContainer
     */
    @PostConstruct
    public void validateRulesOnStartup() {
        log.info("========================================");
        log.info("  开始验证 Drools 规则文件...");
        log.info("========================================");

        // 检查各层规则路径下是否存在规则文件
        String[] allPaths = {l1RulesPath, l2RulesPath, l3RulesPath, l4RulesPath};
        String[] pathNames = {"L1物理层", "L2条令层", "L3战术层", "L4学习层"};

        for (int i = 0; i < allPaths.length; i++) {
            int count = countRuleFiles(allPaths[i]);
            if (count > 0) {
                log.info("[{}] 检测到 {} 个规则文件，路径: {}", pathNames[i], count, allPaths[i]);
            } else {
                log.warn("[{}] 未检测到规则文件，路径: {}，将使用空规则库", pathNames[i], allPaths[i]);
            }
        }

        // 尝试构建 KieContainer
        try {
            reloadLock.writeLock().lock();
            this.kieContainer = buildKieContainer();
            log.info("KieContainer 构建成功，规则引擎就绪");
        } catch (Exception e) {
            log.error("KieContainer 构建失败: {}", e.getMessage(), e);
            log.warn("将以降级模式运行——创建最小化空 KieContainer");
            try {
                this.kieContainer = buildMinimalKieContainer();
                log.info("最小化 KieContainer 构建成功（降级模式）");
            } catch (Exception ex) {
                log.error("降级模式 KieContainer 构建也失败: {}", ex.getMessage(), ex);
            }
        } finally {
            reloadLock.writeLock().unlock();
        }

        log.info("========================================");
        log.info("  Drools 规则文件验证完成");
        log.info("========================================");
    }

    /**
     * 创建 KieContainer Bean
     * <p>
     * 负责加载 L2 条令层和 L3 战术层规则，以及 kmodule.xml 中定义的其他规则库。
     * </p>
     */
    @Bean
    public KieContainer kieContainer() {
        if (this.kieContainer == null) {
            reloadLock.writeLock().lock();
            try {
                if (this.kieContainer == null) {
                    this.kieContainer = buildKieContainer();
                }
            } finally {
                reloadLock.writeLock().unlock();
            }
        }
        return this.kieContainer;
    }

    // ============================================================
    // KieSession 工厂方法
    // ============================================================

    /**
     * 获取或创建 L1 物理层无状态会话
     * <p>
     * 无状态会话适用于高频快速匹配场景，不需要维护会话状态。
     * </p>
     *
     * @return StatelessKieSession 实例
     */
    public StatelessKieSession getL1StatelessSession() {
        KieContainer container = kieContainer();
        if (container == null) {
            log.error("KieContainer 未初始化，无法获取 L1 无状态会话");
            throw new IllegalStateException("规则引擎容器未就绪");
        }
        try {
            StatelessKieSession session = container.newStatelessKieSession("L1StatelessSession");
            log.debug("L1 无状态会话创建成功");
            return session;
        } catch (Exception e) {
            log.error("创建 L1 无状态会话失败: {}", e.getMessage());
            throw new RuntimeException("无法创建 L1 规则会话", e);
        }
    }

    /**
     * 获取或创建 L2 条令层有状态会话
     * <p>
     * 有状态会话支持跨多次推理的上下文累积，适用于条令合规性检查。
     * </p>
     *
     * @return KieSession 实例（需调用方负责 dispose）
     */
    @Bean
    public KieSession l2StatefulSession() {
        KieContainer container = kieContainer();
        if (container == null) {
            log.error("KieContainer 未初始化，无法获取 L2 有状态会话");
            throw new IllegalStateException("规则引擎容器未就绪");
        }
        try {
            KieSession session = container.newKieSession("L2StatefulSession");
            log.debug("L2 有状态会话创建成功");
            return session;
        } catch (Exception e) {
            log.warn("创建 L2 有状态会话失败: {}，尝试使用默认会话", e.getMessage());
            // 降级：尝试获取默认 KieSession
            KieBase kieBase = container.getKieBase("L2DoctrineBase");
            if (kieBase != null) {
                log.info("使用 L2DoctrineBase 创建会话（降级模式）");
                return kieBase.newKieSession();
            }
            throw new RuntimeException("无法创建 L2 规则会话，且无可用的降级方案", e);
        }
    }

    /**
     * 获取或创建 L3 战术层有状态会话
     * <p>
     * 支持多目标协同推理与资源分配决策。
     * </p>
     *
     * @return KieSession 实例（需调用方负责 dispose）
     */
    @Bean
    public KieSession l3StatefulSession() {
        KieContainer container = kieContainer();
        if (container == null) {
            log.error("KieContainer 未初始化，无法获取 L3 有状态会话");
            throw new IllegalStateException("规则引擎容器未就绪");
        }
        try {
            KieSession session = container.newKieSession("L3StatefulSession");
            log.debug("L3 有状态会话创建成功");
            return session;
        } catch (Exception e) {
            log.warn("创建 L3 有状态会话失败: {}，尝试使用默认会话", e.getMessage());
            KieBase kieBase = container.getKieBase("L3TacticalBase");
            if (kieBase != null) {
                log.info("使用 L3TacticalBase 创建会话（降级模式）");
                return kieBase.newKieSession();
            }
            throw new RuntimeException("无法创建 L3 规则会话，且无可用的降级方案", e);
        }
    }

    /**
     * 获取或创建 L4 学习层有状态会话
     *
     * @return KieSession 实例（需调用方负责 dispose）
     */
    public KieSession getL4StatefulSession() {
        KieContainer container = kieContainer();
        if (container == null) {
            log.error("KieContainer 未初始化，无法获取 L4 有状态会话");
            throw new IllegalStateException("规则引擎容器未就绪");
        }
        try {
            KieSession session = container.newKieSession("L4StatefulSession");
            log.debug("L4 有状态会话创建成功");
            return session;
        } catch (Exception e) {
            log.warn("创建 L4 有状态会话失败: {}，使用降级方案", e.getMessage());
            KieBase kieBase = container.getKieBase("L4LearningBase");
            if (kieBase != null) {
                return kieBase.newKieSession();
            }
            throw new RuntimeException("无法创建 L4 规则会话", e);
        }
    }

    // ============================================================
    // 规则热加载机制
    // ============================================================

    /**
     * 重新加载所有规则文件
     * <p>
     * 清除现有的 KieContainer 并基于最新的规则文件重建。
     * 该方法是线程安全的，使用读写锁保护。
     * </p>
     *
     * @return 是否加载成功
     */
    public boolean reloadRules() {
        if (!hotReloadEnabled) {
            log.warn("规则热加载功能未启用，跳过重载");
            return false;
        }

        log.info("========================================");
        log.info("  开始重新加载规则文件...");
        log.info("========================================");

        reloadLock.writeLock().lock();
        try {
            KieContainer oldContainer = this.kieContainer;

            // 重建 KieContainer
            this.kieContainer = buildKieContainer();

            // 清理旧的 KieContainer
            if (oldContainer != null) {
                try {
                    oldContainer.dispose();
                    log.info("旧的 KieContainer 已释放");
                } catch (Exception e) {
                    log.warn("释放旧 KieContainer 时出现警告: {}", e.getMessage());
                }
            }

            log.info("规则文件重新加载成功");
            log.info("========================================");
            return true;

        } catch (Exception e) {
            log.error("规则文件重新加载失败: {}", e.getMessage(), e);
            log.warn("保持使用现有的 KieContainer，系统继续运行");
            log.info("========================================");
            return false;
        } finally {
            reloadLock.writeLock().unlock();
        }
    }

    /**
     * 针对特定规则层进行重载
     * <p>
     * 由于 Drools 7.x 的 KieContainer 是整体构建的，
     * 此处执行全量重载。在未来版本中可考虑按 KieBase 细粒度重载。
     * </p>
     *
     * @param layerName 规则层名称（L1/L2/L3/L4）
     * @return 是否加载成功
     */
    public boolean reloadRulesForLayer(String layerName) {
        log.info("请求重载 [{}] 层规则，执行全量规则重载", layerName);
        return reloadRules();
    }

    // ============================================================
    // 私有构建方法
    // ============================================================

    /**
     * 构建完整的 KieContainer
     * <p>
     * 首先尝试通过 classpath 加载 kmodule.xml，
     * 如果规则文件目录存在 .drl 或其他规则文件，则通过编程方式加载。
     * </p>
     */
    private KieContainer buildKieContainer() {
        KieFileSystem kieFileSystem = kieServices.newKieFileSystem();

        // 确保 kmodule.xml 在 classpath 上
        // 注意：kmodule.xml 由 Drools 自动从 classpath:META-INF/ 或 classpath 根发现。
        // 此处通过 KieFileSystem 显式注册，确保使用项目中的 kmodule 配置。
        Resource kmoduleResource = ResourceFactory.newClassPathResource("kmodule.xml");
        kieFileSystem.write("src/main/resources/META-INF/kmodule.xml", kmoduleResource);

        // 加载各层规则文件到 KieFileSystem
        List<RuleGroup> ruleGroups = Arrays.asList(
                new RuleGroup("L1物理层", new String[]{"classpath*:rules/l1-physics/**/*.*"}, ResourceType.DRL),
                new RuleGroup("L2条令层", new String[]{"classpath*:rules/l2-doctrine/**/*.*"}, ResourceType.DRL),
                new RuleGroup("L3战术层", new String[]{"classpath*:rules/l3-tactical/**/*.*"}, ResourceType.DRL),
                new RuleGroup("L4学习层", new String[]{"classpath*:rules/l4-learning/**/*.*"}, ResourceType.DRL)
        );

        int totalLoaded = 0;
        for (RuleGroup group : ruleGroups) {
            int count = loadRuleGroup(kieFileSystem, group);
            totalLoaded += count;
        }

        log.info("共加载 {} 个规则文件到 KieFileSystem", totalLoaded);

        // 构建 KieModule
        KieBuilder kieBuilder = kieServices.newKieBuilder(kieFileSystem);
        kieBuilder.buildAll();

        Results results = kieBuilder.getResults();
        if (results.hasMessages(Message.Level.ERROR)) {
            List<Message> errors = results.getMessages(Message.Level.ERROR);
            StringBuilder sb = new StringBuilder("规则编译错误:\n");
            for (Message error : errors) {
                sb.append("  - [").append(error.getPath()).append("] ")
                        .append(error.getText()).append("\n");
            }
            log.error(sb.toString());
            throw new RuntimeException("规则编译失败，共有 " + errors.size() + " 个错误");
        }

        // 打印警告信息
        if (results.hasMessages(Message.Level.WARNING)) {
            List<Message> warnings = results.getMessages(Message.Level.WARNING);
            log.warn("规则编译产生 {} 个警告:", warnings.size());
            for (Message warning : warnings) {
                log.warn("  - [{}] {}", warning.getPath(), warning.getText());
            }
        }

        log.info("规则编译完成，生成 KieContainer");
        return kieServices.newKieContainer(kieServices.getRepository().getDefaultReleaseId());
    }

    /**
     * 构建最小化的 KieContainer（降级模式）
     * <p>
     * 当完整规则加载失败时使用，确保应用可以启动。
     * </p>
     */
    private KieContainer buildMinimalKieContainer() {
        KieFileSystem kieFileSystem = kieServices.newKieFileSystem();

        // 仅注册 kmodule.xml，不加载任何规则文件
        Resource kmoduleResource = ResourceFactory.newClassPathResource("kmodule.xml");
        kieFileSystem.write("src/main/resources/META-INF/kmodule.xml", kmoduleResource);

        // 为每个规则包写入一个空的占位规则，防止 KieBase 创建失败
        String[] packages = {"l1_physics", "l2_doctrine", "l3_tactical", "l4_learning"};
        for (String pkg : packages) {
            String emptyRule = "package rules." + pkg + "\n"
                    + "// 降级模式占位规则 - 该规则库暂无规则文件\n"
                    + "rule \"Placeholder_" + pkg.replace("-", "_") + "\"\n"
                    + "  when\n"
                    + "    // 无匹配条件\n"
                    + "  then\n"
                    + "    // 无操作\n"
                    + "end\n";
            kieFileSystem.write("src/main/resources/rules/" + pkg + "/placeholder.drl", emptyRule);
        }

        KieBuilder kieBuilder = kieServices.newKieBuilder(kieFileSystem);
        kieBuilder.buildAll();

        return kieServices.newKieContainer(kieServices.getRepository().getDefaultReleaseId());
    }

    /**
     * 加载一组规则文件到 KieFileSystem
     *
     * @param kieFileSystem KieFileSystem 实例
     * @param group         规则组配置
     * @return 成功加载的文件数量
     */
    private int loadRuleGroup(KieFileSystem kieFileSystem, RuleGroup group) {
        int loadedCount = 0;
        for (String pathPattern : group.paths) {
            try {
                ResourcePatternResolver resolver = new PathMatchingResourcePatternResolver();
                org.springframework.core.io.Resource[] resources = resolver.getResources(pathPattern);
                for (org.springframework.core.io.Resource resource : resources) {
                    // 只加载 .drl 文件，排除 JSON 等非规则文件
            if (resource.isReadable()
                    && !resource.getFilename().contains("placeholder")
                    && resource.getFilename().endsWith(".drl")) {
                        String virtualPath = "src/main/resources/rules/"
                                + extractPackageFromPath(pathPattern) + "/"
                                + resource.getFilename();
                        Resource droolsResource = ResourceFactory.newInputStreamResource(
                                resource.getInputStream());
                        droolsResource.setResourceType(group.resourceType);
                        kieFileSystem.write(virtualPath, droolsResource);
                        loadedCount++;
                        log.debug("[{}] 加载规则文件: {}", group.name, resource.getFilename());
                    }
                }
            } catch (IOException e) {
                // 规则文件不存在是正常情况（开发初期），记录调试日志而非错误
                log.debug("[{}] 规则路径下未找到文件: {} ({})", group.name, pathPattern, e.getMessage());
            }
        }

        if (loadedCount == 0) {
            log.info("[{}] 未加载任何规则文件（规则目录为空或不存在），将使用空规则库", group.name);
        } else {
            log.info("[{}] 成功加载 {} 个规则文件", group.name, loadedCount);
        }
        return loadedCount;
    }

    /**
     * 从路径模式中提取包名（连字符转换为下划线以符合 Java 包名规范）
     * <p>
     * 例如 classpath*:rules/l2-doctrine/** → l2_doctrine
     * </p>
     */
    private String extractPackageFromPath(String pathPattern) {
        // 移除 classpath*: 前缀
        String path = pathPattern.replace("classpath*:", "").replace("classpath:", "");
        // 移除 **/*.* 后缀
        path = path.replace("/**/*.*", "").replace("/**", "");
        // 移除开头的 /
        if (path.startsWith("/")) {
            path = path.substring(1);
        }
        // 取最后一段作为包目录名
        int lastSlash = path.lastIndexOf('/');
        if (lastSlash >= 0) {
            path = path.substring(lastSlash + 1);
        }
        // 将连字符转换为下划线，确保与 DRL 文件的 package 声明一致
        return path.replace("-", "_");
    }

    /**
     * 统计指定路径下的规则文件数量
     *
     * @param pathPattern 路径模式
     * @return 文件数量
     */
    private int countRuleFiles(String pathPattern) {
        try {
            ResourcePatternResolver resolver = new PathMatchingResourcePatternResolver();
            String searchPattern = pathPattern;
            if (!searchPattern.endsWith("/*.*") && !searchPattern.endsWith("/**")) {
                if (searchPattern.endsWith("/")) {
                    searchPattern += "**/*.*";
                } else {
                    searchPattern += "/**/*.*";
                }
            }
            org.springframework.core.io.Resource[] resources = resolver.getResources(searchPattern);
            return resources.length;
        } catch (IOException e) {
            log.debug("统计规则文件数量时出现IO异常: {}", e.getMessage());
            return 0;
        }
    }
}
