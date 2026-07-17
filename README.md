# 反无人机辅助决策系统 (Counter-UAV Decision Agent)

> 版本: 1.0.0 | 最后更新: 2026-07-13 | 密级: 内部
>
> **混合架构**: 四层规则引擎 (L1物理→L2战术→L3策略→L4元规则) + LLM智能体协同
> **输出方式**: 建议方案生成 -> 操作员确认 -> 反制执行

---

## 项目概述

反无人机辅助决策系统是一款面向反无人机作战指挥的多层规则引擎与LLM智能体混合决策系统。系统通过四层规则架构实现从原始传感器数据到最终反制决策的全链路智能化处理，具备多传感器融合、自主威胁评估、智能反制决策、多设备协同调度、策略自适应及人机协同等核心能力。

### 核心特点

- **四层混合架构**: L1物理层(Python) + L2战术层(Drools) + L3策略层(JSON) + L4元规则层(LLM)，从确定性计算到自适应推理逐层递进
- **多传感器融合**: 雷达、RF探测、光电、声学等多源异构传感器数据统一融合处理
- **智能威胁评估**: 基于无人机类型、运动特征、有效载荷、环境上下文的5级动态威胁评估
- **多手段反制**: 射频干扰、GNSS欺骗、激光毁伤、动能拦截四类反制手段的智能选择与协同
- **场景自适应**: 8类作战场景策略模板 + LLM驱动的未覆盖场景自适应推理
- **人机协同**: 操作员在环确认、手动超控、AI辅助决策、策略推演
- **全程留痕**: 决策全过程可追溯，支持复盘分析、规则优化、反馈学习

### 能力指标

| 指标 | 值 |
|------|-----|
| 最大同时跟踪目标数 | 500+ |
| 单目标决策延迟 (P95) | < 200ms (规则) / < 3s (含LLM) |
| 规则总数 (含L1-L4) | 38 |
| 覆盖场景组合 | 150种 (5级威胁 x 6类机型 x 5类环境) |
| 场景覆盖率 | 98% (COVERED+PARTIAL) |
| LLM辅助覆盖率 | L4可在所有GAP场景介入 |
| 支持反制设备类型 | 4类 (干扰/欺骗/激光/动能) |
| 部署方式 | Docker Compose / 手动部署 |

---

## 架构图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              操作员控制台 (C2 Console)                        │
│                        态势显示 | 告警管理 | 手动超控 | AI对话                 │
└─────────────────────────────────────┬───────────────────────────────────────┘
                                      │ WebSocket + REST API
┌─────────────────────────────────────▼───────────────────────────────────────┐
│                          决策融合层 (Decision Fusion)                         │
│                   规则引擎输出 + LLM建议 -> 置信度评估 -> 最终决策              │
└──────────────┬─────────────────────────────────────────────┬────────────────┘
               │                                             │
    ┌──────────▼──────────┐                    ┌─────────────▼────────────────┐
    │    规则引擎层 (L1-L4) │                    │       LLM 智能体层            │
    │                      │                    │                              │
    │  L4: 元规则层 (LLM)  │<--- 触发 ---------│  Claude API / 本地大模型      │
    │  L3: 策略规则层(JSON)│                    │  提示词管理 | 缓存管理          │
    │  L2: 战术规则层(DRL) │                    │  降级模式 | 反馈学习           │
    │  L1: 物理规则层(PY)  │                    │                              │
    └──────────┬───────────┘                    └──────────────────────────────┘
               │
    ┌──────────▼──────────────────────────────────────────────────────────────┐
    │                          数据处理与知识库层                                │
    │                                                                          │
    │  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐        │
    │  │ 数据预处理  │  │ 目标关联    │  │ 轨迹管理    │  │ 特征提取    │        │
    │  └────────────┘  └────────────┘  └────────────┘  └────────────┘        │
    │                                                                          │
    │  ┌────────────────────────────────────────────────────────────────┐     │
    │  │              知识库 (Knowledge Base)                            │     │
    │  │  无人机特征库 | 场景模板库 | 电磁环境库 | 地形数据库 | FAISS索引  │     │
    │  └────────────────────────────────────────────────────────────────┘     │
    └──────────────────────────────────┬───────────────────────────────────────┘
                                       │
    ┌──────────────────────────────────▼───────────────────────────────────────┐
    │                            传感器接入层                                    │
    │                                                                          │
    │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐                │
    │  │ 雷达系统  │  │ RF探测器  │  │ 光电转台  │  │ 声学阵列  │   ...          │
    │  │ (X/P/L)  │  │ (70M-6G)│  │ (EO/IR)  │  │ (8通道)  │                │
    │  └──────────┘  └──────────┘  └──────────┘  └──────────┘                │
    └──────────────────────────────────────────────────────────────────────────┘
                                       │
    ┌──────────────────────────────────▼───────────────────────────────────────┐
    │                            反制执行层                                      │
    │                                                                          │
    │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐                │
    │  │ 射频干扰器 │  │GNSS欺骗器│  │ 激光设备  │  │ 动能拦截器 │               │
    │  │ 2.4/5.8G│  │ GPS/BD   │  │ 光纤激光  │  │ 网枪/捕捉 │               │
    │  └──────────┘  └──────────┘  └──────────┘  └──────────┘                │
    └──────────────────────────────────────────────────────────────────────────┘
