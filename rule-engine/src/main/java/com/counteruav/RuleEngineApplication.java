package com.counteruav;

import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.core.env.Environment;

import java.net.InetAddress;
import java.net.UnknownHostException;

/**
 * 反无人机决策规则引擎 - 启动类    ---Spring Boot 启动类
 * <p>
 * 基于 Drools 7.73 规则引擎，提供多层级威胁评估与决策推理服务。
 * 支持 L1物理层、L2条令层、L3战术层、L4学习层四级规则管道。
 * </p>
 *
 * @author counteruav
 * @since 1.0.0
 */
@Slf4j
@SpringBootApplication
public class RuleEngineApplication {

    private static final String BANNER = "\n" +
            "  ____                  _                                  \n" +
            " / ___|___  _ __  _ __ | |_ ___ _ __ ___   ___   _ __ __ _\n" +
            "| |   / _ \\| '_ \\| '_ \\| __/ _ \\ '__/ _ \\ / _ \\ | '__/ _` |\n" +
            "| |__| (_) | | | | | | | ||  __/ | | (_) | (_) || | | (_| |\n" +
            " \\____\\___/|_| |_|_| |_|\\__\\___|_|  \\___/ \\___/ |_|  \\__,_|\n" +
            "                                                           \n" +
            "  反无人机决策规则引擎  v1.0.0                              \n" +
            "  Counter-UAV Decision Rule Engine                         \n";

    public static void main(String[] args) throws UnknownHostException {
        // 输出启动横幅
        System.out.println(BANNER);

        log.info("========================================");
        log.info("  反无人机决策规则引擎 正在启动...");
        log.info("========================================");

        // 启动 Spring 容器，自动扫描 com.counteruav 包下的所有组件
        ConfigurableApplicationContext context = SpringApplication.run(RuleEngineApplication.class, args);

        Environment env = context.getEnvironment();
        // 获取服务器 IP 地址，支持外部访问
        String host = InetAddress.getLocalHost().getHostAddress();
        String port = env.getProperty("server.port", "8080");
        // 读取配置属性，若未配置则使用默认值（端口默认 8080）
        String contextPath = env.getProperty("server.servlet.context-path", "");

        log.info("========================================");
        log.info("  规则引擎启动成功！");
        log.info("  本地访问:    http://localhost:{}{}", port, contextPath);
        log.info("  外部访问:    http://{}:{}{}", host, port, contextPath);
        //  获取当前激活的配置文件（如 dev 、 prod ）
        log.info("  激活的配置文件: {}", String.join(",", env.getActiveProfiles()));
        log.info("========================================");
    }
}
