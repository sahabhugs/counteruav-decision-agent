# ============================================================
# 规则引擎 Dockerfile - Spring Boot + Drools
# ============================================================

# ---- 构建阶段 ----
FROM maven:3.8-openjdk-8 as builder

WORKDIR /build
COPY pom.xml .
# 缓存依赖
RUN mvn dependency:go-offline -B

COPY src ./src
RUN mvn clean package -DskipTests -B

# ---- 运行阶段 ----
FROM openjdk:8-jre-alpine

LABEL maintainer="CounterUAV Team"
LABEL description="反无人机规则引擎服务 (Spring Boot + Drools)"

# 安装调试工具
RUN apk add --no-cache curl tzdata && \
    cp /usr/share/zoneinfo/Asia/Shanghai /etc/localtime && \
    echo "Asia/Shanghai" > /etc/timezone

WORKDIR /app

# 复制JAR
COPY --from=builder /build/target/rule-engine-*.jar app.jar

# 创建日志和数据目录
RUN mkdir -p /app/logs /app/data

# 非root用户运行
RUN addgroup -g 1000 cuav && \
    adduser -D -u 1000 -G cuav cuav && \
    chown -R cuav:cuav /app
USER cuav

# JVM参数
ENV JAVA_OPTS="-Xms512m -Xmx1024m -XX:+UseG1GC -XX:MaxGCPauseMillis=200"

# 健康检查
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8080/actuator/health || exit 1

EXPOSE 8080

ENTRYPOINT ["sh", "-c", "java $JAVA_OPTS -jar app.jar"]