```

---

## 技术栈

| 组件 | 技术 | 说明 |
|------|------|------|
| 规则引擎 | Drools 8.x / KIE Server 7.73 | L2战术规则执行、冲突解决、规则热加载 |
| LLM Agent | Claude API / 本地大模型 (Qwen2.5) | L4元规则层自适应推理、异常场景分析 |
| 数据库 | MySQL 8.0 | 知识库、规则版本、决策日志、设备管理 |
| 向量检索 | FAISS + BGE-small-zh-v1.5 | 相似案例检索、知识库语义搜索 |
| 缓存/队列 | Redis 7.0 (可选) | 会话状态、消息队列、结果缓存 |
| 后端框架 | Python 3.10+ / FastAPI | REST API、WebSocket推送、中间件 |
| 前端 | React 18 + TypeScript | 态势显示、操作控制台 |
| 消息推送 | WebSocket | 实时态势、告警推送 |
| 容器化 | Docker + Docker Compose | 一键部署、环境隔离 |
| 监控 | Prometheus + Grafana | 系统健康、指标采集、告警 |
| 日志 | structlog + syslog | 结构化日志、集中收集 |

---

## 快速开始

### 前置要求

- Docker 24.0+
- Docker Compose 2.20+
- 可用磁盘空间 >= 100GB
- 内存 >= 16GB (推荐32GB)
- (可选) NVIDIA GPU + nvidia-docker (用于LLM本地推理加速)

### Docker Compose 一键部署

```bash
# 1. 克隆仓库
git clone git@internal-git.company.com:security/counteruav-decision-agent.git
cd counteruav-decision-agent
git checkout v1.0.0

# 2. 配置环境变量
cp .env.example .env
vim .env  # 修改数据库密码、LLM API Key等关键配置

# 3. 启动全部服务
docker compose up -d

# 4. 验证服务状态
docker compose ps
# 预期: 所有服务状态为 Up / healthy

# 5. 健康检查
curl http://localhost:8000/health
# 预期: {"status": "healthy", "version": "1.0.0"}

# 6. 访问API文档
# 浏览器打开: http://<服务器IP>:8000/docs
```

### 手动部署

```bash
# 1. 设置Python虚拟环境
python3.10 -m venv venv && source venv/bin/activate

# 2. 安装依赖
pip install -r requirements.txt

# 3. 初始化数据库
mysql -u root -p < sql/schema.sql
mysql -u root -p counteruav < sql/init_data.sql

# 4. 构建FAISS索引
python scripts/build_faiss_index.py \
  --input knowledge-base/ \
  --output knowledge-base/faiss_index/ \
  --model BAAI/bge-small-zh-v1.5

# 5. 启动服务 (确保MySQL和KIE Server已运行)
uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --workers 4

