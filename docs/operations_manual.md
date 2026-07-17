# 反无人机辅助决策系统 - 运维手册

> 版本: 1.0.0 | 最后更新: 2026-07-13 | 密级: 内部

---

## 目录

1. [系统概述](#第一章-系统概述)
2. [安装部署](#第二章-安装部署)
3. [配置指南](#第三章-配置指南)
4. [规则管理](#第四章-规则管理)
5. [LLM智能体管理](#第五章-llm智能体管理)
6. [备份与恢复](#第六章-备份与恢复)
7. [监控与告警](#第七章-监控与告警)
8. [故障排查](#第八章-故障排查)

---

## 第一章 系统概述

### 1.1 系统定位

反无人机辅助决策系统 (Counter-UAV Decision Agent) 是一款面向反无人机作战指挥的多层规则引擎+LLM智能体混合决策系统。系统通过四层规则架构 (L1物理层→L2战术层→L3策略层→L4元规则层)，实现从原始传感器数据到最终反制决策的全链路智能化处理。

### 1.2 核心能力

| 能力 | 描述 |
|------|------|
| 多传感器融合 | 雷达、RF探测、光电、声学等多源数据融合处理 |
| 自主威胁评估 | 基于无人机类型、运动特征、环境上下文的5级威胁评估 |
| 智能反制决策 | 自动匹配最优反制手段(射频干扰/GNSS欺骗/激光毁伤/动能拦截) |
| 多设备协同 | 管理多台反制设备的协同工作、冲突检测与资源调度 |
| 策略自适应 | 8类场景模板 + LLM驱动的未知场景自适应推理 |
| 人机协同 | 操作员在环确认、手动超控、策略推演 |
| 全程留痕 | 决策过程全记录、规则触达追踪、反馈学习闭环 |

### 1.3 硬件要求

| 组件 | 最低配置 | 推荐配置 | 高性能配置 |
|------|---------|---------|-----------|
| CPU | 8核 x86_64, 2.5GHz | 16核 x86_64, 3.0GHz+ | 32核 x86_64, 3.5GHz+ |
| 内存 | 16 GB DDR4 | 32 GB DDR4 ECC | 64 GB DDR4 ECC |
| GPU (LLM) | NVIDIA T4 16GB (可选) | NVIDIA A10 24GB | NVIDIA A100 40GB |
| 系统盘 | SSD 256GB | NVMe SSD 512GB | NVMe SSD 1TB |
| 数据盘 | HDD 1TB | SSD 2TB | NVMe SSD 4TB (RAID1) |
| 网络 | 千兆以太网 | 万兆光纤 | 双万兆光纤 (Bond) |
| 传感器接口 | 1x 千兆网口+USB3.0 | 2x 千兆网口+USB3.0 | 4x 万兆网口 |

### 1.4 软件要求

| 软件 | 版本要求 | 说明 |
|------|---------|------|
| 操作系统 | Ubuntu 22.04 LTS / CentOS 8+ / Debian 12 | 推荐Ubuntu 22.04 LTS |
| Docker | 24.0+ | 容器化部署 |
| Docker Compose | 2.20+ | 多容器编排 |
| Python | 3.10 ~ 3.12 | 后端服务 |
| MySQL | 8.0.32+ | 规则库、知识库、决策日志 |
| Redis | 7.0+ (可选) | 消息队列、缓存 |
| JDK | 17 LTS | Drools/KIE Server运行环境 |
| Node.js | 18+ (可选) | 前端态势显示构建 |

### 1.5 支持的反制设备类型

| 设备类型 | 接口协议 | 典型型号 | 控制方式 |
|---------|---------|---------|---------|
| 全频段干扰器 | TCP Socket / HTTP API | 各类国产干扰器 | 功率设定、频段切换、开关控制 |
| GNSS欺骗器 | TCP Socket / Serial | 导航欺骗设备 | 欺骗模式、偏移量、功率 |
| 激光反制设备 | TCP Socket / RS-485 | 光纤激光器 | 功率、照射时间、云台控制 |
| 网枪/捕捉器 | HTTP API / Relay | 物理捕捉设备 | 发射触发、保险解除 |
| 光电转台 | ONVIF / RTSP | 各类光电吊舱 | 云台控制、变焦、跟踪锁定 |

---

## 第二章 安装部署

### 2.1 Docker部署 (推荐)

#### 2.1.1 前提条件检查

```bash
# 检查操作系统版本
cat /etc/os-release
# 预期: Ubuntu 22.04 LTS

# 检查内核版本 (Docker需要3.10+)
uname -r

# 检查可用磁盘空间 (至少100GB)
df -h

# 检查内存
free -h

# 检查NVIDIA驱动 (如使用GPU)
nvidia-smi

# 检查端口可用性 (以下端口不应被占用)
# 8000: API服务
# 8080: KIE Server
# 3306: MySQL
# 6379: Redis
# 9090: Prometheus (监控)
# 3000: Grafana (监控)
netstat -tlnp | grep -E "8000|8080|3306|6379|9090|3000"
```

#### 2.1.2 安装Docker和Docker Compose

```bash
# 卸载旧版本
sudo apt-get remove docker docker-engine docker.io containerd runc

# 安装依赖
sudo apt-get update
sudo apt-get install -y \
    ca-certificates \
    curl \
    gnupg \
    lsb-release

# 添加Docker官方GPG密钥
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg

# 设置仓库
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# 安装Docker引擎
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# 验证安装
sudo docker --version
sudo docker compose version

# 将当前用户加入docker组 (免sudo)
sudo usermod -aG docker $USER
newgrp docker
```

#### 2.1.3 克隆代码仓库

```bash
# 创建部署目录
sudo mkdir -p /opt/counteruav
sudo chown $USER:$USER /opt/counteruav
cd /opt/counteruav

# 克隆代码 (使用实际的内部Git地址)
git clone git@internal-git.company.com:security/counteruav-decision-agent.git .
cd counteruav-decision-agent

# 切换到生产版本标签
git checkout v1.0.0
```

#### 2.1.4 配置环境变量

创建 `.env` 文件:

```bash
# ============================================================
# 反无人机辅助决策系统 - 环境配置文件
# ============================================================

# ---- 数据库配置 ----
MYSQL_HOST=mysql
MYSQL_PORT=3306
MYSQL_DATABASE=counteruav
MYSQL_USER=counteruav_admin
MYSQL_PASSWORD=<请修改为强密码>
MYSQL_ROOT_PASSWORD=<请修改为Root强密码>
MYSQL_POOL_SIZE=20
MYSQL_POOL_RECYCLE=3600

# ---- Redis配置 ----
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=<请修改为强密码>
REDIS_DB=0

# ---- 规则引擎配置 ----
KIE_SERVER_URL=http://kie-server:8080/kie-server/services/rest/server
KIE_SERVER_USER=kieserver
KIE_SERVER_PASSWORD=<请修改为强密码>
KIE_CONTAINER_ID=counteruav-rules-1.0.0
DROOLS_SESSION_POOL_SIZE=10
DROOLS_RULE_RELOAD_INTERVAL=300

# ---- LLM Agent配置 ----
LLM_API_ENDPOINT=https://api.anthropic.com/v1/messages
LLM_API_KEY=<请填入API密钥>
LLM_MODEL_NAME=claude-sonnet-4-20250514
LLM_MAX_TOKENS=4096
LLM_TEMPERATURE=0.3
LLM_TIMEOUT=30
LLM_MAX_RETRIES=3

# 本地模型备选 (当API不可用时)
LOCAL_LLM_ENDPOINT=http://localhost:11434/v1/chat/completions
LOCAL_LLM_MODEL=qwen2.5:32b

# ---- 传感器配置 (示例) ----
RADAR_1_IP=192.168.10.101
RADAR_1_PORT=8001
RADAR_2_IP=192.168.10.102
RADAR_2_PORT=8001
RF_DETECTOR_1_IP=192.168.10.201
RF_DETECTOR_1_PORT=9001
CAMERA_1_RTSP=rtsp://192.168.10.301:554/stream1
CAMERA_2_RTSP=rtsp://192.168.10.302:554/stream1

# ---- 反制设备配置 (示例) ----
JAMMER_2400_IP=192.168.20.101
JAMMER_2400_PORT=7001
JAMMER_5800_IP=192.168.20.102
JAMMER_5800_PORT=7001
SPOOFER_IP=192.168.20.201
SPOOFER_PORT=7002
LASER_IP=192.168.20.301
LASER_PORT=7003

# ---- 安全配置 ----
API_JWT_SECRET=<请生成随机密钥: openssl rand -hex 64>
API_CORS_ORIGINS=https://c2-console.internal.company.com
API_RATE_LIMIT=100

# ---- 日志配置 ----
LOG_LEVEL=INFO
LOG_FORMAT=json
LOG_RETENTION_DAYS=30
SYSLOG_HOST=<可选: 集中日志服务器IP>
SYSLOG_PORT=514

# ---- 部署环境 ----
DEPLOY_ENV=production
TIMEZONE=Asia/Shanghai
```

#### 2.1.5 Docker Compose启动

创建 `docker-compose.yml` (生产版本):

```yaml
version: '3.8'

services:
  mysql:
    image: mysql:8.0.32
    container_name: counteruav-mysql
    restart: unless-stopped
    environment:
      MYSQL_ROOT_PASSWORD: ${MYSQL_ROOT_PASSWORD}
      MYSQL_DATABASE: ${MYSQL_DATABASE}
      MYSQL_USER: ${MYSQL_USER}
      MYSQL_PASSWORD: ${MYSQL_PASSWORD}
    volumes:
      - mysql_data:/var/lib/mysql
      - ./sql/init:/docker-entrypoint-initdb.d:ro
    ports:
      - "127.0.0.1:3306:3306"
    command:
      - --character-set-server=utf8mb4
      - --collation-server=utf8mb4_unicode_ci
      - --max_connections=500
      - --innodb_buffer_pool_size=2G
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "localhost"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - counteruav-net

  redis:
    image: redis:7.2-alpine
    container_name: counteruav-redis
    restart: unless-stopped
    command: redis-server --requirepass ${REDIS_PASSWORD} --appendonly yes
    volumes:
      - redis_data:/data
    ports:
      - "127.0.0.1:6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "--raw", "incr", "ping"]
      interval: 10s
      timeout: 3s
      retries: 5
    networks:
      - counteruav-net

  kie-server:
    image: quay.io/kiegroup/kie-server:7.73.0.Final
    container_name: counteruav-kie
    restart: unless-stopped
    environment:
      KIE_SERVER_ID: counteruav-kie
      KIE_SERVER_LOCATION: http://kie-server:8080/kie-server/services/rest/server
      KIE_SERVER_USER: ${KIE_SERVER_USER}
      KIE_SERVER_PASSWORD: ${KIE_SERVER_PASSWORD}
      KIE_MAVEN_REPO: /opt/kie/data/m2
      JAVA_OPTS: -Xms2g -Xmx4g -Dorg.kie.server.persistence.ds=java:comp/env/jdbc/kieDS
    volumes:
      - kie_maven_repo:/opt/kie/data/m2
      - ./rules:/opt/kie/rules:ro
    ports:
      - "127.0.0.1:8080:8080"
    depends_on:
      mysql:
        condition: service_healthy
    networks:
      - counteruav-net

  decision-api:
    build:
      context: .
      dockerfile: Dockerfile
    image: counteruav-decision-agent:1.0.0
    container_name: counteruav-api
    restart: unless-stopped
    environment:
      - MYSQL_HOST=${MYSQL_HOST}
      - MYSQL_PORT=${MYSQL_PORT}
      - MYSQL_DATABASE=${MYSQL_DATABASE}
      - MYSQL_USER=${MYSQL_USER}
      - MYSQL_PASSWORD=${MYSQL_PASSWORD}
      - REDIS_HOST=${REDIS_HOST}
      - REDIS_PORT=${REDIS_PORT}
      - REDIS_PASSWORD=${REDIS_PASSWORD}
      - KIE_SERVER_URL=${KIE_SERVER_URL}
      - KIE_SERVER_USER=${KIE_SERVER_USER}
      - KIE_SERVER_PASSWORD=${KIE_SERVER_PASSWORD}
      - LLM_API_ENDPOINT=${LLM_API_ENDPOINT}
      - LLM_API_KEY=${LLM_API_KEY}
      - LLM_MODEL_NAME=${LLM_MODEL_NAME}
      - LOG_LEVEL=${LOG_LEVEL}
    volumes:
      - ./config:/app/config:ro
      - ./knowledge-base:/app/knowledge-base:ro
      - decision_logs:/app/logs
    ports:
      - "8000:8000"
    depends_on:
      mysql:
        condition: service_healthy
      kie-server:
        condition: service_started
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 15s
      timeout: 5s
      retries: 3
    networks:
      - counteruav-net

  prometheus:
    image: prom/prometheus:v2.48.0
    container_name: counteruav-prometheus
    restart: unless-stopped
    volumes:
      - ./config/prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - prometheus_data:/prometheus
    ports:
      - "127.0.0.1:9090:9090"
    networks:
      - counteruav-net

  grafana:
    image: grafana/grafana:10.2.0
    container_name: counteruav-grafana
    restart: unless-stopped
    environment:
      GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_ADMIN_PASSWORD:-admin}
    volumes:
      - grafana_data:/var/lib/grafana
      - ./config/grafana-dashboards:/etc/grafana/provisioning/dashboards:ro
    ports:
      - "127.0.0.1:3000:3000"
    depends_on:
      - prometheus
    networks:
      - counteruav-net

volumes:
  mysql_data:
  redis_data:
  kie_maven_repo:
  decision_logs:
  prometheus_data:
  grafana_data:

networks:
  counteruav-net:
    driver: bridge
```

启动所有服务:

```bash
# 拉取基础镜像
docker compose pull

# 构建决策引擎镜像
docker compose build decision-api

# 启动全部服务
docker compose up -d

# 查看启动状态
docker compose ps

# 查看所有服务日志
docker compose logs -f
```

#### 2.1.6 验证服务健康状态

```bash
# 1. 验证MySQL
docker exec counteruav-mysql mysqladmin ping -h localhost -u root -p${MYSQL_ROOT_PASSWORD}
# 预期: mysqld is alive

# 2. 验证Redis
docker exec counteruav-redis redis-cli -a ${REDIS_PASSWORD} ping
# 预期: PONG

# 3. 验证KIE Server
curl -u ${KIE_SERVER_USER}:${KIE_SERVER_PASSWORD} \
  http://localhost:8080/kie-server/services/rest/server/containers
# 预期: JSON格式的容器列表

# 4. 验证决策API
curl http://localhost:8000/health
# 预期: {"status": "healthy", "version": "1.0.0", "uptime": "..."}

# 5. 验证API功能
curl -X POST http://localhost:8000/api/v1/threat/assess \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your-jwt-token>" \
  -d '{
    "drone_id": "test-001",
    "type": "consumer_small",
    "position": {"lat": 30.5, "lon": 120.5, "alt": 100},
    "speed": 12.0,
    "heading": 180.0,
    "frequency_band": "2.4GHz"
  }'
```

#### 2.1.7 初始化数据库

```bash
# 数据库表结构和初始数据由 docker-entrypoint-initdb.d 自动执行
# 如需手动初始化:

# 导入基础表结构
docker exec -i counteruav-mysql mysql -u${MYSQL_USER} -p${MYSQL_PASSWORD} ${MYSQL_DATABASE} \
  < sql/schema.sql

# 导入初始数据 (无人机类型库、场景模板等)
docker exec -i counteruav-mysql mysql -u${MYSQL_USER} -p${MYSQL_PASSWORD} ${MYSQL_DATABASE} \
  < sql/init_data.sql

# 导入地理围栏数据
docker exec -i counteruav-mysql mysql -u${MYSQL_USER} -p${MYSQL_PASSWORD} ${MYSQL_DATABASE} \
  < sql/geofence_data.sql
```

### 2.2 手动部署

#### 2.2.1 Python虚拟环境设置

```bash
# 安装Python 3.10+ (如未安装)
sudo add-apt-repository ppa:deadsnakes/ppa -y
sudo apt-get update
sudo apt-get install -y python3.10 python3.10-venv python3.10-dev

# 创建虚拟环境
cd /opt/counteruav/counteruav-decision-agent
python3.10 -m venv venv
source venv/bin/activate

# 升级pip
pip install --upgrade pip setuptools wheel
```

#### 2.2.2 依赖安装

```bash
# 安装Python依赖
pip install -r requirements.txt

# requirements.txt 核心依赖包括:
# fastapi==0.104.1
# uvicorn[standard]==0.24.0
# sqlalchemy==2.0.23
# pymysql==1.1.0
# redis==5.0.1
# httpx==0.25.2
# numpy==1.26.2
# scipy==1.11.4
# faiss-cpu==1.7.4  (或 faiss-gpu==1.7.4)
# sentence-transformers==2.2.2
# httpx==0.25.2
# pydantic==2.5.2
# python-jose[cryptography]==3.3.0
# passlib[bcrypt]==1.7.4
# python-multipart==0.0.6
# prometheus-client==0.19.0
# structlog==23.2.0
# geopy==2.4.1
# shapely==2.0.2
```

#### 2.2.3 MySQL数据库初始化

```bash
# 安装MySQL 8.0
sudo apt-get install -y mysql-server-8.0

# 安全初始化
sudo mysql_secure_installation

# 创建数据库和用户
sudo mysql -u root -p <<EOF
CREATE DATABASE IF NOT EXISTS counteruav
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

CREATE USER IF NOT EXISTS 'counteruav_admin'@'localhost'
  IDENTIFIED BY '<强密码>';

GRANT ALL PRIVILEGES ON counteruav.* TO 'counteruav_admin'@'localhost';
FLUSH PRIVILEGES;
EOF

# 导入表结构
mysql -u counteruav_admin -p counteruav < sql/schema.sql

# 导入初始数据
mysql -u counteruav_admin -p counteruav < sql/init_data.sql
```

#### 2.2.4 FAISS索引构建

```bash
# 激活虚拟环境
source venv/bin/activate

# 构建知识库FAISS索引
# 将knowledge-base下的所有JSON转换为向量并建立索引
python scripts/build_faiss_index.py \
  --input knowledge-base/ \
  --output knowledge-base/faiss_index/ \
  --model BAAI/bge-small-zh-v1.5

# 验证索引
python scripts/verify_faiss_index.py --index knowledge-base/faiss_index/
```

#### 2.2.5 服务启动顺序

```bash
# 1. 先启动基础设施
sudo systemctl start mysql
sudo systemctl start redis-server  # 如使用Redis

# 2. 启动KIE Server (需要JDK 17)
cd /opt/counteruav/kie-server
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
./bin/standalone.sh -c standalone-full.xml -b 0.0.0.0 &

# 3. 等待KIE Server就绪
until curl -s -u ${KIE_USER}:${KIE_PASSWORD} \
  http://localhost:8080/kie-server/services/rest/server/containers > /dev/null; do
  echo "等待KIE Server就绪..."
  sleep 5
done

# 4. 启动决策引擎API
cd /opt/counteruav/counteruav-decision-agent
source venv/bin/activate
uvicorn src.api.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --workers 4 \
  --log-level info \
  --access-log

# 5. 启动态势显示前端 (可选)
cd /opt/counteruav/frontend
npm run build
# 将build目录部署到Nginx
```

#### 2.2.6 验证

```bash
# 健康检查
curl http://localhost:8000/health

# API文档
curl http://localhost:8000/docs  # Swagger UI
curl http://localhost:8000/redoc # ReDoc

# 提交测试评估
curl -X POST http://localhost:8000/api/v1/threat/assess \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $(curl -s -X POST http://localhost:8000/api/v1/auth/login \
    -H 'Content-Type: application/json' \
    -d '{"username":"admin","password":"admin123"}')" \
  -d @tests/data/sample_drone_detection.json
```

---

## 第三章 配置指南

### 3.1 数据库配置

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `MYSQL_HOST` | string | localhost | MySQL服务器地址 |
| `MYSQL_PORT` | int | 3306 | MySQL端口 |
| `MYSQL_DATABASE` | string | counteruav | 数据库名称 |
| `MYSQL_USER` | string | - | 数据库用户 |
| `MYSQL_PASSWORD` | string | - | 数据库密码 |
| `MYSQL_POOL_SIZE` | int | 20 | 连接池大小，建议=CPU核数×2 |
| `MYSQL_POOL_RECYCLE` | int | 3600 | 连接回收时间(秒) |
| `MYSQL_POOL_PRE_PING` | bool | true | 连接前验证可用性 |
| `MYSQL_ECHO_SQL` | bool | false | 调试模式输出SQL (仅开发环境) |

MySQL连接池调优:

```python
# 根据并发量调整
# 低并发 (<50 req/s): pool_size=10
# 中并发 (50-200 req/s): pool_size=20
# 高并发 (>200 req/s): pool_size=40, 需相应增加MySQL max_connections
```

### 3.2 规则引擎配置

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `KIE_SERVER_URL` | string | - | KIE Server REST API完整地址 |
| `KIE_SERVER_USER` | string | - | KIE Server认证用户 |
| `KIE_SERVER_PASSWORD` | string | - | KIE Server认证密码 |
| `KIE_CONTAINER_ID` | string | counteruav-rules | Drools规则容器ID |
| `DROOLS_SESSION_POOL_SIZE` | int | 10 | KieSession对象池大小 |
| `DROOLS_RULE_RELOAD_INTERVAL` | int | 300 | 规则热加载检查间隔(秒) |
| `DROOLS_FIREALL_LIMIT` | int | 100 | 单次fireAllRules最大触发数 |
| `DROOLS_EVENT_EXPIRY` | int | 60 | CEP事件过期时间(秒) |

KIE Server session配置相关内容在 `config/rules.properties`:

```properties
# Drools运行时属性
drools.maxThreads=8
drools.sessionPoolSize=10
drools.clockType=realtime
drools.eventProcessingMode=stream
drools.knowledgeBaseCache=true
```

### 3.3 LLM代理配置

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `LLM_API_ENDPOINT` | string | - | LLM API完整端点地址 |
| `LLM_API_KEY` | string | - | API认证密钥 |
| `LLM_MODEL_NAME` | string | claude-sonnet-4 | 使用的模型名称 |
| `LLM_MAX_TOKENS` | int | 4096 | 最大生成令牌数 |
| `LLM_TEMPERATURE` | float | 0.3 | 温度参数 (0=确定性, 1=创造性) |
| `LLM_TIMEOUT` | int | 30 | 请求超时时间(秒) |
| `LLM_MAX_RETRIES` | int | 3 | 失败重试次数 |
| `LLM_CACHE_TTL` | int | 300 | 相似请求结果缓存时间(秒) |
| `LLM_OFFLINE_FALLBACK` | bool | true | 离线降级模式开关 |
| `LOCAL_LLM_ENDPOINT` | string | - | 本地LLM备选地址 |
| `LOCAL_LLM_MODEL` | string | qwen2.5:32b | 本地备选模型名称 |

LLM Prompt模板配置路径: `config/prompts/`

```
config/prompts/
├── system_prompt.yaml        # 系统提示词
├── threat_analysis.yaml      # 威胁分析提示词模板
├── strategy_recommendation.yaml  # 策略推荐提示词模板
├── anomaly_analysis.yaml     # 异常分析提示词模板
└── debrief_summary.yaml      # 战报总结提示词模板
```

### 3.4 传感器配置

传感器配置文件: `config/sensors.yaml`

```yaml
sensors:
  radars:
    - id: radar-01
      name: "X波段相控阵雷达-01"
      type: phased_array_x
      ip: 192.168.10.101
      port: 8001
      protocol: tcp_json
      location:
        lat: 30.5123
        lon: 120.5678
        alt: 50.0
      params:
        max_range_m: 5000
        min_range_m: 50
        az_range_deg: 360
        el_range_deg: -10~60
        update_rate_hz: 10

  rf_detectors:
    - id: rfdet-01
      name: "全频段RF探测-01"
      type: wideband_spectrum
      ip: 192.168.10.201
      port: 9001
      protocol: tcp_json
      location:
        lat: 30.5120
        lon: 120.5670
        alt: 45.0
      params:
        freq_range_mhz: [70, 6000]
        sensitivity_dbm: -90
        scan_bandwidth_mhz: 40

  cameras:
    - id: cam-01
      name: "光电转台-01"
      type: eo_ir_ptz
      rtsp_url: rtsp://192.168.10.301:554/stream1
      location:
        lat: 30.5125
        lon: 120.5680
        alt: 52.0
      params:
        resolution: [1920, 1080]
        fps: 30
        ir_available: true
        max_zoom: 30x

  acoustic:
    - id: aco-01
      name: "声学阵列-01"
      type: mic_array_8ch
      ip: 192.168.10.401
      port: 10001
      protocol: tcp_json
      location:
        lat: 30.5122
        lon: 120.5675
        alt: 10.0
      params:
        channels: 8
        sample_rate_hz: 48000
        freq_range_hz: [50, 8000]
```

### 3.5 反制设备配置

配置文件: `config/countermeasures.yaml`

```yaml
countermeasures:
  jammers:
    - id: jam-2400-01
      name: "2.4GHz定向干扰器-01"
      type: directional_jammer
      ip: 192.168.20.101
      port: 7001
      protocol: tcp_json
      location:
        lat: 30.5100
        lon: 120.5650
        alt: 48.0
      params:
        freq_bands: ["2400-2483MHz"]
        max_power_w: 100
        antenna_gain_dbi: 15
        beam_width_deg: 30
        response_time_ms: 200

    - id: jam-5800-01
      name: "5.8GHz定向干扰器-01"
      type: directional_jammer
      ip: 192.168.20.102
      port: 7001
      protocol: tcp_json
      location:
        lat: 30.5100
        lon: 120.5660
        alt: 48.0
      params:
        freq_bands: ["5725-5850MHz"]
        max_power_w: 100
        antenna_gain_dbi: 15
        beam_width_deg: 30
        response_time_ms: 200

  spoofers:
    - id: spf-01
      name: "GNSS导航欺骗器-01"
      type: gnss_spoofer
      ip: 192.168.20.201
      port: 7002
      protocol: tcp_json
      location:
        lat: 30.5110
        lon: 120.5660
        alt: 50.0
      params:
        supported_constellations: ["GPS_L1", "GLONASS_L1", "BeiDou_B1"]
        max_power_dbm: 10
        coverage_range_km: 10
        spoof_modes: ["navigation", "geofence", "forced_landing"]
        acquisition_time_s: 30

  lasers:
    - id: las-01
      name: "光纤激光反制设备-01"
      type: fiber_laser
      ip: 192.168.20.301
      port: 7003
      protocol: tcp_json
      location:
        lat: 30.5105
        lon: 120.5655
        alt: 55.0
      params:
        power_kw: 30
        wavelength_nm: 1070
        divergence_mrad: 0.5
        max_range_m: 3000
        beam_quality_m2: 1.5
        cooldown_s: 10

  kinetic:
    - id: net-01
      name: "网枪捕捉器-01"
      type: net_launcher
      ip: 192.168.20.401
      port: 7004
      protocol: tcp_json
      location:
        lat: 30.5100
        lon: 120.5640
        alt: 45.0
      params:
        effective_range_m: 150
        net_size_m: [3, 3]
        reload_time_s: 30
        projectile_speed_ms: 50
```

### 3.6 地理围栏配置

配置文件: `config/geofences.yaml`

```yaml
geofences:
  restricted_zones:
    - id: rz-airport-01
      name: "xxx国际机场净空区"
      type: airport
      severity: critical
      geometry:
        type: "Polygon"
        coordinates: [[[120.50, 30.50], [120.55, 30.50], [120.55, 30.55], [120.50, 30.55], [120.50, 30.50]]]
      altitude_limit_m: 120
      effective_time: "24/7"

    - id: rz-military-01
      name: "xxx军事禁区"
      type: military
      severity: critical
      geometry:
        type: "Circle"
        center: [120.60, 30.60]
        radius_m: 5000
      altitude_limit_m: 0
      effective_time: "24/7"

  alert_zones:
    - id: az-vip-01
      name: "xxx行政中心警戒区"
      type: government
      severity: high
      geometry:
        type: "Polygon"
        coordinates: [[[120.52, 30.52], [120.53, 30.52], [120.53, 30.53], [120.52, 30.53], [120.52, 30.52]]]
      altitude_limit_m: 150
      effective_time: "08:00-20:00"

  safe_zones:
    - id: sz-training-01
      name: "反无人机训练场"
      type: training_area
      geometry:
        type: "Circle"
        center: [120.70, 30.70]
        radius_m: 3000
      note: "允许测试用无人机飞行"
```

### 3.7 告警配置

配置文件: `config/alerts.yaml`

```yaml
alerts:
  levels:
    - level: INFO
      description: "信息提示"
      color: blue
      sound: none
      auto_acknowledge_s: 0

    - level: WARNING
      description: "预警"
      color: yellow
      sound: beep_2s
      auto_acknowledge_s: 30

    - level: CRITICAL
      description: "严重告警"
      color: red
      sound: siren
      auto_acknowledge_s: 0
      require_confirmation: true

    - level: EMERGENCY
      description: "紧急告警"
      color: red_flash
      sound: siren_continuous
      auto_acknowledge_s: 0
      require_confirmation: true
      escalation_timeout_s: 10

  notification_channels:
    - type: web_ui
      enabled: true
    - type: websocket
      enabled: true
    - type: syslog
      enabled: true
      host: 192.168.1.100
      port: 514
    - type: sms
      enabled: false
      provider: aliyun
      phones: ["+86-138xxxx1234"]
    - type: wechat_work
      enabled: true
      webhook_url: "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx"

  escalation_policy:
    - after_s: 10
      action: "重复告警"
    - after_s: 30
      action: "升级通知 (值班组长)"
    - after_s: 60
      action: "升级通知 (指挥长)"
    - after_s: 120
      action: "升级通知 (值班领导)"
```

### 3.8 日志配置

配置文件: `config/logging.yaml`

```yaml
logging:
  level: INFO  # DEBUG | INFO | WARNING | ERROR
  format: json  # json | text
  output:
    - type: console
      enabled: true
    - type: file
      enabled: true
      path: /app/logs/decision-agent.log
      max_size_mb: 100
      backup_count: 10
      rotation: daily
      retention_days: 30
    - type: syslog
      enabled: false
      host: 192.168.1.100
      port: 514
      protocol: udp
      facility: local0

  modules:
    engine:
      level: INFO
    agent:
      level: DEBUG
    api:
      level: INFO
    utils:
      level: WARNING
```

---

## 第四章 规则管理

### 4.1 规则生命周期

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│ Proposed │───>│ Testing  │───>│ Approved │───>│ Active   │───>│ Deprecated│
│  (提议)  │    │  (测试)  │    │  (批准)  │    │  (生效)  │    │  (废弃)  │
└──────────┘    └──────────┘    └──────────┘    └──────────┘    └──────────┘
      │              │               │               │               │
      │              │               │               │               │
      └──────────────┴───────────────┴───────────────┴───────┬───────┘
                                                              │
                                                         ┌────▼─────┐
                                                         │ Archived │
                                                         │  (归档)  │
                                                         └──────────┘
```

| 阶段 | 说明 | 操作权限 | 存储位置 |
|------|------|---------|---------|
| Proposed | 新规则草案，分析师创建 | 规则分析师 | `rules/drafts/` |
| Testing | 在仿真环境验证 | 规则分析师 | `rules/testing/` |
| Approved | 通过审核，待上线 | 规则审核员 | `rules/approved/` |
| Active | 生产环境生效 | 系统管理员 | `rules/l2_tactical/` 或 `rules/l3_strategic/` |
| Deprecated | 标记废弃，保留回滚能力 | 系统管理员 | `rules/deprecated/` |
| Archived | 长期归档 | 系统管理员 | `rules/archived/` |

### 4.2 如何添加新规则

#### 4.2.1 添加L2 Drools规则

**步骤1**: 定义规则需求

```
规则名称: THREAT-006
用途: 蜂群数量威胁评估 (swarm数量越多威胁越高)
触发条件: 检测到同区域目标数 >= 5
执行动作: 每个目标威胁等级+1 (上限5)
```

**步骤2**: 编写规则文件 `rules/l2_tactical/swarm_threat.drl`

```java
package com.counteruav.rules.tactical

import com.counteruav.facts.DroneFact
import com.counteruav.facts.ThreatAssessmentFact
import com.counteruav.facts.SwarmDetectionEvent

rule "THREAT-006: 蜂群数量威胁评估"
    agenda-group "threat-assessment"
    salience 88
    when
        $swarm: SwarmDetectionEvent(count >= 5, region != null)
        $drone: DroneFact(region == $swarm.region)
        $threat: ThreatAssessmentFact(droneId == $drone.id, level < 5)
    then
        int newLevel = Math.min($threat.getLevel() + 1, 5);
        $threat.setLevel(newLevel);
        $threat.addModificationReason("THREAT-006: 蜂群数量" + $swarm.getCount() + ", 威胁升级至" + newLevel);
        update($threat);
        logger.info("THREAT-006 fired: drone={}, swarm_count={}, new_level={}",
            $drone.getId(), $swarm.getCount(), newLevel);
end
```

**步骤3**: 创建测试用例 `tests/test_threat_006.py`

```python
def test_swarm_threat_escalation():
    """测试THREAT-006: 蜂群威胁评估"""
    # 插入SwarmDetectionEvent(count=5)
    # 插入同一区域的DroneFact
    # 执行规则
    # 验证ThreatAssessmentFact.level 增加了1
    pass
```

**步骤4**: 部署并验证

```bash
# 放置规则文件
cp rules/l2_tactical/swarm_threat.drl rules/testing/

# 运行测试套件
pytest tests/test_threat_006.py -v

# 测试通过后，提交审批
git add rules/l2_tactical/swarm_threat.drl tests/test_threat_006.py
git commit -m "feat: add THREAT-006 swarm threat escalation rule"
git push origin feature/threat-006
```

**步骤5**: 更新规则目录文档 `docs/rule_catalog.md`

### 4.3 如何修改现有规则

修改现有规则的变更控制流程:

```
1. 提出变更请求 (Change Request)
   ├── 描述变更原因和预期效果
   ├── 影响分析 (哪些规则和策略受此变更影响)
   └── 回滚方案

2. 规则分析师评估
   ├── 技术可行性评估
   ├── 与现有规则的兼容性检查
   └── 性能影响预估

3. 仿真环境验证
   ├── 单元测试
   ├── 回归测试 (所有相关规则)
   ├── 仿真场景测试 (历史数据重放)
   └── 性能基准测试

4. A/B测试 (生产环境灰度)
   ├── 10%流量 → 新规则
   ├── 90%流量 → 旧规则
   ├── 比较决策差异 (24小时)
   └── 统计分析

5. 全量发布或回滚
   ├── A/B测试通过 → 全量发布
   └── A/B测试失败 → 回滚至旧版本
```

修改示例: 调整THREAT-004的接近距离阈值

```bash
# 1. 签出变更分支
git checkout -b change/threat-004-distance-threshold

# 2. 修改规则文件
vim rules/l2_tactical/asset_proximity.drl
# 修改: VIP距离阈值从500m改为300m

# 3. 更新测试
vim tests/test_threat_004.py
# 更新预期值以匹配新阈值

# 4. 运行测试
pytest tests/ -k "threat_004" -v

# 5. 提交
git commit -m "change: THREAT-004 VIP distance threshold 500m→300m"
```

### 4.4 规则测试流程

#### 4.4.1 仿真模式

```bash
# 启动仿真模式 (不连接真实传感器和反制设备)
python scripts/run_simulation.py \
  --scenario scenarios/drone_swarm_attack.yaml \
  --rules-dir rules/ \
  --output results/simulation_$(date +%Y%m%d_%H%M%S).json
```

#### 4.4.2 历史数据重放 (Dry Run)

```bash
# 使用历史传感器数据重放，测试规则变更效果
python scripts/replay_historical.py \
  --start "2026-07-01 00:00:00" \
  --end "2026-07-07 00:00:00" \
  --rules-version v1.1.0-test \
  --compare-version v1.0.0 \
  --output results/replay_comparison.csv
```

#### 4.4.3 A/B测试配置

```yaml
# config/ab_test.yaml
ab_test:
  enabled: true
  experiment_id: "threat-004-threshold-test"
  control:
    rules_version: "v1.0.0"
    traffic_percent: 90
  treatment:
    rules_version: "v1.1.0-test"
    traffic_percent: 10
  metrics:
    - decision_latency_ms
    - false_positive_rate
    - operator_override_rate
    - cm_success_rate
  duration_hours: 24
```

### 4.5 规则回滚流程

```bash
# 紧急回滚方案

# 1. 立即切换到上一个已知良好版本
docker exec counteruav-api python scripts/rollback_rules.py \
  --version v1.0.0 \
  --reason "THREAT-004误报率过高"

# 2. 或者通过API回滚
curl -X POST http://localhost:8000/api/v1/admin/rules/rollback \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <admin-token>" \
  -d '{
    "target_version": "v1.0.0",
    "reason": "THREAT-004 夜间误报率从2%升至15%",
    "force": false
  }'

# 3. 验证回滚后状态
curl http://localhost:8000/api/v1/admin/rules/status
# 预期输出包含: "active_version": "v1.0.0"
```

### 4.6 规则版本管理

```bash
# 规则版本管理使用Git标签
git tag -a rules-v1.1.0 -m "规则库v1.1.0: 新增THREAT-006蜂群威胁规则, 调整THREAT-004距离阈值"
git push origin rules-v1.1.0

# 查询规则版本历史
git tag -l 'rules-v*' --sort=-v:refname | head -10

# 比较两个版本的规则差异
git diff rules-v1.0.0 rules-v1.1.0 -- rules/
```

规则版本在数据库中的记录:

```sql
-- 查询规则版本历史
SELECT version, release_date, description, status
FROM rule_versions
ORDER BY release_date DESC;

-- 查询特定规则的变更历史
SELECT rule_id, version, change_type, old_value, new_value, changed_by, changed_at
FROM rule_change_log
WHERE rule_id = 'THREAT-004'
ORDER BY changed_at DESC;
```

---

## 第五章 LLM智能体管理

### 5.1 LLM Agent触发条件

LLM Agent按以下条件被触发调用:

| 触发条件编号 | 条件描述 | 触发阈值 | 默认行为 |
|-------------|---------|---------|---------|
| L4-TRIG-01 | 策略置信度过低 | L3策略输出置信度 < 0.7 | 调用LLM生成备选方案 |
| L4-TRIG-02 | 多策略冲突 | 2+个L3策略同时匹配 | 调用LLM仲裁选择 |
| L4-TRIG-03 | 场景未覆盖 | 威胁/环境组合在覆盖矩阵中为GAP | 调用LLM分析推理 |
| L4-TRIG-04 | 操作员主动请求 | 操作员点击"AI辅助分析" | 调用LLM生成建议 |
| L4-TRIG-05 | 历史成功率低 | 相似案例历史成功率 < 50% | 调用LLM优化方案 |
| L4-TRIG-06 | 目标行为异常 | 目标行为偏离已知模式 > 2σ | 调用LLM意图分析 |

### 5.2 提示词管理

#### 5.2.1 系统提示词

文件: `config/prompts/system_prompt.yaml`

```yaml
system_prompt:
  role: |
    你是一位经验丰富的反无人机作战指挥官AI助手。
    你的职责是在规则引擎无法完全覆盖的场景下，提供专业、安全、合规的辅助决策建议。

  expertise:
    - 无人机型号识别与性能分析
    - 电子对抗战术与电磁频谱管理
    - 防空作战与拦截几何
    - 风险评估与交战规则

  constraints:
    - 始终优先考虑人身安全和民用航空安全
    - 严格遵守交战规则 (ROE)
    - 在不确定时建议“进一步确认”而非盲目行动
    - 所有建议需附带置信度评估和风险提示
    - 不得建议违反国际法和国内法规的行动

  output_format:
    threat_analysis: "威胁分析结论"
    recommended_action: "建议行动方案"
    alternatives: ["备选方案1", "备选方案2"]
    risk_assessment: "风险评估 (高/中/低)"
    confidence: 0.0-1.0
    reasoning: "推理过程简述"
    caveats: ["注意事项1", "注意事项2"]
```

#### 5.2.2 模板变量

LLM请求中使用的模板变量:

| 变量名 | 类型 | 说明 | 示例值 |
|--------|------|------|--------|
| `{{drone_type}}` | string | 无人机类型中文名 | "小型消费级四旋翼" |
| `{{drone_count}}` | int | 目标数量 | 5 |
| `{{threat_level}}` | int | 当前威胁等级(1-5) | 3 |
| `{{distance_m}}` | float | 目标距离(米) | 1250.5 |
| `{{speed_ms}}` | float | 目标速度(m/s) | 18.3 |
| `{{altitude_m}}` | float | 目标高度(米) | 120.0 |
| `{{environment}}` | string | 环境类型 | "城市核心" |
| `{{zone_type}}` | string | 所在区域类型 | "民用航空净空区" |
| `{{payload}}` | string | 检测到的载荷 | "未知小型容器" |
| `{{frequency_band}}` | string | 工作频段 | "2.4GHz + 5.8GHz" |
| `{{available_cm}}` | list | 可用反制设备列表 | ["Jammer-2400", "Spoofer-01"] |
| `{{matched_strategies}}` | list | 匹配的L3策略 | ["STRAT-004", "STRAT-007"] |
| `{{l2_recommendation}}` | string | L2层推荐方案摘要 | "RF干扰+GNSS欺骗组合" |

### 5.3 模型切换

```bash
# 1. 修改环境变量
# 切换到云端API
export LLM_API_ENDPOINT="https://api.anthropic.com/v1/messages"
export LLM_MODEL_NAME="claude-opus-4-20250514"
export LLM_API_KEY="sk-ant-xxxx"

# 或切换到本地部署模型
export LLM_API_ENDPOINT="http://localhost:11434/v1/chat/completions"
export LLM_MODEL_NAME="qwen2.5:32b"
export LLM_API_KEY=""

# 2. 重启决策引擎
docker compose restart decision-api

# 3. 验证模型可用性
curl http://localhost:8000/api/v1/admin/llm/test
```

模型对比:

| 模型 | 推理能力 | 响应延迟 | 成本 | 适用场景 |
|------|---------|---------|------|---------|
| Claude Opus 4 | 最强 | 2-5s | 高 | 复杂多域威胁分析 |
| Claude Sonnet 4 | 强 | 1-3s | 中 | 日常使用推荐 |
| GPT-4o | 强 | 1-3s | 中 | 备选方案 |
| Qwen2.5 32B (本地) | 良好 | 0.5-2s | 低 | 离线/保密场景 |
| Qwen2.5 7B (本地) | 一般 | 0.2-1s | 低 | 快速分析, 低优先级场景 |

### 5.4 LLM调用监控

#### 5.4.1 监控指标

| 指标 | 说明 | 告警阈值 |
|------|------|---------|
| `llm_request_total` | LLM总请求数 | - |
| `llm_request_duration_seconds` | 请求延迟分布 (p50/p95/p99) | p99 > 10s |
| `llm_token_usage_total` | Token总消耗 | - |
| `llm_cost_total_usd` | 累计美元成本 | 日成本 > $50 |
| `llm_error_rate` | 错误率 | > 5% |
| `llm_cache_hit_rate` | 缓存命中率 | < 30% |
| `llm_hallucination_flag_count` | 幻觉标记次数 | > 2次/天 |
| `llm_fallback_activation_count` | 降级模式激活次数 | > 5次/天 |

#### 5.4.2 Prometheus查询示例

```promql
# LLM请求延迟P95
histogram_quantile(0.95, rate(llm_request_duration_seconds_bucket[5m]))

# LLM错误率
rate(llm_request_errors_total[5m]) / rate(llm_request_total[5m]) * 100

# Token消耗速率 (每分钟)
rate(llm_token_usage_total[1m])

# 缓存命中率
llm_cache_hits / (llm_cache_hits + llm_cache_misses) * 100
```

### 5.5 常见问题排查

#### 问题1: LLM请求超时

```bash
# 现象: 日志中出现 "LLM request timeout after 30s"
# 原因: 网络延迟、模型服务负载高、请求Token数过大

# 排查步骤:
# 1. 检查网络连通性
curl -w "\n%{time_total}s\n" -o /dev/null -s ${LLM_API_ENDPOINT}

# 2. 检查当前Token使用量 (从监控面板查看)
# 如果单次请求Token > 8000, 考虑减少上下文

# 3. 临时增加超时
export LLM_TIMEOUT=60
docker compose restart decision-api

# 4. 如果是云端API问题, 切换到本地模型
export LLM_API_ENDPOINT="http://localhost:11434/v1/chat/completions"
export LLM_MODEL_NAME="qwen2.5:32b"
```

#### 问题2: API速率限制

```bash
# 现象: 日志中出现 "429 Too Many Requests" 或 "Rate limit exceeded"
# 解决方案:

# 1. 启用请求缓存 (减少重复请求)
export LLM_CACHE_TTL=600  # 缓存10分钟

# 2. 调整请求合并策略
# 编辑 config/llm_config.yaml
llm:
  request_batching:
    enabled: true
    max_batch_size: 5
    max_wait_ms: 500

# 3. 增加LLM调用触发阈值 (减少不必要调用)
export LLM_TRIGGER_CONFIDENCE_THRESHOLD=0.5  # 仅置信度<0.5才调用
```

#### 问题3: 模型幻觉/不合理建议

```bash
# 现象: LLM建议实施明显不合理的反制措施
# 原因: 温度参数过高、提示词不够约束、上下文不足

# 解决方案:
# 1. 降低Temperature
export LLM_TEMPERATURE=0.1

# 2. 增强系统提示词约束
# 编辑 config/prompts/system_prompt.yaml
# 在constraints中添加硬性约束

# 3. 添加后处理校验
# 对所有LLM输出进行规则校验:
#   - 不允许在禁反制区域建议硬杀伤
#   - 不允许对有人航空器反制
#   - 不允许建议超出设备能力的方案
# 此功能在 src/agent/post_process.py 中实现

# 4. 标记问题输出用于反馈学习
curl -X POST http://localhost:8000/api/v1/admin/llm/feedback \
  -H "Content-Type: application/json" \
  -d '{
    "request_id": "llm-req-20260713-001234",
    "feedback": "inappropriate",
    "reason": "建议在机场附近使用激光",
    "operator": "commander_wang"
  }'
```

### 5.6 离线降级模式

当LLM服务不可用时，系统自动进入降级模式:

| 降级行为 | 正常模式 | 降级模式 |
|---------|---------|---------|
| 威胁分析 | LLM辅助分析未知目标 | 仅依赖L1+L2规则 |
| 策略推荐 | LLM优化策略参数 | 使用L3默认参数 |
| 异常检测 | LLM分析异常行为模式 | 统计阈值检测 |
| 战报总结 | LLM生成自然语言战报 | 模板化数据报告 |
| 响应延迟 | 500-3000ms (含LLM) | 50-200ms (纯规则) |

降级模式日志:

```
2026-07-13 10:23:45 WARNING [agent.llm_client] LLM API unreachable after 3 retries. 
  Switching to OFFLINE_FALLBACK mode. Reason: ConnectionError to api.anthropic.com
2026-07-13 10:23:45 INFO [agent.fallback] Fallback mode activated. Using deterministic rules only.
2026-07-13 10:24:12 INFO [agent.fallback] Successfully processed 5 events in fallback mode. 
  Latency: avg=85ms, max=120ms.
2026-07-13 10:25:30 INFO [agent.llm_client] LLM API connectivity restored. 
  Switching back to NORMAL mode.
```

---

## 第六章 备份与恢复

### 6.1 数据库备份

#### 6.1.1 自动备份脚本

```bash
#!/bin/bash
# 文件: scripts/backup_mysql.sh
# 用途: 每日MySQL数据库自动备份

BACKUP_DIR="/backup/mysql"
RETENTION_DAYS=30
DB_NAME="counteruav"
DB_USER="counteruav_admin"
DB_PASS="${MYSQL_PASSWORD}"  # 从环境变量读取
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

mkdir -p ${BACKUP_DIR}

# 完整备份
mysqldump -u ${DB_USER} -p${DB_PASS} \
  --single-transaction \
  --routines \
  --triggers \
  --events \
  --hex-blob \
  ${DB_NAME} | gzip > ${BACKUP_DIR}/${DB_NAME}_full_${TIMESTAMP}.sql.gz

# 仅备份关键表 (决策日志可能很大)
mysqldump -u ${DB_USER} -p${DB_PASS} \
  --single-transaction \
  --no-data \
  ${DB_NAME} | gzip > ${BACKUP_DIR}/${DB_NAME}_schema_${TIMESTAMP}.sql.gz

# 清理旧备份
find ${BACKUP_DIR} -name "*.sql.gz" -mtime +${RETENTION_DAYS} -delete

echo "Backup completed: ${BACKUP_DIR}/${DB_NAME}_full_${TIMESTAMP}.sql.gz"
```

#### 6.1.2 Cron定时任务

```bash
# 编辑crontab
crontab -e

# 添加每日凌晨3点的备份任务
0 3 * * * /opt/counteruav/counteruav-decision-agent/scripts/backup_mysql.sh >> /var/log/backup.log 2>&1

# 添加每周日凌晨4点的异地备份 (同步到远程NAS)
0 4 * * 0 rsync -avz /backup/mysql/ backup@nas-server:/backup/counteruav/mysql/ >> /var/log/backup_sync.log 2>&1
```

### 6.2 规则库备份

规则库使用Git进行版本管理，自动备份策略：

```bash
# 规则库Git仓库位于 rules/ 目录

# 自动提交规则变更 (通过CI/CD或定时任务)
cd /opt/counteruav/counteruav-decision-agent
git add rules/ config/
git commit -m "auto: daily rules backup $(date +%Y-%m-%d)"
git push origin main

# 规则库导出为归档包
tar -czf /backup/rules/rules_$(date +%Y%m%d).tar.gz rules/ config/rules.properties
```

### 6.3 知识库备份

```bash
#!/bin/bash
# 文件: scripts/backup_knowledge_base.sh

BACKUP_DIR="/backup/knowledge_base"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

mkdir -p ${BACKUP_DIR}

# 备份知识库JSON文件和FAISS索引
tar -czf ${BACKUP_DIR}/knowledge_base_${TIMESTAMP}.tar.gz \
  knowledge-base/*.json \
  knowledge-base/terrain_db/ \
  knowledge-base/em_environment/ \
  knowledge-base/site_templates/ \
  knowledge-base/faiss_index/

echo "Knowledge base backup completed."
```

### 6.4 完整系统恢复流程

```bash
#!/bin/bash
# 文件: scripts/restore_full_system.sh
# 用途: 从备份完整恢复系统

set -e

RESTORE_DATE=$1  # 恢复日期, 如 20260713

if [ -z "$RESTORE_DATE" ]; then
    echo "Usage: $0 <YYYYMMDD>"
    exit 1
fi

BACKUP_DIR="/backup"
echo "=== 开始系统恢复 (日期: ${RESTORE_DATE}) ==="

# Step 1: 停止服务
echo "[1/6] 停止正在运行的服务..."
docker compose down
sleep 5

# Step 2: 恢复数据库
echo "[2/6] 恢复MySQL数据库..."
LATEST_DB_BACKUP=$(ls -t ${BACKUP_DIR}/mysql/counteruav_full_${RESTORE_DATE}*.sql.gz 2>/dev/null | head -1)
if [ -z "$LATEST_DB_BACKUP" ]; then
    echo "错误: 未找到${RESTORE_DATE}的数据库备份"
    exit 1
fi

# 删除现有数据库并重建
docker compose up -d mysql
sleep 10
docker exec counteruav-mysql mysql -u root -p${MYSQL_ROOT_PASSWORD} \
  -e "DROP DATABASE IF EXISTS counteruav; CREATE DATABASE counteruav CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

# 恢复数据
zcat ${LATEST_DB_BACKUP} | docker exec -i counteruav-mysql \
  mysql -u root -p${MYSQL_ROOT_PASSWORD} counteruav

echo "数据库恢复完成: ${LATEST_DB_BACKUP}"

# Step 3: 恢复规则库
echo "[3/6] 恢复规则库..."
cd /opt/counteruav/counteruav-decision-agent
git checkout tags/rules-v1.0.0  # 或其他指定版本

# Step 4: 恢复知识库
echo "[4/6] 恢复知识库..."
LATEST_KB_BACKUP=$(ls -t ${BACKUP_DIR}/knowledge_base/knowledge_base_${RESTORE_DATE}*.tar.gz 2>/dev/null | head -1)
if [ -n "$LATEST_KB_BACKUP" ]; then
    rm -rf knowledge-base/
    tar -xzf ${LATEST_KB_BACKUP}
    echo "知识库恢复完成: ${LATEST_KB_BACKUP}"
else
    echo "警告: 未找到知识库备份, 将重建FAISS索引"
    python scripts/build_faiss_index.py --input knowledge-base/ --output knowledge-base/faiss_index/
fi

# Step 5: 重建FAISS索引
echo "[5/6] 重建FAISS向量索引..."
python scripts/build_faiss_index.py \
  --input knowledge-base/ \
  --output knowledge-base/faiss_index/ \
  --model BAAI/bge-small-zh-v1.5

# Step 6: 启动服务
echo "[6/6] 启动全部服务..."
docker compose up -d
sleep 30

# 验证
echo "=== 系统恢复验证 ==="
curl -s http://localhost:8000/health | python -m json.tool
echo "=== 系统恢复完成 ==="
```

### 6.5 灾难恢复演练计划

| 演练内容 | 频率 | 参与人员 | 预期RTO | 预期RPO |
|---------|------|---------|---------|---------|
| 数据库故障恢复 | 每季度 | 系统管理员 | < 30分钟 | < 5分钟 |
| 规则库回滚 | 每季度 | 规则管理员 | < 10分钟 | < 1分钟 |
| LLM服务不可用降级 | 每月 | 全体操作员 | < 1分钟 | 不适用 |
| 传感器全断 | 每半年 | 全体操作员 | < 15分钟 | < 10秒 |
| 全系统故障恢复 | 每年 | 全体人员 | < 2小时 | < 15分钟 |

---

## 第七章 监控与告警

### 7.1 系统健康指标

| 指标类别 | 指标名称 | 类型 | 正常范围 | 告警阈值 |
|---------|---------|------|---------|---------|
| 响应延迟 | `decision_latency_ms` | Histogram | < 200ms | > 500ms (WARN), > 1000ms (CRIT) |
| 响应延迟 | `llm_latency_ms` | Histogram | < 3000ms | > 5000ms (WARN), > 10000ms (CRIT) |
| 规则引擎 | `rule_fire_rate` | Gauge | 0~500/s | > 800/s (WARN) |
| 规则引擎 | `rule_conflict_rate` | Gauge | < 5% | > 10% (WARN) |
| 设备状态 | `device_online_ratio` | Gauge | > 95% | < 90% (WARN), < 80% (CRIT) |
| 设备状态 | `jammer_active_count` | Gauge | - | - |
| API服务 | `api_request_rate` | Counter | - | > 500/s (WARN) |
| API服务 | `api_error_rate` | Gauge | < 1% | > 5% (WARN), > 10% (CRIT) |
| 数据库 | `db_connection_pool_usage` | Gauge | < 70% | > 85% (WARN), > 95% (CRIT) |
| 数据库 | `db_query_latency_ms` | Histogram | < 50ms | > 200ms (WARN) |
| 系统资源 | `cpu_usage_percent` | Gauge | < 60% | > 80% (WARN), > 90% (CRIT) |
| 系统资源 | `memory_usage_percent` | Gauge | < 70% | > 85% (WARN), > 95% (CRIT) |
| 系统资源 | `disk_usage_percent` | Gauge | < 70% | > 85% (WARN), > 95% (CRIT) |

### 7.2 Prometheus Metrics端点

系统在 `http://localhost:8000/metrics` 暴露Prometheus格式指标:

```
# HELP decision_latency_ms Decision-making latency in milliseconds
# TYPE decision_latency_ms histogram
decision_latency_ms_bucket{le="50"} 1234
decision_latency_ms_bucket{le="100"} 5678
decision_latency_ms_bucket{le="200"} 8901
decision_latency_ms_bucket{le="500"} 9234
decision_latency_ms_bucket{le="1000"} 9456
decision_latency_ms_bucket{le="+Inf"} 9500
decision_latency_ms_sum 1234567
decision_latency_ms_count 9500

# HELP rule_fire_total Total rule fire count by rule_id
# TYPE rule_fire_total counter
rule_fire_total{rule_id="THREAT-001"} 23456
rule_fire_total{rule_id="THREAT-002"} 1234
rule_fire_total{rule_id="CM-001"} 5678

# HELP device_online_status Device online status (1=online, 0=offline)
# TYPE device_online_status gauge
device_online_status{device_id="jam-2400-01", device_type="jammer"} 1
device_online_status{device_id="spf-01", device_type="spoofer"} 1
device_online_status{device_id="las-01", device_type="laser"} 0

# HELP threat_level_distribution Distribution of threat levels
# TYPE threat_level_distribution gauge
threat_level_distribution{level="1"} 3
threat_level_distribution{level="2"} 1
threat_level_distribution{level="3"} 0
threat_level_distribution{level="4"} 0
threat_level_distribution{level="5"} 0

# HELP llm_request_duration_seconds LLM request duration
# TYPE llm_request_duration_seconds histogram
llm_request_duration_seconds_bucket{le="0.5"} 100
llm_request_duration_seconds_bucket{le="1.0"} 250
llm_request_duration_seconds_bucket{le="2.0"} 400
llm_request_duration_seconds_bucket{le="5.0"} 480
llm_request_duration_seconds_bucket{le="10.0"} 495
llm_request_duration_seconds_bucket{le="+Inf"} 500

# HELP countermeasure_execution_total Countermeasure execution count
# TYPE countermeasure_execution_total counter
countermeasure_execution_total{cm_type="rf_jamming", result="success"} 89
countermeasure_execution_total{cm_type="rf_jamming", result="failed"} 5
countermeasure_execution_total{cm_type="gnss_spoofing", result="success"} 34
countermeasure_execution_total{cm_type="gnss_spoofing", result="failed"} 2
countermeasure_execution_total{cm_type="laser", result="success"} 12
countermeasure_execution_total{cm_type="laser", result="failed"} 1
```

### 7.3 Grafana Dashboard推荐面板

#### 面板1: 系统概览 (System Overview)

```
┌─────────────────────────────────────────────────────────────────┐
│  系统状态: ● 正常    |  版本: 1.0.0  |  运行时间: 15d 3h 22m    │
├──────────────┬──────────────┬──────────────┬───────────────────┤
│   决策延迟    │  规则触发率   │  设备在线率   │   LLM调用次数     │
│   85ms       │  42/min      │  94% ▲       │   12/day          │
│   (P95:120ms)│  (峰值:89)   │  (3/32离线)  │   ($1.20/天)      │
├──────────────┴──────────────┴──────────────┴───────────────────┤
│                                                                  │
│  决策延迟趋势 [折线图]                                            │
│  120ms ┤              ╭─╮                                       │
│  100ms ┤    ╭──╮  ╭──╯  ╰─╮                                     │
│   80ms ┤╭──╯  ╰──╯        ╰──                                    │
│        └──────────────────────────────                           │
│                                                                  │
│  威胁等级分布 [柱状图]        设备在线状态 [状态表]                │
│  L1 ████████░░ 7             Jammer-2400  ● 在线                │
│  L2 ████░░░░░░ 3             Jammer-5800  ● 在线                │
│  L3 ██░░░░░░░░ 1             Spoofer-01   ● 在线                │
│  L4 ░░░░░░░░░░ 0             Laser-01     ◌ 离线                │
│  L5 ░░░░░░░░░░ 0             NetLauncher  ● 在线                │
└──────────────────────────────────────────────────────────────────┘
```

#### 面板2: LLM智能体监控 (LLM Agent Dashboard)

```
┌─────────────────────────────────────────────────────────────────┐
│  LLM服务状态: ● 正常 (Claude Sonnet 4)  |  本地备选: ● 待命     │
├──────────────┬──────────────┬──────────────┬───────────────────┤
│  今日请求     │  缓存命中率   │  平均延迟     │   今日成本        │
│  23 次       │  45%         │  1.8s        │   $1.34          │
│  (限流0次)   │  (目标>30%)  │  (P95:4.2s)  │   (预估:$35/月)  │
├──────────────┴──────────────┴──────────────┴───────────────────┤
│  LLM请求延迟分布 [热力图]                                        │
│  5s+  ░░░░░░░░░░░░                                              │
│  2-5s ░░░░████░░░░                                              │
│  1-2s ░░██████░░░░                                              │
│  0-1s ████████████                                              │
│                                                                  │
│  Token消耗趋势 [折线图]          触发原因分布 [饼图]              │
│  50k ┤        ╭╮                 L4-TRIG-01 ████████░ 52%      │
│  40k ┤   ╭╮  ╭╯╰╮                L4-TRIG-02 ██░░░░░░░ 13%      │
│  30k ┤╭──╯╰──╯  ╰─               L4-TRIG-03 █░░░░░░░░  8%      │
│      └────────────────            L4-TRIG-04 ███░░░░░░ 18%      │
│                                    L4-TRIG-05 █░░░░░░░░  5%      │
│                                    L4-TRIG-06 █░░░░░░░░  4%      │
└──────────────────────────────────────────────────────────────────┘
```

### 7.4 关键告警阈值

Prometheus告警规则文件: `config/prometheus_alerts.yml`

```yaml
groups:
  - name: counteruav_critical
    rules:
      - alert: HighDecisionLatency
        expr: histogram_quantile(0.95, rate(decision_latency_ms_bucket[5m])) > 500
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "决策延迟P95超过500ms"
          description: "当前P95延迟: {{ $value }}ms, 可能影响实时响应能力"

      - alert: DeviceOffline
        expr: device_online_status == 0
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "反制设备 {{ $labels.device_id }} 离线"
          description: "设备 {{ $labels.device_id }} ({{ $labels.device_type }}) 超过2分钟无心跳"

      - alert: LLMServiceDown
        expr: llm_request_errors_total - llm_request_errors_total offset 10m > 5
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "LLM服务异常"
          description: "最近10分钟LLM请求错误数: {{ $value }}, 已切换降级模式"

      - alert: HighThreatMultipleTargets
        expr: threat_level_distribution{level="4"} + threat_level_distribution{level="5"} > 3
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "多目标高威胁报警"
          description: "当前有 {{ $value }} 个4级及以上威胁目标, 建议立即响应"

      - alert: DatabaseConnectionPoolHigh
        expr: db_connection_pool_usage > 85
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "数据库连接池使用率超过85%"
          description: "当前使用率: {{ $value }}%, 可能需要扩大连接池"
```

### 7.5 日志分析指引

#### 日志级别含义

| 级别 | 含义 | 示例场景 |
|------|------|---------|
| DEBUG | 详细调试信息 | 规则匹配细节、变量绑定、LLM原始请求/响应 |
| INFO | 正常运行信息 | 规则触发、决策输出、设备状态变更 |
| WARNING | 潜在问题 | 规则冲突、设备超时、LLM重试、接近阈值 |
| ERROR | 错误情况 | 规则引擎异常、数据库连接失败、设备无响应 |
| CRITICAL | 严重故障 | 系统崩溃、数据丢失、安全事件 |

#### 日志查询示例

```bash
# 查看最近的LLM调用日志
docker exec counteruav-api grep "LLM" /app/logs/decision-agent.log | tail -20

# 查看特定规则的触发历史
docker exec counteruav-api grep "THREAT-002.*fired" /app/logs/decision-agent.log | tail -20

# 查看设备故障日志
docker exec counteruav-api grep "offline\|disconnected\|timeout" /app/logs/decision-agent.log

# 查看系统错误
docker exec counteruav-api grep "ERROR\|CRITICAL" /app/logs/decision-agent.log

# 按时间范围查询 (需安装 jq 处理 JSON格式日志)
docker exec counteruav-api cat /app/logs/decision-agent.log | \
  jq 'select(.timestamp >= "2026-07-13T10:00:00" and .timestamp < "2026-07-13T11:00:00")'
```

---

## 第八章 故障排查

### 8.1 常见问题FAQ

#### FAQ-01: 决策引擎响应缓慢 (>500ms)

**现象**: API响应时间从正常100ms升至500ms+

**排查**:
```bash
# 检查系统资源
docker stats counteruav-api --no-stream

# 检查数据库连接池
curl http://localhost:8000/metrics | grep db_connection_pool_usage

# 检查规则引擎状态
curl -u ${KIE_SERVER_USER}:${KIE_SERVER_PASSWORD} \
  http://localhost:8080/kie-server/services/rest/server/containers/${KIE_CONTAINER_ID}
```

**解决**: 增加Drools session池大小 (`DROOLS_SESSION_POOL_SIZE=20`) 或增加API workers (`--workers 8`)

#### FAQ-02: MySQL连接被拒绝

**现象**: 日志中出现 "(2003, Can't connect to MySQL server)"

**解决**:
```bash
# 检查MySQL容器状态
docker compose ps mysql

# 检查MySQL日志
docker compose logs mysql | tail -50

# 如果在手动部署模式下，检查MySQL服务
sudo systemctl status mysql

# 检查防火墙
sudo ufw status | grep 3306
```

#### FAQ-03: KIE Server无法加载规则容器

**现象**: 日志显示 "Container counteruav-rules not found"

**解决**:
```bash
# 检查KIE Server状态
curl -u ${KIE_SERVER_USER}:${KIE_SERVER_PASSWORD} \
  http://localhost:8080/kie-server/services/rest/server/containers

# 重新部署规则容器
curl -X PUT -u ${KIE_SERVER_USER}:${KIE_SERVER_PASSWORD} \
  -H "Content-Type: application/xml" \
  -d @rules/kjars/counteruav-rules-1.0.0.jar \
  http://localhost:8080/kie-server/services/rest/server/containers/counteruav-rules-1.0.0
```

#### FAQ-04: 反制设备无法连接

**现象**: 日志中 "Device jam-2400-01 unreachable"

**排查**:
```bash
# 网络连通性测试
ping -c 4 192.168.20.101
nc -zv 192.168.20.101 7001

# 直接测试设备API
curl -m 5 http://192.168.20.101:7001/status

# 检查防火墙规则
sudo iptables -L -n | grep 192.168.20
```

**解决**: 检查物理连接、IP配置、防火墙规则、设备电源

#### FAQ-05: FAISS索引加载失败

**现象**: 日志中 "Failed to load FAISS index from knowledge-base/faiss_index/"

**解决**:
```bash
# 重建索引
python scripts/build_faiss_index.py \
  --input knowledge-base/ \
  --output knowledge-base/faiss_index/ \
  --model BAAI/bge-small-zh-v1.5 \
  --force

# 如使用GPU版FAISS遇到CUDA错误
pip uninstall faiss-gpu
pip install faiss-cpu  # 降级到CPU版本
```

#### FAQ-06: LLM返回不合理建议

**现象**: LLM建议使用激光在机场附近或建议攻击己方无人机

**解决**: 不需要重启，问题在LLM输出后处理阶段被拦截:
```bash
# 检查拦截日志
docker exec counteruav-api grep "BLOCKED_POST_PROCESS" /app/logs/decision-agent.log

# 调整后处理严格度
# 编辑 config/agent_config.yaml
post_process:
  strict_mode: true  # 更严格的后处理校验
  block_on:
    - "激光.*机场"
    - "硬杀伤.*城市"
    - "反制.*己方"
```

#### FAQ-07: 系统磁盘空间不足

**现象**: 日志中出现磁盘写入错误

**解决**:
```bash
# 检查磁盘使用
df -h

# 清理旧日志 (>30天)
find /app/logs/ -name "*.log" -mtime +30 -delete

# 清理旧的Docker镜像
docker system prune -a --filter "until=168h"

# 清理旧的数据库备份
find /backup/mysql/ -name "*.sql.gz" -mtime +90 -delete

# 压缩决策日志表
mysql -u counteruav_admin -p counteruav -e \
  "OPTIMIZE TABLE decision_logs;"
```

#### FAQ-08: WebSocket连接频繁断开

**现象**: 前端态势显示页面频繁显示"连接已断开"

**解决**:
```bash
# 检查Nginx代理超时设置
# 在Nginx配置中增加:
proxy_read_timeout 300s;
proxy_send_timeout 300s;

# 检查客户端心跳间隔
# 前端应每30秒发送心跳
```

#### FAQ-09: 规则冲突导致死循环

**现象**: 日志中同一规则不断触发，CPU占用100%

**解决**:
```bash
# 设置规则触发上限
export DROOLS_FIREALL_LIMIT=50

# 检查是否有两个规则互相触发对方条件更新
# 在设计规则时，使用 no-loop true 或 lock-on-active true
```

#### FAQ-10: 部署后服务无法启动

**现象**: `docker compose up -d`后容器反复重启

**排查**:
```bash
# 查看失败容器的详细日志
docker compose logs decision-api | tail -100

# 检查所有必需的环境变量是否已设置
docker compose config | grep -E "MYSQL_|LLM_|KIE_"

# 验证配置文件格式
python -c "import yaml; yaml.safe_load(open('config/default.yaml'))"

# 手动尝试启动以获取详细错误
docker compose run --rm decision-api python -c "from src.engine.rule_engine import RuleEngine; print('OK')"
```

#### FAQ-11: 传感器数据格式不兼容

**现象**: 某型号传感器数据解析失败

**解决**:
```bash
# 添加传感器适配器
# 在 src/utils/sensor_adapters.py 中新增适配器类
# 参考已有适配器实现, 例如RadarAdapter, RfDetectorAdapter

# 配置传感器类型映射
# 编辑 config/sensors.yaml 中的 protocol 字段
```

#### FAQ-12: 系统时钟不同步导致事件乱序

**现象**: CEP (复杂事件处理) 规则未能正确触发时序依赖

**解决**:
```bash
# 确保所有节点使用NTP同步
sudo apt-get install -y chrony
sudo systemctl enable chrony
sudo systemctl start chrony
chronyc tracking

# 检查系统时钟偏差
chronyc sources -v

# 在Docker容器中继承宿主机时钟
# docker-compose.yml 中确保没有配置与宿主机不同的时区
```

### 8.2 诊断命令集合

```bash
# === 系统状态快速检查 ===

# 1. 所有服务状态
docker compose ps

# 2. API健康检查
curl -s http://localhost:8000/health | python -m json.tool

# 3. 系统指标快照
curl -s http://localhost:8000/metrics | grep -E "^[a-z].*{" | sort

# 4. 数据库连接测试
docker exec counteruav-mysql mysqladmin ping -h localhost -u ${MYSQL_USER} -p${MYSQL_PASSWORD}

# 5. KIE Server容器列表
curl -s -u ${KIE_SERVER_USER}:${KIE_SERVER_PASSWORD} \
  http://localhost:8080/kie-server/services/rest/server/containers | python -m json.tool

# 6. Redis连接测试
docker exec counteruav-redis redis-cli -a ${REDIS_PASSWORD} ping

# 7. 资源使用
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}"

# 8. 网络连通性 (传感器和反制设备)
for ip in 192.168.10.101 192.168.10.201 192.168.10.301 \
          192.168.20.101 192.168.20.201 192.168.20.301; do
  ping -c 1 -W 2 $ip > /dev/null 2>&1 && echo "$ip: OK" || echo "$ip: FAIL"
done

# 9. 磁盘使用
df -h / /backup /app/logs

# 10. 最近错误日志
docker compose logs --tail=50 decision-api | grep -E "ERROR|CRITICAL"
```

### 8.3 日志位置说明

| 日志类型 | 位置 | 说明 |
|---------|------|------|
| 决策引擎日志 | `/app/logs/decision-agent.log` | 主应用日志 |
| 规则触发日志 | `/app/logs/rule_fire.log` | 规则触发详细记录 |
| LLM调用日志 | `/app/logs/llm_calls.log` | LLM请求/响应完整记录 |
| 设备通信日志 | `/app/logs/device_comms.log` | 与反制设备的通信记录 |
| API访问日志 | `/app/logs/api_access.log` | HTTP请求日志 |
| KIE Server日志 | Docker日志 `counteruav-kie` | Drools规则引擎日志 |
| MySQL日志 | Docker日志 `counteruav-mysql` | 数据库日志 |
| Docker守护日志 | `journalctl -u docker` | 容器运行时日志 |

### 8.4 联系支持

当遇到无法解决的问题时，请收集以下信息后联系技术支持:

```bash
# 一键收集诊断信息包
python scripts/diagnostic_collector.py --output /tmp/counteruav_diag_$(date +%Y%m%d_%H%M%S).tar.gz

# 诊断信息包含:
# - 系统配置 (脱敏后的 .env 和 YAML 配置)
# - 最近1小时日志
# - 当前Metrics快照
# - Docker版本和容器状态
# - 网络连通性测试结果
# - 系统资源使用快照
```

| 支持渠道 | 联系方式 | 响应时间 |
|---------|---------|---------|
| 内部工单 | tickets.internal.company.com/counteruav | 4小时 (工作日) |
| 值班电话 | +86-xxx-xxxx-xxxx | 30分钟 (7×24) |
| 紧急热线 | +86-xxx-xxxx-xxxx | 15分钟 (7×24) |
| 邮件 | counteruav-support@company.com | 8小时 (工作日) |

---

> **文档维护**: 系统工程组 | **审核**: 技术总监 | **批准**: 项目总师
