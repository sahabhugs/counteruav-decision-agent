package com.counteruav.config;

import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestTemplate;

import java.time.Duration;

/**
 * RestTemplate 配置
 * <p>
 * 提供 HTTP 客户端 Bean，配置连接超时和读取超时，
 * 用于与服务端 LLM Agent 的 RESTful 通信。
 * </p>
 *
 * @author counteruav
 * @since 1.0.0
 */
@Slf4j
@Configuration
public class RestTemplateConfig {

    @Value("${counteruav.llm.agent-connect-timeout-ms:30000}")
    private int connectTimeoutMs;

    @Value("${counteruav.llm.agent-read-timeout-ms:60000}")
    private int readTimeoutMs;

    /**
     * 创建 RestTemplate Bean
     * <p>
     * 配置超时策略：
     * - 连接超时：默认30秒
     * - 读取超时：默认60秒（LLM推理可能耗时较长）
     * </p>
     *
     * @param builder Spring Boot RestTemplate构建器
     * @return 配置完成的RestTemplate实例
     */
    @Bean
    public RestTemplate restTemplate(RestTemplateBuilder builder) {
        log.info("初始化 RestTemplate: connectTimeout={}ms, readTimeout={}ms",
                connectTimeoutMs, readTimeoutMs);

        return builder
                .setConnectTimeout(Duration.ofMillis(connectTimeoutMs))
                .setReadTimeout(Duration.ofMillis(readTimeoutMs))
                .build();
    }
}