# 6. 验证
curl http://localhost:8000/health
```

---

## 目录结构说明

```
counteruav-decision-agent/
├── README.md                           # 项目说明 (本文件)
├── docker-compose.yml                  # Docker Compose编排文件
├── Dockerfile                          # 决策引擎Docker镜像构建文件
├── requirements.txt                    # Python依赖清单
├── .env.example                        # 环境变量模板
├── Makefile                            # 常用操作快捷命令
│
├── config/                             # 配置文件目录
│   ├── default.yaml                    # 系统默认配置
│   ├── rules.properties                # Drools规则引擎属性
│   ├── sensors.yaml                    # 传感器配置
│   ├── countermeasures.yaml            # 反制设备配置
│   ├── geofences.yaml                  # 地理围栏配置
│   ├── alerts.yaml                     # 告警配置
│   ├── logging.yaml                    # 日志配置
│   ├── llm_config.yaml                 # LLM智能体配置
│   ├── prometheus.yml                  # Prometheus采集配置
│   ├── prometheus_alerts.yml           # Prometheus告警规则
│   ├── grafana-dashboards/             # Grafana仪表盘JSON
│   └── prompts/                        # LLM提示词模板
│       ├── system_prompt.yaml
│       ├── threat_analysis.yaml
│       ├── strategy_recommendation.yaml
│       ├── anomaly_analysis.yaml
│       └── debrief_summary.yaml
│
├── knowledge-base/                     # 知识库目录
│   ├── drone_types.json                # 无人机特征库 (200+型号)
│   ├── scenario_templates.json         # 场景模板库
│   ├── frequency_bands.json            # 频段分配与特征
│   ├── countermeasure_effects.json     # 反制效果数据
│   ├── historical_cases.json           # 历史案例库
│   ├── terrain_db/                     # 地形数据库
│   │   ├── site_templates.json         # 阵地模板
│   │   └── terrain_types.yaml          # 地形分类定义
│   ├── em_environment/                 # 电磁环境库
│   │   ├── common_interference.json    # 常见干扰源特征
│   │   └── spectrum_allocation.json    # 频谱分配
│   └── faiss_index/                    # FAISS向量索引
│       ├── drone_types.index
│       ├── scenarios.index
│       └── historical_cases.index
│
├── rules/                              # 规则库目录
│   ├── l1_physics/                     # L1: 物理公式 (Python)
│   │   ├── __init__.py
│   │   ├── kinematics.py               # PHY-001~003
│   │   ├── rf_propagation.py           # PHY-004~006
│   │   ├── optics.py                   # PHY-007~008
│   │   ├── radar.py                    # PHY-009
│   │   ├── interception.py             # PHY-010
│   │   ├── acoustics.py                # PHY-011
│   │   └── power.py                    # PHY-012
│   ├── l2_tactical/                    # L2: 战术规则 (.drl)
│   │   ├── threat_assessment.drl       # THREAT-001~005
│   │   ├── countermeasure_select.drl   # CM-001~004
│   │   ├── coordination.drl            # CM-005~006
│   │   └── roe_constraints.drl         # ROE-001
│   ├── l3_strategic/                   # L3: 策略规则 (.json)
│   │   ├── strat_001_standard.json
│   │   ├── strat_002_swarm.json
│   │   ├── strat_003_night.json
│   │   ├── strat_004_urban.json
│   │   ├── strat_005_border.json
│   │   ├── strat_006_vip.json
│   │   ├── strat_007_em.json
│   │   └── strat_008_hybrid.json
│   ├── l4_meta/                        # L4: 元规则 (Prompt + 触发逻辑)
│   │   ├── trigger_conditions.yaml     # 6个触发条件定义
│   │   ├── meta_prompts.py             # 动态提示词构建
│   │   └── post_process.py             # LLM输出后处理与校核
│   ├── drafts/                         # 规则草案 (开发中)
│   ├── testing/                        # 测试中规则
│   ├── approved/                       # 已批准待上线
│   ├── deprecated/                     # 已废弃规则
│   └── archived/                       # 归档规则
│
├── sql/                                # 数据库脚本
│   ├── schema.sql                      # 表结构定义
│   ├── init_data.sql                   # 初始数据
│   ├── geofence_data.sql               # 地理围栏数据
│   └── migrations/                     # 版本迁移脚本
│
├── scripts/                            # 运维脚本
│   ├── backup_mysql.sh                 # 数据库备份
│   ├── backup_knowledge_base.sh        # 知识库备份
│   ├── restore_full_system.sh          # 全系统恢复
│   ├── build_faiss_index.py            # FAISS索引构建
│   ├── verify_faiss_index.py           # FAISS索引验证
│   ├── run_simulation.py               # 仿真运行
│   ├── replay_historical.py            # 历史数据重放
│   ├── rollback_rules.py               # 规则回滚
│   └── diagnostic_collector.py         # 诊断信息收集
│
├── src/                                # 源代码
│   ├── __init__.py
│   ├── api/                            # API服务模块
│   │   ├── __init__.py
│   │   ├── main.py                     # FastAPI应用入口
│   │   ├── dependencies.py             # 依赖注入
│   │   ├── routers/                    # 路由
│   │   │   ├── threat.py               # 威胁评估API
│   │   │   ├── countermeasure.py       # 反制措施API
│   │   │   ├── device.py               # 设备管理API
│   │   │   ├── strategy.py             # 策略API
│   │   │   ├── admin.py                # 管理API
│   │   │   └── websocket.py            # WebSocket端点
│   │   ├── middleware/                 # 中间件
│   │   │   ├── auth.py                 # JWT认证
│   │   │   ├── logging.py              # 请求日志
│   │   │   └── rate_limit.py           # 速率限制
│   │   └── schemas/                    # Pydantic数据模型
│   │       ├── threat.py
│   │       ├── countermeasure.py
│   │       ├── device.py
│   │       └── common.py
│   ├── engine/                         # 规则引擎模块
│   │   ├── __init__.py
│   │   ├── rule_engine.py              # 规则引擎主入口
│   │   ├── kie_client.py               # KIE Server客户端
│   │   ├── session_pool.py             # KieSession对象池
│   │   ├── fact_builder.py             # Drools Fact构建器
│   │   ├── conflict_resolver.py        # 规则冲突解决
│   │   ├── l1_runner.py                # L1物理层调度
│   │   ├── l2_runner.py                # L2战术层调度
│   │   ├── l3_runner.py                # L3策略层调度
│   │   └── decision_fusion.py          # 决策融合 (规则+LLM)
│   ├── agent/                          # LLM智能体模块
│   │   ├── __init__.py
│   │   ├── llm_client.py               # LLM客户端 (Claude/本地)
│   │   ├── prompt_manager.py           # 提示词管理
│   │   ├── context_builder.py          # 上下文构建
│   │   ├── cache_manager.py            # 请求缓存
│   │   ├── trigger_engine.py           # L4触发条件引擎
│   │   ├── post_process.py             # 输出后处理校核
│   │   └── fallback.py                 # 离线降级逻辑
│   ├── knowledge/                      # 知识库模块
│   │   ├── __init__.py
│   │   ├── knowledge_base.py           # 知识库管理
│   │   ├── vector_store.py             # FAISS向量存储
│   │   ├── embedding.py                # 文本向量化
│   │   ├── drone_db.py                 # 无人机特征检索
│   │   ├── scenario_matcher.py         # 场景模板匹配
│   │   └── terrain_analyzer.py         # 地形分析
│   ├── data/                           # 数据持久化模块
│   │   ├── __init__.py
│   │   ├── database.py                 # 数据库连接池
│   │   ├── models/                     # SQLAlchemy ORM模型
│   │   │   ├── threat.py
│   │   │   ├── decision.py
│   │   │   ├── device.py
│   │   │   └── rule.py
│   │   ├── repositories/              # 数据访问层
│   │   │   ├── threat_repo.py
│   │   │   ├── decision_repo.py
│   │   │   └── rule_repo.py
│   │   └── redis_client.py            # Redis客户端
│   └── utils/                         # 工具模块
│       ├── __init__.py
│       ├── geo_utils.py               # 地理计算工具 (Haversine等)
│       ├── rf_utils.py                # 射频计算工具
│       ├── sensor_adapters.py         # 传感器数据适配器
│       ├── device_adapters.py         # 反制设备适配器
│       ├── alert_manager.py           # 告警管理
│       ├── logger.py                  # 日志工具
│       └── metrics.py                 # Prometheus指标
│
├── tests/                             # 测试目录
│   ├── unit/                          # 单元测试
│   │   ├── test_l1_physics.py
│   │   ├── test_l2_rules.py
│   │   ├── test_l3_strategies.py
│   │   ├── test_l4_agent.py
│   │   └── test_utils.py
│   ├── integration/                   # 集成测试
│   │   ├── test_rule_chain.py
│   │   ├── test_api.py
│   │   └── test_device_comms.py
│   ├── simulation/                    # 仿真测试
│   │   └── scenarios/
│   │       ├── single_drone_violation.yaml
│   │       ├── drone_swarm_attack.yaml
│   │       ├── night_intrusion.yaml
│   │       └── hybrid_threat.yaml
│   ├── data/                          # 测试数据
│   │   └── sample_drone_detection.json
│   └── conftest.py                    # Pytest fixtures
│
├── docs/                              # 文档
│   ├── rule_catalog.md                # 规则目录 (完整规则说明)
│   └── operations_manual.md           # 运维手册
│
└── frontend/                          # 前端 (React + TypeScript)
    ├── package.json
    ├── tsconfig.json
    ├── src/
    │   ├── App.tsx
    │   ├── components/
    │   ├── pages/
    │   ├── services/
    │   └── utils/
    └── public/
