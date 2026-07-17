# 反无人机决策规则引擎

基于 Drools 7.73 + Spring Boot 2.7 的多层级威胁评估与反制策略推理服务。

---

## 环境要求

| 组件 | 版本 | 路径 |
|------|------|------|
| JDK | 21.0.2 (Eclipse Temurin) | `F:\lch\2026\反无\jdk-21.0.2` |
| Maven | 3.9.6 | `F:\lch\2026\反无\apache-maven-3.9.6` |
| 数据库 (开发) | H2 嵌入式 | `./data/rule_engine_db` |
| 数据库 (生产) | MySQL 8.0 | 需单独安装 |

---

## 快速开始

### 1. 进入项目目录

```bash
cd "F:/lch/2026/反无/方案/软件设计0624/counteruav-decision-agent/rule-engine"
```

### 2. 运行测试（推荐首选）

验证 64 个单元测试全部通过：

**Git Bash / 终端：**

```bash
python mvn.py test
```

**Windows 资源管理器：** 双击 `run-tests.bat`

**手动（需先配好 JAVA_HOME 和 PATH）：**

```bash
mvn test -Dspring.profiles.active=dev
```

预期输出：

```
Tests run: 64, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
```

### 3. 启动服务

**Git Bash / 终端：**

```bash
python mvn.py run
```

**Windows 资源管理器：** 双击 `start-dev.bat`

服务启动后访问：

- API 端点: `http://localhost:8080/api/decision/assess`
- H2 控制台: `http://localhost:8080/h2-console`（JDBC URL: `jdbc:h2:file:./data/rule_engine_db`，用户名 `sa`，密码留空）
- Druid 监控: `http://localhost:8080/druid/`（用户名 `admin`，密码 `admin`）

### 4. 测试 API

```bash
curl -X POST http://localhost:8080/api/decision/assess \
  -H "Content-Type: application/json" \
  -d @test_request.json
```

---

## 三种运行方式对照

| 方式 | Shell | 命令 | 适用场景 |
|------|-------|------|----------|
| **Python 脚本** | Git Bash / PowerShell / cmd | `python mvn.py test` / `python mvn.py run` | ⭐ 推荐，自动处理中文路径 |
| **批处理文件** | Windows 资源管理器双击 | `run-tests.bat` / `start-dev.bat` | 最简单，无需开终端 |
| **原生 Maven** | 任意（需先配 PATH） | `mvn test -Dspring.profiles.active=dev` | 熟悉 Maven 的开发者 |

### mvn.py 命令参考

```bash
python mvn.py test      # 运行 64 个单元测试
python mvn.py run       # 启动服务（开发模式，H2 嵌入式数据库）
python mvn.py compile   # 仅编译
python mvn.py clean     # 清理 + 编译
```

> **注意**：当前 Git Bash 终端通过 `cmd.exe //c` 传递中文路径会乱码，因此推荐使用 `python mvn.py` 或直接双击 `.bat` 文件。Python 内部用 Unicode 处理路径，能正确传递中文目录给 Maven。

---

## 项目结构

