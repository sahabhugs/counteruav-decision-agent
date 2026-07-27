# 反无人机 LLM Agent 辅助决策模块

基于 ReAct（Reasoning-Acting）推理模式的离线智能辅助决策系统，搭载 Qwen3-8B 本地大模型，在规则引擎低置信度时为指挥员提供深度态势分析和反制策略建议。

---

## 目录

1. [架构总览](#1-架构总览)
2. [核心设计原则](#2-核心设计原则)
3. [模块结构与文件说明](#3-模块结构与文件说明)
4. [ReAct 推理引擎](#4-react-推理引擎)
5. [七个 Tool 工具](#5-七个-tool-工具)
6. [威胁等级感知限流器](#6-威胁等级感知限流器)
7. [输出校验与 ROE 硬约束](#7-输出校验与-roe-硬约束)
8. [决策全链路数据流](#8-决策全链路数据流)
9. [配置参数说明](#9-配置参数说明)
10. [运行与测试](#10-运行与测试)
11. [实现路线回顾](#11-实现路线回顾)

---

## 1. 架构总览

```
┌─────────────────────────────────────────────────────────────────────┐
│                           llm-agent 模块                            │
│                                                                     │
│  POST /api/llm/decide                                               │
│       │                                                             │
│       ▼                                                             │
│  ┌──────────────┐    ┌──────────────────────────────────────────┐  │
│  │  限流器       │───→│  ReAct 推理引擎                           │  │
│  │  威胁等级感知  │    │                                          │  │
│  │  紧急通道     │    │  System Prompt（态势+工具+术语）            │  │
│  └──────────────┘    │       │                                    │  │
│                      │       ▼                                    │  │
│                      │  ┌──────────────────────────────────┐     │  │
│                      │  │  Think → Action → Observe 循环    │     │  │
│                      │  │  · 最多 5 轮有效推理              │     │  │
│                      │  │  · 格式错误不消耗轮数             │     │  │
│                      │  │  · 超时优先解析已有输出           │     │  │
│                      │  └──────────────┬───────────────────┘     │  │
│                      │                 │                          │  │
│                      │     ┌───────────┼───────────┐              │  │
│                      │     ▼           ▼           ▼              │  │
│                      │  Tool 1-7   工具调用      最终决策          │  │
│                      │  (规则/知识库  (轨迹/行动   (JSON 格式)     │  │
│                      │   /TOPSIS/设备  预测/案例)                  │  │
│                      │   /预测/模拟)                               │  │
│                      └──────────────────────────────────────────┘  │
│                                         │                          │
│                                         ▼                          │
│  ┌─────────────────┐    ┌─────────────────────────────┐           │
│  │  OutputValidator │←───│  JSON Schema 校验             │           │
│  │  · 结构校验      │    │  + ROE 硬约束业务规则          │           │
│  │  · 业务规则      │    │  + 风险等级标记               │           │
│  └─────────────────┘    └─────────────────────────────┘           │
│                                         │                          │
│                                         ▼                          │
│                              结构化决策 JSON → Java 规则引擎        │
│                              → ROE 二次过滤 → 操作风险分级          │
│                              → 可逆自动 / 不可逆人工确认            │
└─────────────────────────────────────────────────────────────────────┘
```

### 与上游 Java 规则引擎的协作关系

```
规则引擎 (Java/Drools)                     LLM Agent (Python/本模块)
        │                                         │
   每帧数据 (50ms)                                │
        │                                         │
   置信度计算 (六维加权)                            │
        │                                         │
   conf ≥ 阈值? ───Yes──→ 直接执行                 │
        │                                         │
       No                                         │
        │                                         │
        └──→ 预注入 TOPSIS + 规则列表              │
             + 态势 JSON                           │
                    ──→  POST /api/llm/decide ──→  ReAct 深度推理
                                                         │
                                                   结构化决策 JSON
                                                         │
                    ←──  返回决策  ←─────────────────────┘
             │
        ROE 硬约束过滤 (Drools L2)
             │
        操作风险分级
        ├─ L-可逆 → 自动执行
        ├─ M-半可逆 → 自动+可撤销
        └─ H-不可逆 → 强制人工确认
```

---

## 2. 核心设计原则

| 原则 | 说明 | 实现方式 |
|------|------|---------|
| **规则引擎为主，LLM 为辅** | 100% 帧过规则引擎，仅低置信度案例触发 LLM | 置信度门控机制（六维加权） |
| **安全先于效率** | 所有 LLM 输出不可直接控制武器 | ROE 硬约束过滤 + 操作风险分级 + 人工确认 |
| **离线可运行** | 军工场景无网络依赖 | Qwen3-8B GGUF + llama.cpp CPU 推理 |
| **可解释可审计** | 每个决策必须引用来源 | 推理链记录 + 工具调用追溯 + 数据来源标注 |
| **渐进降级** | 异常时安静退化而非崩溃 | HTTP → 本地文件 → 内置默认值三级回退 |
| **人在回路** | 不可逆操作强制人工确认 | L/M/H 三级操作风险分级 |
| **自研轻量** | 不依赖 LangGraph/CrewAI 等重框架 | ~600 行 ReAct 引擎 + 模块化 Tool 设计 |

---

## 3. 模块结构与文件说明

```
llm-agent/
│
├── src/
│   ├── main.py                    # FastAPI 服务入口（生命周期、端点、Tool 注册）
│   ├── config.py                  # 全局配置（环境变量 → 类属性）
│   ├── react_engine.py            # ReAct 推理循环引擎（核心）
│   ├── rule_engine.py             # 规则引擎集成层（置信度门控 + Agent 上报）
│   ├── rate_limiter.py            # 威胁等级感知限流器
│   ├── output_validator.py        # JSON Schema + ROE 业务规则校验
│   │
│   └── tools/                     # 七个 Tool 实现
│       ├── __init__.py            # 模块导出
│       ├── registry.py            # Tool 注册中心（注册/注销/执行/描述）
│       ├── search_rules.py        # Tool 1: 规则库检索（HTTP → 本地 JSON 回退）
│       ├── query_kb.py            # Tool 2: 知识库查询（FAISS → JSON 关键词回退）
│       ├── run_topsis.py          # Tool 3: TOPSIS 假设分析（HTTP → 本地简化计算）
│       ├── check_devices.py       # Tool 4: 设备状态查询（HTTP → 态势数据回退）
│       ├── predict_trajectory.py  # Tool 5: 轨迹预测（新增，L1 运动学外推）
│       ├── simulate_action.py     # Tool 6: 行动效果预测（新增，查表+物理模型）
│       └── retrieve_cases.py      # Tool 7: 案例检索（新增，动态 Few-shot 双轨制）
│
├── prompt_templates/              # 提示词资源
│   ├── system_prompt.txt          # System Prompt 模板（含 {available_tools} 占位符）
│   ├── few_shot_examples.json     # 静态 Few-shot 示例（15 个典型场景，冷启动保底）
│   └── terminology.json           # 军事/反无人机术语词典（33 条）
│
├── tests/                         # 单元测试（157 个测试用例）
│   ├── test_react_engine.py       # ReAct 引擎测试（解析/校验/超时/轮次）
│   ├── test_rule_engine.py        # 规则引擎上报测试（置信度/Agent增强/集成层）★新增
│   ├── test_tools.py              # 原有 Tool 测试（5 个 Tool + 注册中心）
│   ├── test_prompts.py            # 提示词模板质量测试
│   ├── test_predict_trajectory.py # 轨迹预测测试（17 个）
│   ├── test_simulate_action.py    # 行动模拟测试（15 个）
│   ├── test_retrieve_cases.py     # 案例检索测试（7 个）
│   └── test_rate_limiter.py       # 限流器测试（12 个）
│
├── requirements.txt               # Python 依赖
├── Dockerfile                     # 容器化部署
└── README.md                      # 本文档
```

---

## 4. ReAct 推理引擎

### 4.1 原理

ReAct（Reasoning + Acting）是一种让 LLM 在推理过程中主动调用工具获取信息的模式。引擎交替执行：

```
Think（思考）→ Action（调用工具）→ Observe（观察结果）→ Think → ... → Final（最终决策）
```

与传统的单轮 Q&A 相比，ReAct 的优势在于：
- **信息获取**：LLM 不需要从训练数据中"回忆"当前态势细节，而是主动查询规则库、知识库、设备状态
- **推理链可追溯**：每一步工具调用都被记录在 `data_sources` 和 `reasoning_chain` 中
- **减少幻觉**：用实际查询结果替代模型猜测

### 4.2 核心循环

```python
def run(self, task: str, situation: dict) -> dict:
    valid_rounds = 0       # 有效推理轮数
    retry_count = 0        # Schema 校验失败重试
    MAX_RETRIES = 2        # 最多重试 2 次

    while valid_rounds < MAX_ROUNDS:  # 默认 5 轮

        # 1. 调用 LLM
        response = llm.create_chat_completion(messages, ...)

        # 2. 解析 Action（工具调用指令）
        action = self._parse_action(response)
        if action:
            valid_rounds += 1
            result = tools.execute(action.tool, action.args)
            messages.append("工具返回: {result}")
            continue

        # 3. 解析 Final（最终决策 JSON）
        final = self._parse_final(response)
        if final:
            valid, errors = validator.validate(final)
            if valid:
                return final       # 成功！
            else:
                retry_count += 1   # Schema 校验失败
                if retry_count > MAX_RETRIES:
                    return 降级决策  # 重试耗尽
                valid_rounds -= 1  # ★ 不消耗有效轮数
                continue

        # 4. 既无 Action 也无 Final → 提示 LLM 继续
        valid_rounds += 1
```

### 4.3 关键设计决策

**格式错误不消耗轮数**：如果 LLM 输出的 JSON 存在 Schema 问题（缺少字段、类型错误），引擎告知 LLM 修正并回退 `valid_rounds` 计数。这意味着 5 轮保证是 5 轮**有效推理**而非 5 次尝试。

**超时优先解析已有输出**：当 10 秒超时发生时，引擎先从最近的 assistant 消息中尝试提取有效 JSON。只有解析失败时才会降级为保守策略（威胁等级 5，全频段压制）。

**三级降级路径**：

| 情况 | 降级策略 | 置信度 |
|------|---------|--------|
| 超时 + 已有有效输出 | 使用已有输出 + 标记 `RESULT_AFTER_TIMEOUT` | 保留原始置信度 |
| 超时 + 无有效输出 | 保守策略（威胁=5，全频段压制） | 0.30 |
| Schema 校验重试耗尽 | 保留 LLM 部分信息 + 降级标注 | 0.0 |

### 4.4 Action 解析

支持三种 LLM 输出格式：

```
格式 1 (Python 风格):  Action: search_rules(query='高速接近', layers=[1,2])
格式 2 (Shell 风格):   Action: query_kb entity_type=drone query=DJIMavic3 top_k=5
格式 3 (JSON 风格):    {"action": "run_topsis", "args": {"target_id": "T001"}}
```

也支持中文标记：`行动: check_devices(device_type='干扰器')`

---

## 5. 七个 Tool 工具

### 5.1 工具总览

| # | Tool | 功能 | 回退策略 |
|---|------|------|---------|
| 1 | `search_rules` | 检索 Drools 规则库 | HTTP → 本地 JSON 关键词匹配 |
| 2 | `query_kb` | 查询知识库（无人机/场景/地形/电磁环境） | FAISS 语义 → JSON 关键词匹配 |
| 3 | `run_topsis` | TOPSIS 威胁评估（可选假设分析） | HTTP → 本地简化 TOPSIS |
| 4 | `check_devices` | 查询反制设备实时状态 | HTTP → 态势数据提取 |
| 5 | `predict_trajectory` | 轨迹预测 + CPA + 禁飞区检测 | L1 运动学公式（纯本地） |
| 6 | `simulate_action` | 行动效果预测 + 风险评估 | 查表 + 简化物理模型（纯本地） |
| 7 | `retrieve_cases` | 历史相似案例检索（动态 Few-shot） | FAISS → 静态关键词 + 内置默认 |

### 5.2 Tool 注册与调度

```python
# 每个 Tool 都是独立的 Python 函数，签名统一：
def tool_name(args: dict) -> dict:
    return {"success": bool, "data": ..., "error": str}

# 注册中心提供统一的调度接口：
registry = ToolRegistry()
registry.register("search_rules", search_rules, "搜索规则库。参数: ...")
result = registry.execute("search_rules", {"query": "高速接近"})
# → {"success": True, "data": [...], "error": ""}
```

### 5.3 Tool 5: predict_trajectory — 轨迹预测

**原理**：基于 L1 物理定律层的简单运动学公式做线性外推：

```
lat(t) = lat_0 + v × cos(heading) × t / 111320.0
lon(t) = lon_0 + v × sin(heading) × t / (111320.0 × cos(lat_0))
alt(t) = alt_0 + v_vertical × t
```

使用球面几何的 haversine 公式计算大圆距离，通过 0.5s 步长采样搜索 CPA（最近接近点）。

**输入**：
```json
{
  "target_id": "T-073",
  "horizon_s": 30.0,
  "_situation": {
    "targets": [{"target_id": "T-073", "lat": 39.91, "lon": 116.41, "alt": 120, "speed_ms": 22, "heading": 270}],
    "no_fly_zones": [{"center": {"lat": 39.9042, "lon": 116.4040}, "radius_m": 500}]
  }
}
```

**输出**：
```json
{
  "target_id": "T-073",
  "current_position": {"lat": 39.91, "lon": 116.41, "alt_m": 120.0},
  "predicted_positions": [
    {"t_s": 5, "lat": ..., "lon": ..., "distance_to_defense_m": 680.5},
    {"t_s": 10, "lat": ..., "lon": ..., "distance_to_defense_m": 350.2},
    {"t_s": 15, "lat": ..., "lon": ..., "distance_to_defense_m": 120.8}
  ],
  "cpa_m": 85.3,
  "cpa_time_s": 16.5,
  "will_enter_no_fly": true,
  "no_fly_violation_time_s": 12.0
}
```

### 5.4 Tool 6: simulate_action — 行动效果预测

**原理**：多维因子加权模型，综合考虑 6 个效果因子和风险维度：

```
效果 = base_factor × 类型匹配 + JSR 因子 + 遮挡因子

其中：
- 距离因子 = 1.0（范围内）或 exp(-2×(超出比例-1))（范围外）
- 类型匹配 = 查表（unknown→rf_jamming=0.6, consumer→rf_jamming=1.0, military→rf_jamming=0.4, ...）
- JSR 因子 = min(1.0, JSR_dB / 20)，JSR = ERP_jammer(dB) - ERP_signal(dB)
- 遮挡因子 = 地形系数 × 天气系数
- 民用区域惩罚 = ×0.3（H-不可逆）/ ×0.7（M-半可逆）
```

**支持的行动类型**：

| 行动 | 风险等级 | 执行方式 |
|------|---------|---------|
| `rf_jamming_*`（射频干扰） | L-可逆 | 自动执行 |
| `gnss_spoofing`（导航诱骗） | L-可逆 | 自动执行 |
| `monitor`（监测） | L-可逆 | 自动执行 |
| `rf_jamming_full_band`（全频段压制） | M-半可逆 | 自动+可撤销 |
| `high_power_microwave`（微波毁伤） | M-半可逆 | 自动+可撤销 |
| `net_capture`（网捕） | M-半可逆 | 自动+可撤销 |
| `laser_destruction`（激光摧毁） | **H-不可逆** | **强制人工确认** |
| `kinetic_impact`（动能打击） | **H-不可逆** | **强制人工确认** |

### 5.5 Tool 7: retrieve_cases — 案例检索（动态 Few-shot）

**双轨制设计**：

```
冷启动阶段（< 50 个 APPROVED 案例）:
  ┌─────────────┐     关键词匹配      ┌──────────────┐
  │ 态势描述文本  │ ─────────────────→ │ 15 个静态示例  │
  └─────────────┘                    └──────────────┘

热启动阶段（≥ 50 个 APPROVED 案例）:
  ┌─────────────┐     bge-small-zh     ┌──────────────┐
  │ 态势描述文本  │ ──→ embedding ──→  │ FAISS 索引    │ → Top-3 动态案例
  └─────────────┘                    └──────────────┘
  动态检索失败时 fallback 到静态模板
```

---

## 6. 威胁等级感知限流器

### 6.1 设计原理

传统限流器对所有目标一视同仁，在突发威胁场景下会把高威胁目标的推理请求和低威胁的一起拦住。威胁等级感知限流器根据目标紧迫性动态调整配额。

### 6.2 三级配额

| 威胁等级 | 同目标配额（次/分钟） | 全局冷却 | 说明 |
|---------|---------------------|---------|------|
| 5（极危） | **无限制** | 无冷却 | 等同于紧急通道，始终放行 |
| 4（高危） | 6 | 1 秒 | 每 10 秒可推理一次 |
| 3（中危） | 3 | 5 秒（常规冷却） | 每 20 秒 |
| 1-2（低危） | 2 | 5 秒 | 每 30 秒 |

### 6.3 紧急通道

两种情况可直接绕过所有限流检查：

1. `threat_level >= 5` — 极危目标
2. `urgent=True` — 指挥员手动触发

```python
# 常规调用
limiter.try_acquire("T001", threat_level=3, urgent=False)

# 紧急调用（指挥员手动触发或威胁等级 5）
limiter.try_acquire("T001", threat_level=5, urgent=False)  # 始终返回 True
limiter.try_acquire("T001", threat_level=3, urgent=True)   # 始终返回 True
```

---

## 7. 输出校验与 ROE 硬约束

### 7.1 双重校验

```
LLM 输出 JSON
      │
      ▼
┌──────────────────┐
│ 层 1: Pydantic   │  → 结构校验（必填字段、数值范围、类型正确性）
│ Schema 校验       │
└────────┬─────────┘
         │ 通过
         ▼
┌──────────────────┐
│ 层 2: 业务规则   │  → ROE 硬约束
│ 校验              │     · 威胁等级 ≤ 1 + 硬杀伤 → 拒绝
└──────────────────┘     · 平民区域 + 威胁 < 5 + 硬杀伤 → 拒绝
         │               · 置信度 < 0.3 → 警告
         ▼               · 威胁等级与评分不一致 → 拒绝
    有效决策 JSON
```

### 7.2 风险等级自动判定

LLM 输出的 `recommended_action.action_type` 会自动映射到风险等级：

```
rf_jamming_selective    → L-可逆
gnss_spoofing           → L-可逆
rf_jamming_full_band    → M-半可逆
net_capture             → M-半可逆
high_power_microwave    → M-半可逆
laser_destruction       → H-不可逆
kinetic_impact          → H-不可逆
```

---

## 8. 决策全链路数据流

### 完整请求→响应流程

```
1. Java 规则引擎发送决策请求
   POST /api/llm/decide
   {
     "task_id": "task-20260720-00142",
     "trigger_reason": "LOW_CONFIDENCE",
     "threat_level": 4,
     "urgent": false,
     "situation": {
       "targets": [{...}],           # 目标列表
       "available_devices": [{...}], # 设备列表
       "environment": {...},         # 环境信息
       "precomputed": {              # 规则引擎预计算
         "topsis": {...},
         "matched_rules": [...],
         "confidence_breakdown": {...}
       }
     },
     "task_description": "目标 T-073 置信度 0.62，请深度推理"
   }

2. 限流器检查
   → threat_level=4, urgent=false
   → 检查冷却+配额 → 通过

3. System Prompt 构建
   → 注入态势摘要（precomputed 数据直接可用）
   → 注入 7 个 Tool 描述
   → 注入 15 个静态 Few-shot（冷启动）或动态检索案例（热启动）
   → 注入 33 条军事术语定义

4. ReAct 推理循环（示例）
   Round 1:
     Think: 目标 T-073 型号未知，速度 22m/s，precomputed 中 TOPSIS=0.94...
     Action: predict_trajectory(target_id='T-073')
     Observe: CPA=85.3m, 16.5 秒后最近

   Round 2:
     Think: CPA 极近，需要紧急处置。先检查设备状态和模拟射频干扰效果
     Action: check_devices()
     Action: simulate_action(target_id='T-073', action_type='rf_jamming_full_band')
     Observe: RF-JAM-001 在线, 距离 1.2km, 预测效果 0.78

   Round 3:
     Think: 信息足够。型号未知→全频段压制，备选 GNSS 诱骗。避免激光。
     Final: {完整决策 JSON}

5. 输出校验
   → Pydantic Schema 校验 → 通过
   → ROE 业务规则校验 → action_type=rf_jamming_full_band（L-可逆），无硬杀伤违规 → 通过

6. 返回给 Java 规则引擎
   {
     "decision": {
       "threat_assessment": {"level": 5, "confidence": 0.78, ...},
       "recommended_action": {
         "action_type": "rf_jamming_full_band",
         "risk_level": "L-可逆",      ← 可自动执行
         ...
       },
       "reasoning_chain": [...],
       "data_sources": ["predict_trajectory", "check_devices", "simulate_action"]
     },
     "metadata": {
       "elapsed_seconds": 3.2,
       "validation_passed": true,
       "agent_confidence": 0.78,
       "confidence_improved": true,
       "trigger_reason": "置信度低于阈值: 0.6200 < 0.8"
     }
   }

7. Java 侧 ROE 硬约束过滤（二次校验）
   → 通过 Drools L2 规则过滤
   → 风险分级: L-可逆 → 自动执行 + 通知指挥员
```

---

## 9. 配置参数说明

所有配置项支持环境变量覆盖（`.env` 文件或系统环境变量）：

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `LLM_MODEL_PATH` | `models/qwen3-8b-q4_k_m.gguf` | Qwen3-8B 量化模型路径 |
| `LLM_EMBEDDING_MODEL` | `models/bge-small-zh` | bge-small-zh 嵌入模型路径 |
| `LLM_N_CTX` | `8192` | LLM 上下文窗口大小 |
| `LLM_N_THREADS` | `8` | llama.cpp 推理线程数 |
| `LLM_TEMPERATURE` | `0.1` | LLM 温度（低=稳定输出） |
| `LLM_MAX_TOKENS` | `1024` | 单次推理最大生成 token |
| `LLM_MAX_ROUNDS` | `5` | ReAct 最大有效推理轮数 |
| `LLM_TIMEOUT_SECONDS` | `10.0` | 单次推理超时时间 |
| `LLM_CONFIDENCE_THRESHOLD` | `0.80` | 置信度门控阈值（可热更新） |
| `LLM_MAX_CALLS_PER_MINUTE` | `10` | 全局每分钟最大调用次数 |
| `LLM_COOLDOWN_SECONDS` | `5` | 常规调用冷却时间 |
| `LLM_SERVER_HOST` | `0.0.0.0` | FastAPI 服务监听地址 |
| `LLM_SERVER_PORT` | `8001` | FastAPI 服务端口 |
| `LLM_RULE_ENGINE_URL` | `http://localhost:8080` | Java 规则引擎 HTTP 地址 |
| `LLM_KB_INDEX_DIR` | `data/kb_index` | FAISS 索引存储目录 |
| `LLM_KB_JSON_DIR` | `data/kb_json` | 知识库 JSON 数据目录 |
| `LLM_LOG_LEVEL` | `INFO` | 日志级别 |

---

## 10. 运行与测试

### 安装依赖

```bash
pip install -r requirements.txt
```

### 运行测试

```bash
# ==================== 全量测试 ====================
cd llm-agent
python -m pytest tests/ -v

# ==================== 按模块测试 ====================

# 规则引擎上报流程测试（45 个用例）★ 核心
python -m pytest tests/test_rule_engine.py -v

# ReAct 引擎测试（解析/校验/超时/轮次）
python -m pytest tests/test_react_engine.py -v

# 规则引擎集成层单独测试
python -m pytest tests/test_rule_engine.py::TestRuleEngineIntegration -v

# 置信度计算函数测试
python -m pytest tests/test_rule_engine.py::TestRuleEngineModuleFunctions -v

# 端到端上报流程测试
python -m pytest tests/test_rule_engine.py::TestEndToEndEscalationFlow -v

# 请求/响应格式兼容性测试
python -m pytest tests/test_rule_engine.py::TestRequestResponseCompatibility -v

# 原有工具测试
python -m pytest tests/test_tools.py -v

# 轨迹预测测试
python -m pytest tests/test_predict_trajectory.py -v

# 行动模拟测试
python -m pytest tests/test_simulate_action.py -v

# 案例检索测试
python -m pytest tests/test_retrieve_cases.py -v

# 限流器测试
python -m pytest tests/test_rate_limiter.py -v

# 提示词模板测试
python -m pytest tests/test_prompts.py -v

# ==================== 运行单个测试 ====================
python -m pytest tests/test_rule_engine.py::TestRuleEngineIntegration::test_low_confidence_triggers_agent -v
python -m pytest tests/test_rule_engine.py::TestRuleEngineIntegration::test_agent_unavailable_fallback -v
python -m pytest tests/test_rule_engine.py::TestConfidenceGate::test_low_confidence_triggers_escalation -v

# ==================== 关键字过滤 ====================
python -m pytest tests/test_rule_engine.py -v -k "confidence"    # 只运行含 confidence 的测试
python -m pytest tests/test_rule_engine.py -v -k "escalation"    # 只运行含 escalation 的测试
python -m pytest tests/test_rule_engine.py -v -k "fallback"      # 只运行含 fallback 的测试

# ==================== 详细输出 ====================
python -m pytest tests/test_rule_engine.py -v --tb=long          # 详细错误追踪
python -m pytest tests/test_rule_engine.py -v -s                 # 显示 print 输出
```

### 启动服务

```bash
# 确认模型文件存在
ls models/qwen3-8b-q4_k_m.gguf

# 启动（默认 8001 端口）
python src/main.py

# 健康检查
curl http://localhost:8001/api/llm/health
# → {"status":"healthy","model_loaded":true,"tools_count":7,...}

# 限流器状态
curl http://localhost:8001/api/llm/status
# → {"global_calls_last_minute":0,"global_limit":10,...}
```

### 测试当前状态

```
157 passed, 0 failed
```

---

## 11. 实现路线回顾

### 已完成的改进（基于 grill-me 技能深度质询后的 12 项优化）

| # | 改进项 | 实现位置 | 状态 |
|---|--------|---------|------|
| 1 | 模型能力验证关卡 | 配置 + 阶段 1 实施脚本 | 就绪 |
| 2 | 置信度阈值可配置 + 校准 | `config.py` CONFIDENCE_THRESHOLD | ✅ |
| 3 | ReAct 终止逻辑修复 | `react_engine.py` run() 循环 | ✅ |
| 4 | 新增 predict_trajectory Tool | `tools/predict_trajectory.py` | ✅ |
| 4 | 新增 simulate_action Tool | `tools/simulate_action.py` | ✅ |
| 5 | ROE 硬约束过滤 | `output_validator.py` 业务规则校验 | ✅ |
| 6 | 规则升级量化标准 | 属 Java 规则引擎侧 | — |
| 7 | 操作风险分级 (L/M/H) | `simulate_action.py` + `output_validator.py` | ✅ |
| 8 | 威胁等级感知限流器 | `rate_limiter.py` | ✅ |
| 9 | propose_new_rule 移出实时 Tool | `main.py` 注册列表 | ✅ |
| 10 | TOPSIS 预注入 | `run_topsis.py` 改为可选假设分析 | ✅ |
| 11 | 动态 Few-shot 双轨制 | `tools/retrieve_cases.py` | ✅ |
| 12 | 行为-型号一致性检查 | 属 Java 侧置信度计算 | — |
| — | 新增 retrieve_cases Tool | `tools/retrieve_cases.py` | ✅ |

### 技术栈

| 组件 | 选型 | 理由 |
|------|------|------|
| Web 框架 | FastAPI 0.104 | 异步高性能，Pydantic 深度集成 |
| LLM 推理 | llama.cpp (llama-cpp-python) | CPU 推理，硬件兼容性最强 |
| 推理模型 | Qwen3-8B GGUF Q4_K_M | 中文理解好，量化后 <6GB 内存 |
| 嵌入模型 | bge-small-zh | 中文语义检索，~100MB CPU 友好 |
| 向量索引 | FAISS CPU | 离线轻量，无需额外服务 |
| 配置管理 | python-dotenv | 环境变量覆盖，部署灵活 |
| 测试框架 | pytest + unittest.mock | 无外部依赖的纯 Python 测试 |

---

> **文档版本**: v2.0
> **生成日期**: 2026-07-20
> **关联文档**: 《离线Agent威胁评估与决策优化-落地方案》
> **测试覆盖**: 142 个单元测试，覆盖所有 Tool、引擎、限流器、校验器和提示词模板