```

---

## 核心模块说明

### 1. 规则引擎模块 (`src/engine/`)

规则引擎是整个系统的核心决策组件，负责执行L1-L3层规则，输出反制建议。

**主要功能:**
- **L1物理层** (`l1_runner.py`): 执行12条物理公式计算 (距离、速度、链路预算、干扰距离、激光功率等)。全部为确定性Python函数，延迟<1ms。
- **L2战术层** (`l2_runner.py`): 通过KIE Server Client与Drools规则引擎交互，执行13条战术规则。管理KieSession对象池，支持规则热加载。
- **L3策略层** (`l3_runner.py`): 根据L2输出结果匹配对应的8个作战策略模板(JSON)，输出结构化的处置方案和时序。
- **决策融合** (`decision_fusion.py`): 综合规则引擎输出和LLM建议(如有)，计算置信度，生成最终可执行决策。

**关键特性:**
- KieSession对象池: 预创建10个session，支持高并发 (200+ req/s)
- 规则热加载: 每5分钟检查规则变更，自动重新部署
- 冲突解决: DRL salience + agenda-group 控制规则执行顺序
- 事件过期: CEP事件60秒自动过期，防止内存溢出

### 2. LLM智能体模块 (`src/agent/`)

LLM智能体在规则引擎覆盖不足时介入，提供自适应推理和策略优化。

**主要功能:**
- **触发引擎** (`trigger_engine.py`): 监控6个触发条件 (置信度过低、多策略冲突、场景未覆盖、操作员请求、历史成功率低、行为异常)，决定是否调用LLM。
- **上下文构建** (`context_builder.py`): 将传感器数据、规则引擎输出、知识库检索结果组装为结构化上下文，控制Token消耗。
- **提示词管理** (`prompt_manager.py`): 管理5类提示词模板 (系统提示、威胁分析、策略推荐、异常分析、战报总结)，支持变量替换。
- **输出后处理** (`post_process.py`): 对LLM输出进行规则化校核，拦截危险建议 (如在机场附近使用激光，反制己方无人机等)。
- **降级模式** (`fallback.py`): LLM不可用时自动切换至纯规则模式，保证核心功能可用。

**关键特性:**
- 多模型支持: Claude API (主) + 本地Qwen2.5 (备) + OpenAI兼容API
- 结果缓存: 相似请求 (余弦相似度>0.95) 复用结果，缓存TTL 5分钟
- 幻觉防控: 后处理强校核 + 操作员反馈标记 + 历史建议质量追踪
- 降级无缝: LLM不可用->纯规则模式，切换延迟<100ms

### 3. 知识库模块 (`src/knowledge/`)

知识库为规则引擎和LLM提供领域知识支撑。

**知识库内容:**

| 知识库 | 文件 | 条目数 | 用途 |
|--------|------|--------|------|
| 无人机特征库 | `drone_types.json` | 200+ | 型号识别、性能参数、频段特征 |
| 场景模板库 | `scenario_templates.json` | 8+ | L3策略匹配基准 |
| 频段数据库 | `frequency_bands.json` | 50+ | RF干扰频段匹配 |
| 电磁环境库 | `em_environment/` | 30+ | 常见干扰源、频谱分配 |
| 地形数据库 | `terrain_db/` | 20+ | 阵地模板、地形分类 |
| 历史案例库 | `historical_cases.json` | 500+ | 相似案例检索、反馈学习 |
| 反制效果库 | `countermeasure_effects.json` | 40+ | 各手段对不同机型的有效性数据 |

**检索方式:**
- FAISS向量索引: 语义相似度检索 (top-k)
- 结构化查询: 精确匹配型号/频段/场景ID
- 混合检索: 语义+结构化组合，提升召回率

### 4. 决策融合模块 (`src/engine/decision_fusion.py`)

决策融合是本系统的关键特色，负责将确定性规则输出与概率性LLM建议进行加权融合。

**融合策略:**

```
最终决策 = f(L2规则输出, L3策略模板, L4元规则建议, 操作员输入)