```
rule-engine/
├── src/main/java/com/counteruav/
│   ├── RuleEngineApplication.java    # Spring Boot 启动类
│   ├── config/
│   │   ├── DroolsConfig.java         # Drools 规则引擎配置
│   │   └── RestTemplateConfig.java   # HTTP 客户端配置
│   ├── controller/
│   │   ├── DecisionController.java   # 威胁评估 REST API
│   │   └── RuleManageController.java # 规则管理 REST API
│   ├── model/                        # 数据模型 (Target, Device, ThreatLevel 等)
│   ├── service/
│   │   ├── RuleEngineService.java    # 核心：7步决策流水线
│   │   ├── ThreatEvaluator.java      # IFN-TOPSIS 多指标威胁评估
│   │   ├── StrategyMatcher.java      # 策略匹配与设备分配
│   │   ├── ConfidenceGate.java       # 置信度评估与 LLM 门控
│   │   ├── LLMClientService.java     # LLM Agent HTTP 客户端
│   │   └── DecisionLogService.java   # 决策日志与反馈管理
│   └── util/
│       ├── PhysicsLibrary.java       # 雷达/光电/电子对抗物理计算
│       └── LLMCallRateLimiter.java   # LLM 调用速率限制器
├── src/main/resources/
│   ├── application.yml               # 主配置（MySQL 数据库）
│   ├── application-dev.yml           # 开发配置（H2 嵌入式数据库）
│   ├── kmodule.xml                   # Drools KIE 模块定义
│   └── rules/
│       ├── l1-physics/               # L1 物理层规则 (7条)
│       ├── l2-doctrine/              # L2 条令层规则 (21条)
│       ├── l3-tactical/              # L3 战术层规则 (7条)
│       └── l4-learning/              # L4 学习层规则 (6条)
├── src/test/java/com/counteruav/
│   ├── service/
│   │   ├── ThreatEvaluatorTest.java  # 13 tests - 威胁评估
│   │   ├── StrategyMatcherTest.java  # 14 tests - 策略匹配
│   │   └── ConfidenceGateTest.java   # 16 tests - 置信度门控
│   └── util/
│       └── PhysicsLibraryTest.java   # 21 tests - 物理计算
├── mvn.py                            # Python 启动脚本
├── run-tests.bat                     # Windows 测试脚本
├── start-dev.bat                     # Windows 启动脚本
├── build-and-run.bat                 # Windows 一键构建
├── setup-env.bat                     # 环境变量配置
├── check-env.py                      # 环境检查脚本
└── test_request.json                 # API 测试数据
```

---

## 四级规则管道

```
Request → [L1 物理层 7规则] → [L2 条令层 21规则] → [L3 战术层 7规则] → [L4 学习层 6规则] → Response
              ↑ 高频快速匹配      ↑ 核心分类+ROE        ↑ 多目标协同          ↑ 历史数据驱动
```

| 层级 | 文件 | 规则数 | 功能 |
|------|------|--------|------|
| L1 物理层 | `kinematics_threat.drl` | 7 | 运动学特征、射频信号、分类置信度 |
| L2 条令层 | `threat_classification.drl` | 7 | 距离+类别+驻留时间威胁分类 |
| | `threat_escalation.drl` | 5 | 俯冲、蜂群、低空突防升级条件 |
| | `rules_of_engagement.drl` | 4 | 民用区域致命武器限制、友军保护 |
| | `strategy_match.drl` | 5 | 按机型匹配干扰/诱骗/摧毁策略 |
| L3 战术层 | `multi_target_coordination.drl` | 7 | 多目标协同、蜂群判定、环境自适应 |
| L4 学习层 | `historical_patterns.drl` | 6 | 夜间模式、侦察预警、历史策略反馈 |

---

## API 接口

| 方法 | 路径 | 功能 |
|------|------|------|
| POST | `/api/decision/assess` | 威胁评估 - 提交目标列表，返回决策方案 |
| POST | `/api/decision/feedback` | 提交指挥员反馈（批准/驳回/修改） |
| GET | `/api/decision/history` | 查询历史决策记录 |
| GET | `/api/decision/{decisionId}` | 查询单条决策详情 |
| GET | `/api/decision/status` | 系统状态（LLM 健康、限流状态） |
| GET | `/api/rules` | 所有规则列表 |
| GET | `/api/rules/{ruleId}` | 单条规则详情 |
| PUT | `/api/rules/{ruleId}` | 更新规则内容 |
| POST | `/api/rules/reload` | 热加载所有规则 |
| POST | `/api/rules/pending/{id}/approve` | 审批 L4 规则提案 |
| POST | `/api/rules/pending/{id}/reject` | 拒绝 L4 规则提案 |

---

## 测试覆盖

```
ConfidenceGateTest       ████████████  16 tests  置信度计算 + 5个LLM触发条件
StrategyMatcherTest      ████████████  14 tests  5级响应策略 + ROE约束 + 设备分配
ThreatEvaluatorTest      ████████████  13 tests  IFN-TOPSIS评估 + 多目标排序 + 边界
PhysicsLibraryTest       ████████████  21 tests  雷达/SNR/dB/多普勒/干扰/光电
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total                                             64 tests, 0 failures
```