加权规则:
  - 确定场景 (覆盖矩阵=COVERED): 规则权重 0.9, LLM权重 0.1
  - 部分场景 (覆盖矩阵=PARTIAL): 规则权重 0.6, LLM权重 0.4
  - 未覆盖场景 (覆盖矩阵=GAP):   规则权重 0.3, LLM权重 0.7

置信度计算:
  confidence = w_rule * confidence_rule + w_llm * confidence_llm

操作员可随时超控，超控优先级最高
```

### 5. API服务模块 (`src/api/`)

提供REST API和WebSocket接口，供前端态势显示和外部系统集成。

**主要端点:**

| 端点 | 方法 | 说明 |
|------|------|------|
| `/health` | GET | 系统健康检查 |
| `/api/v1/threat/assess` | POST | 提交目标威胁评估请求 |
| `/api/v1/threat/batch` | POST | 批量威胁评估 (最多50个目标) |
| `/api/v1/countermeasure/recommend` | POST | 获取反制措施建议 |
| `/api/v1/countermeasure/execute` | POST | 执行反制措施 |
| `/api/v1/device/status` | GET | 查询设备状态 |
| `/api/v1/device/control` | POST | 设备控制指令 |
| `/api/v1/strategy/list` | GET | 查询可用策略列表 |
| `/api/v1/strategy/activate` | POST | 激活指定策略 |
| `/api/v1/admin/rules/reload` | POST | 热加载规则库 |
| `/api/v1/admin/llm/test` | GET | 测试LLM连接 |
| `/api/v1/decision/feedback` | POST | 提交操作员反馈 |
| `/ws/situation` | WebSocket | 态势数据实时推送 |

### 6. 数据持久化模块 (`src/data/`)

管理所有持久化数据的存储和检索。

**核心数据表:**

| 表名 | 说明 | 预估数据量 |
|------|------|-----------|
| `drone_detections` | 无人机探测记录 | 100万+/天 |
| `threat_assessments` | 威胁评估记录 | 50万+/天 |
| `countermeasure_decisions` | 反制决策记录 | 1万+/天 |
| `decision_logs` | 规则触发明细 | 500万+/天 |
| `device_status_history` | 设备状态历史 | 100万+/天 |
| `rule_versions` | 规则版本记录 | < 1000 |
| `rule_change_log` | 规则变更日志 | < 10000 |
| `llm_call_records` | LLM调用记录 | 1000+/天 |
| `operator_actions` | 操作员操作日志 | < 5000/天 |
| `alert_history` | 告警历史 | 5000+/天 |

---

## 规则库说明

### 四层规则架构

| 层级 | 类型 | 实现 | 数量 | 确定性 | 延迟 |
|------|------|------|------|--------|------|
| L1 | 物理公式 | Python函数 | 12条 | 100% | <1ms |
| L2 | 战术规则 | Drools .drl | 13条 | 100% | 5-50ms |
| L3 | 策略模板 | JSON配置 | 8条 | 确定性(模板) | 10-100ms |
| L4 | 元规则 | LLM Agent | 6个触发条件 | 概率性 | 500-3000ms |

### 规则覆盖矩阵摘要

系统覆盖了 5级威胁 x 6类无人机 x 5种环境 共150种场景组合:

| 覆盖状态 | 数量 | 占比 |
|---------|------|------|
| COVERED (完全覆盖) | 120 | 80% |
| PARTIAL (部分覆盖) | 27 | 18% |
| GAP (未覆盖) | 3 | 2% |

未覆盖场景 (GAP) 集中在: **F型穿越机 x T1城市核心 / T5特殊区域 / 中威胁城市环境**。这些场景通过L4元规则层自动介入处理。

详细规则说明参见: [docs/rule_catalog.md](docs/rule_catalog.md)

---

## 知识库说明

### 无人机特征库 (`knowledge-base/drone_types.json`)

包含200+种常见和军用无人机的详细特征，结构示例:

```json
{
  "drone_id": "DJI-Mavic3",
  "category": "consumer_small",
  "manufacturer": "DJI",
  "weight_g": 895,
  "max_speed_ms": 21,
  "max_altitude_m": 6000,
  "endurance_min": 46,
  "frequency_bands": ["2.4GHz", "5.8GHz"],
  "gnss_support": ["GPS", "GLONASS", "Galileo", "BeiDou"],
  "rcs_sqm": 0.01,
  "noise_db": 75,
  "typical_payload": "camera",
  "countermeasure_effectiveness": {
    "rf_jamming": "high",
    "gnss_spoofing": "medium",
    "laser": "high",
    "kinetic": "medium"
  }
}
```

### 场景模板库 (`knowledge-base/scenario_templates.json`)

定义8种标准作战场景及对应的策略参数 (STRAT-001~008)。

### 电磁环境库 (`knowledge-base/em_environment/`)

包含常见电磁干扰源特征 (通信基站、WiFi、微波链路等) 和频谱分配数据，用于电磁环境建模和干扰效果预测。

---

## 开发指南

### 环境搭建

```bash
# 1. 克隆仓库并创建虚拟环境
git clone git@internal-git.company.com:security/counteruav-decision-agent.git
cd counteruav-decision-agent
python3.10 -m venv venv && source venv/bin/activate

# 2. 安装开发依赖
pip install -r requirements.txt
pip install -r requirements-dev.txt  # 包含pytest, black, mypy等

# 3. 安装pre-commit hooks
pre-commit install

# 4. 启动开发数据库
docker compose -f docker-compose.dev.yml up -d mysql redis

# 5. 初始化测试数据
python scripts/setup_dev_env.py

# 6. 启动开发服务器 (热重载)
uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000
```

### 代码规范

| 方面 | 规范 |
|------|------|
| 代码风格 | Black (line-length=100) |
| 类型检查 | MyPy (strict mode) |
| 导入排序 | isort (Black profile) |
| 文档字符串 | Google style docstrings |
| 提交信息 | Conventional Commits |
| 分支命名 | `feat/`, `fix/`, `change/`, `docs/` |

```bash
# 格式化代码
black src/ tests/
isort src/ tests/

# 类型检查
mypy src/

# 运行lint
flake8 src/ tests/
```

### 测试指南

```bash
# 运行全部测试
pytest tests/ -v

# 运行特定模块测试
pytest tests/unit/test_l1_physics.py -v
pytest tests/unit/test_l2_rules.py -v

# 运行集成测试 (需要Docker服务运行)
pytest tests/integration/ -v --run-integration

# 运行仿真测试
python scripts/run_simulation.py --scenario tests/simulation/scenarios/single_drone.yaml

# 覆盖率报告
pytest tests/ --cov=src --cov-report=html

# 目标覆盖率: 行覆盖率 > 80%, 分支覆盖率 > 70%
```

### 贡献流程

```
1. 创建功能分支
   git checkout -b feat/my-new-rule

2. 开发 + 测试
   - 添加/修改规则代码
   - 编写单元测试
   - 运行全部现有测试确保无回归

3. 提交并推送
   git add .
   git commit -m "feat: description of change"
   git push origin feat/my-new-rule

4. 创建Pull Request
   - 填写PR模板: 变更描述、影响分析、测试结果
   - 指定审核人

5. 代码审核 -> CI全部通过 -> Squash merge to main
```

---

## 部署指南

### Docker部署 (生产环境)

详见 [docs/operations_manual.md](docs/operations_manual.md) 第二章。

生产环境部署检查清单:

- [ ] 所有密码已从默认值修改
- [ ] API JWT Secret已生成 (openssl rand -hex 64)
- [ ] HTTPS已配置 (通过Nginx反向代理)
- [ ] 防火墙规则已配置 (仅暴露8000/3000端口)
- [ ] 数据库备份计划已配置 (每日凌晨3点cron)
- [ ] 日志保留策略已设置 (30天)
- [ ] 监控告警已配置 (Prometheus + Grafana)
- [ ] 健康检查端点正常响应
- [ ] 应急预案已就绪

### 安全加固建议

```bash
# 1. 限制Docker容器权限
# docker-compose.yml 中添加:
services:
  decision-api:
    security_opt:
      - no-new-privileges:true
    read_only: true  # 除必要卷外只读

# 2. 使用Nginx反向代理 + HTTPS
# 3. 限制API速率: API_RATE_LIMIT=50
# 4. 定期安全扫描: docker scan counteruav-decision-agent:1.0.0
# 5. 审计日志: 确保操作员的所有操作都被记录到 operator_actions 表
```

---

## 系统特性

- **离线运行**: LLM支持本地推理，不需互联网连接
- **实时性**: 规则引擎 <200ms (P95)，LLM 限流保证不阻塞
- **可解释**: 规则引用来源清晰，LLM输出包含推理链
- **安全可控**: LLM建议经后处理校核 + 操作员最终确认后执行
- **自动降级**: LLM不可用时纯规则引擎正常运行，无缝切换
- **持续进化**: 操作员确认的高质量决策可回填为经验规则
- **全中文**: 中文界面、日志、规则描述、文档

---

## 许可证

本系统为内部使用软件，版权归 [公司名称] 所有。未经授权，不得复制、分发或用于商业用途。

---

## 文档索引

| 文档 | 路径 | 说明 |
|------|------|------|
| 规则目录 | [docs/rule_catalog.md](docs/rule_catalog.md) | 完整规则库说明 (L1-L4全部38条规则详解、依赖图、覆盖矩阵) |
| 运维手册 | [docs/operations_manual.md](docs/operations_manual.md) | 部署、配置、运维、监控、故障排查指南 |
| API文档 | `http://<host>:8000/docs` | 交互式Swagger API文档 |
| API文档(Redoc) | `http://<host>:8000/redoc` | ReDoc格式API文档 |

---

## 版本历史

| 版本 | 日期 | 里程碑 |
|------|------|--------|
| 0.1.0 | 2025-11-15 | 初始架构设计，L1物理公式12条 |
| 0.2.0 | 2025-12-20 | L2规则完成10条，KIE Server集成 |
| 0.3.0 | 2026-01-28 | L2规则完善至13条，L3策略框架 |
| 0.4.0 | 2026-02-15 | L3策略8个模板，ROE规则，知识库构建 |
| 0.5.0 | 2026-03-10 | L4元规则层设计，LLM Agent集成 |
| 0.6.0 | 2026-04-05 | 全系统联调，仿真环境验证 |
| 0.7.0 | 2026-05-20 | 边界防御和VIP保护策略，覆盖矩阵补充 |
| 0.8.0 | 2026-06-10 | 全部规则验证，文档完善，性能优化 |
| 1.0.0 | 2026-07-13 | V1.0正式发布 |

---

## 联系方式

| 角色 | 联系方式 |
|------|---------|
| 项目负责人 | [待填写] |
| 技术负责人 | [待填写] |
| 系统运维 | counteruav-support@company.com |
| 规则管理 | [待填写] |
| 技术支持热线 | +86-xxx-xxxx-xxxx (7x24) |

---

> 反无人机辅助决策系统 V1.0.0 | 系统工程组 | 2026年7月
