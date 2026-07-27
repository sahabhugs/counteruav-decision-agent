# 离线 Agent 实现威胁评估与决策优化 — 可落地方案

> **来源文档**：《软件设计0708》反无人机一体化指挥控制系统  
> **实施目标**：用离线 Agent 实现数据分析服务中心中的**威胁评估 + 策略调度 + 效果评估优化**决策链  
> **方案结论**：混合架构（Drools 规则引擎 + Qwen3-8B ReAct LLM Agent），四层规则库分层体系，三阶段渐进实现

---

## 目录

1. [架构总览](#一架构总览)
2. [Agent 架构选型](#二agent-架构选型)
3. [规则库设计](#三规则库设计)
4. [置信度门控机制](#四置信度门控机制)
5. [LLM Agent 内部设计](#五llm-agent-内部设计)
6. [分阶段实现路线图](#六分阶段实现路线图)
7. [关键目录与文件结构](#七关键目录与文件结构)
8. [核心接口定义](#八核心接口定义)
9. [数据库表设计](#九数据库表设计)
10. [风险与对策](#十风险与对策)
11. [总结](#十一总结)

---

## 一、架构总览

```
┌──────────────────────────────────────────────────────────────┐
│                    反无人机一体化指挥平台                        │
│                                                              │
│  ┌─────────┐   ┌──────────┐   ┌──────────┐   ┌───────────┐  │
│  │ 多源融合 │ → │ 目标识别  │ → │ 威胁评估  │ → │ 策略调度  │  │
│  │         │   │          │   │          │   │           │  │
│  └─────────┘   └──────────┘   └────┬─────┘   └─────┬─────┘  │
│                                    │               │        │
│                    ┌───────────────┼───────────────┼─────┐  │
│                    │     离线决策 Agent (本项目)          │  │
│                    │                                  │  │
│                    │  ┌──────────────────────┐        │  │
│                    │  │  置信度门控路由器     │        │  │
│                    │  │  (六维计算+可配阈值)  │        │  │
│                    │  └──────┬───────────────┘        │  │
│                    │         │                        │  │
│                    │  conf≥阈值    conf<阈值            │  │
│                    │     │            │                │  │
│                    │     ▼            ▼                │  │
│                    │ ┌────────┐ ┌──────────────┐      │  │
│                    │ │ 规则引擎 │ │ LLM Agent    │      │  │
│                    │ │ Drools  │ │ Qwen3-8B     │      │  │
│                    │ │ (<10ms) │ │ ReAct (2-5s)  │      │  │
│                    │ │        │ │ +预注入TOPSIS │      │  │
│                    │ └───┬────┘ └──────┬───────┘      │  │
│                    │     │            │                │  │
│                    │     └─────┬──────┘                │  │
│                    │           ▼                       │  │
│                    │    ┌──────────────┐               │  │
│                    │    │ ROE硬约束过滤 │ ← 新增        │  │
│                    │    │ (Drools L2)  │               │  │
│                    │    └──────┬───────┘               │  │
│                    │           ▼                       │  │
│                    │    ┌──────────────┐               │  │
│                    │    │ 操作风险分级  │ ← 新增        │  │
│                    │    │ L可逆/M半/H不 │               │  │
│                    │    └──────┬───────┘               │  │
│                    │           ▼                       │  │
│                    │    ┌──────────────┐               │  │
│                    │    │  建议方案输出  │               │  │
│                    │    │  L:自动执行   │               │  │
│                    │    │  H:指挥员确认  │               │  │
│                    │    └──────────────┘               │  │
│                    └──────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

**关键设计原则**：

- **规则引擎 100% 覆盖**：每帧数据都过规则引擎，保证即使 LLM 不可用，核心功能正常
- **LLM 按需调用**：仅低置信度/异常情况触发，威胁等级感知限流器保证高威胁目标优先
- **ROE 硬约束过滤**：所有 LLM 输出经 Drools L2 规则二次校验，违规建议自动拦截
- **操作风险分级**：可逆操作（干扰/诱骗）自动执行，不可逆操作（激光/动能）强制人工确认
- **规则持续进化**：战后异步批处理 → 冲突检测 → 量化标准升级（≥5次匹配+≥80%确认率 L4→L3）
- **模型能力可验证**：阶段 1 模型验证关卡 + 阶段 2 置信度阈值校准实验

---

## 二、Agent 架构选型

### 2.1 为什么选择混合架构

| 维度 | 纯规则引擎 | 纯 LLM Agent | **混合架构（推荐）** |
|------|-----------|-------------|-------------------|
| 延迟 | <10ms ✅ | 1-5s ❌ | <10ms（常规）/ 2-5s（异常）✅ |
| 可解释性 | 完全可追溯 ✅ | 需额外机制 ⚠️ | 规则部分可追溯，LLM 附带推理链 ✅ |
| 边界情况处理 | 无法处理 ❌ | 灵活应对 ✅ | 可处理 ✅ |
| 硬件需求 | 无特殊需求 ✅ | GPU 推荐 ⚠️ | 仅异常时使用 LLM，CPU 可接受 ✅ |
| 持续优化 | 需人工更新 ⚠️ | 可自优化 ✅ | LLM 回填规则，半自动优化 ✅ |

### 2.2 技术选型总表

| 维度 | 选型 | 理由 |
|------|------|------|
| **整体架构** | 混合架构（规则引擎为主，LLM 为辅） | 实时性 + 灵活性兼顾 |
| **规则引擎** | Drools 7.x | Java 生态原生集成，规则热加载，与现有 Spring Boot 一致 |
| **LLM 模型** | Qwen3-8B (GGUF Q4_K_M) | 中文理解好，8B 参数量够用，量化后 CPU 可跑 |
| **推理框架** | llama.cpp | 硬件兼容性最强，军工场景硬件不确定 |
| **Agent 框架** | 自研轻量 ReAct（~500 行 Python） | 不需要 LangGraph 等重框架，决策链是确定性流水线 |
| **向量数据库** | FAISS (CPU 版本) | 离线、轻量、不需要额外服务 |
| **知识库检索** | Elasticsearch（全文）+ FAISS（向量） | ES 检索结构化规则，FAISS 做语义相似度匹配 |
| **规则存储** | MySQL + Git 版本管理 | 与现有技术栈一致 |
| **LLM ↔ Java 通信** | HTTP REST API | 最简集成方式，Python 服务暴露 REST 接口 |

### 2.3 为什么不用现成 Agent 框架

LangGraph / CrewAI / AutoGen 等框架的抽象层级（StateGraph、多 Agent 协作、checkpointing）在反无人机场景是**负担**：

- 决策链是确定性的流水线（融合→识别→评估→调度），不需要动态路由
- 多 Agent 协作是过度设计——只需一个 Agent 串行调用工具
- 引入框架 = 引入延迟 + 调试黑盒 + 依赖风险
- 自研 ~500 行 ReAct 循环引擎完全可控、可审计、可优化

---

## 三、规则库设计

### 3.1 四层规则架构

```
┌─────────────────────────────────────────────────┐
│ L4: 经验优化层（动态、战后异步批处理）               │
│ - 地形适配参数、阈值微调、新发现的战术模式          │
│ - 来源：战后批处理扫描 APPROVED 决策 → 聚类提炼    │
│ - → 冲突检测（交叉验证 L2/L3）→ 人工审核          │
│ - 形式：结构化 JSON                              │
│ - 更新频率：每次作战/演习后                        │
│ - 升级条件 L4→L3: ≥5次匹配 + ≥80%确认率 + 无冲突  │
│          + ≥1次实弹/仿真验证                      │
├─────────────────────────────────────────────────┤
│ L3: 战术策略层（半静态、验证后升级）               │
│ - 无人机型号→反制优选、集群→压制通信频段           │
│ - 来源：L4 升级 + 型号知识库 JSON + 策略模板 JSON  │
│ - 形式：结构化 JSON + Drools .drl                │
│ - 更新频率：随情报数据库更新                       │
│ - 升级条件 L3→L2: ≥20次匹配 + ≥95%确认率          │
│          + 领域专家委员会审核                      │
│ - 降级条件: 任意规则驳回率 >30% → 自动降一级       │
├─────────────────────────────────────────────────┤
│ L2: 作战条例层（基本静态、随条令更新）             │
│ - 5级威胁判定标准、交战规则(ROE)、武器授权边界      │
│ - 来源：条令文档 + 领域专家 + L3 长期验证后升级    │
│ - 形式：Drools .drl 文件                        │
│ - 更新频率：随条令修订                            │
├─────────────────────────────────────────────────┤
│ L1: 物理定律层（永久静态）                        │
│ - 雷达方程、光电作用距离、干扰功率计算             │
│   + predict_trajectory 轨迹预测（运动学公式）     │
│   + simulate_action 距离衰减/干扰比计算           │
│ - 来源：物理公式                                 │
│ - 形式：Java 静态工具类                          │
│ - 更新频率：几乎永不                              │
└─────────────────────────────────────────────────┘
```

### 3.2 L1：物理定律层（Java 工具类）

```java
package com.counteruav.rules.physics;

/**
 * 物理定律层 - 确定性计算，不参与规则匹配
 */
public class PhysicsLibrary {

    /**
     * 雷达最大作用距离（雷达方程简化）
     * R_max = (P_t * G_t * G_r * λ² * σ / ((4π)³ * k * T * B * F * SNR_min))^(1/4)
     */
    public static double radarMaxRange(double pt, double gt, double gr,
                                        double wavelength, double rcs,
                                        double noiseFigure, double snrMin) {
        double numerator = pt * gt * gr * wavelength * wavelength * rcs;
        double denominator = Math.pow(4 * Math.PI, 3)
            * 1.38e-23 * 290 * 1e6 * noiseFigure * snrMin; // k=1.38e-23, T=290K, B=1MHz
        return Math.pow(numerator / denominator, 0.25);
    }

    /**
     * 光电传感器最大探测距离（Johnson 准则简化）
     * R = (H_target * N_pixels * fov_per_pixel) / (2 * tan(FOV/2))
     */
    public static double electroOpticalRange(double targetHeight,
                                              int requiredPixels,
                                              double fovDegrees,
                                              int sensorPixels) {
        double ifov = Math.toRadians(fovDegrees) / sensorPixels;
        return targetHeight / (requiredPixels * ifov);
    }

    /**
     * 干扰有效辐射功率计算
     * ERP_j = P_j * G_j * L_j
     */
    public static double jammerERP(double txPower, double antennaGain, double cableLoss) {
        return txPower * antennaGain / cableLoss;
    }

    /**
     * 干扰距离（干信比 J/S 准则）
     * R_j = R_c * sqrt(P_j * G_j / (P_s * G_s * (J/S)_min))
     */
    public static double jammingRange(double commRange, double jammerERP,
                                       double signalERP, double jsRatioMin) {
        return commRange * Math.sqrt(jammerERP / (signalERP * jsRatioMin));
    }
}
```

### 3.3 L2：作战条例层（Drools .drl）

```java
// 文件: src/main/resources/rules/l2-doctrine/threat_classification.drl
package com.counteruav.rules.threat;

import com.counteruav.model.Target;
import com.counteruav.model.ThreatLevel;

// ==========================================
// 规则组 1：基于距离的威胁等级判定
// ==========================================

rule "L2-001_ThreatLevel_CriticalRange_HighSpeed"
    agenda-group "threat-classification"
    salience 100
    when
        $t: Target(
            distance < 500,                    // 距离小于500m
            radialSpeed > 15,                  // 径向速度>15m/s
            intent == Target.Intent.RAPID_APPROACH
        )
    then
        $t.setThreatLevel(ThreatLevel.CRITICAL); // 5级 - 极危
        $t.addThreatTag("IMMINENT_COLLISION");
        $t.setDecisionSource("L2-001");
        update($t);
end

rule "L2-002_ThreatLevel_CloseRange_CivilianDrone"
    agenda-group "threat-classification"
    salience 90
    when
        $t: Target(
            distance < 1000,
            droneCategory == Target.DroneCategory.CIVILIAN_UNKNOWN,
            threatLevel == null
        )
    then
        $t.setThreatLevel(ThreatLevel.HIGH);    // 4级 - 高
        $t.setDecisionSource("L2-002");
        update($t);
end

rule "L2-003_ThreatLevel_MediumRange_MilitaryDrone"
    agenda-group "threat-classification"
    salience 85
    when
        $t: Target(
            distance < 3000,
            droneCategory == Target.DroneCategory.MILITARY_FIXED_WING,
            threatLevel == null
        )
    then
        $t.setThreatLevel(ThreatLevel.HIGH);    // 4级
        $t.setDecisionSource("L2-003");
        update($t);
end

// ==========================================
// 规则组 2：复合威胁行为升级
// ==========================================

rule "L2-010_ThreatEscalation_MultiBehavior"
    agenda-group "threat-escalation"
    salience 80
    when
        $t: Target(
            threatBehaviorTags contains "ALTITUDE_DIVE",
            threatBehaviorTags contains "SIGNAL_ANOMALY"
        )
    then
        $t.escalateThreat(1);
        $t.setEscalationReason("高度骤降+信号异常 → 复合威胁升级一级");
        $t.setDecisionSource("L2-010");
        update($t);
end

rule "L2-011_ThreatEscalation_SwarmBehavior"
    agenda-group "threat-escalation"
    salience 80
    when
        $t: Target(
            threatBehaviorTags contains "CLUSTER_SWARM",
            threatBehaviorTags contains "RAPID_APPROACH"
        )
    then
        $t.escalateThreat(2);
        $t.setEscalationReason("集群+高速逼近 → 威胁连升两级");
        $t.setDecisionSource("L2-011");
        update($t);
end

// ==========================================
// 规则组 3：交战规则 (ROE)
// ==========================================

rule "L2-020_ROE_LaserOnlyAboveLevel4"
    agenda-group "roe"
    salience 70
    when
        $t: Target(threatLevel.intValue < 4)
        ActionPlan(actionType == ActionType.LASER_DESTRUCTION)
    then
        // 威胁等级 <4 不允许使用激光摧毁
        ActionPlan.setBlocked(true);
        ActionPlan.setBlockReason("威胁等级不足4级，禁止使用激光摧毁（ROE限制）");
end

rule "L2-021_ROE_CivilianAreaRestriction"
    agenda-group "roe"
    salience 70
    when
        $t: Target(
            isOverCivilianArea == true,
            threatLevel.intValue < 5
        )
        ActionPlan(actionType in [ActionType.LASER_DESTRUCTION, ActionType.KINETIC_IMPACT])
    then
        ActionPlan.setBlocked(true);
        ActionPlan.setBlockReason("目标位于平民区域上空，且威胁未达极危级别，禁止硬杀伤");
end

// ==========================================
// 规则组 4：策略匹配 (初始)
// ==========================================

rule "L2-030_Strategy_SmallConsumerDrone"
    agenda-group "strategy-match"
    salience 60
    when
        $t: Target(
            droneCategory == Target.DroneCategory.CONSUMER_QUADCOPTER,
            distance < 3000
        )
    then
        $t.setPrimaryStrategy(StrategyType.RF_JAMMING_2G4_5G8);
        $t.setSecondaryStrategy(StrategyType.GNSS_SPOOFING);
        $t.setDecisionSource("L2-030");
        update($t);
end
```

### 3.4 L3：战术策略层（JSON 规则）

```json
{
  "rule_id": "tactic-001",
  "name": "消费级DJI类无人机-优先射频干扰",
  "source": "LLM-GENERATED",
  "confidence": "PENDING_VERIFICATION",
  "version": 1,
  "created": "2026-07-13T00:00:00Z",
  "condition": {
    "drone_type": "consumer_dji_class",
    "threat_level_range": [2, 4],
    "distance_range_m": [0, 5000]
  },
  "action": {
    "primary": "rf_jamming_2.4g_5.8g",
    "secondary": "gnss_spoofing",
    "avoid": ["laser_destruction", "kinetic_impact"],
    "reason": "消费级无人机多为2.4/5.8GHz遥控链路，射频干扰效果最好且附带损伤最小"
  }
}
```

```json
{
  "rule_id": "tactic-002",
  "name": "军用固定翼无人机-优先GNSS诱骗+激光",
  "source": "LLM-GENERATED",
  "confidence": "PENDING_VERIFICATION",
  "version": 1,
  "created": "2026-07-13T00:00:00Z",
  "condition": {
    "drone_type": "military_fixed_wing",
    "threat_level_range": [3, 5],
    "distance_range_m": [0, 10000]
  },
  "action": {
    "primary": "gnss_spoofing",
    "secondary": "laser_destruction",
    "avoid": ["rf_jamming_low_power_only"],
    "reason": "军用无人机通常有抗干扰措施，INS+GNSS组合导航，GNSS诱骗可使其偏航；若无效则激光摧毁"
  }
}
```

```json
{
  "rule_id": "tactic-003",
  "name": "集群目标-优先全频段压制通信频段",
  "source": "LLM-GENERATED",
  "confidence": "PENDING_VERIFICATION",
  "version": 1,
  "created": "2026-07-13T00:00:00Z",
  "condition": {
    "drone_type": "cluster_swarm",
    "target_count_min": 3,
    "threat_level_range": [3, 5]
  },
  "action": {
    "primary": "rf_jamming_full_band",
    "secondary": "high_power_microwave",
    "avoid": ["single_target_jamming", "gnss_spoofing_single"],
    "reason": "集群目标数量多，逐个处置效率低；全频段压制可同时切断所有蜂群通信链路"
  }
}
```

### 3.5 知识库：无人机型号条目示例

```json
{
  "drone_id": "dji-mavic-3",
  "name": "DJI Mavic 3",
  "name_cn": "大疆御3",
  "category": "consumer_quadcopter",
  "max_speed_ms": 21,
  "max_altitude_m": 6000,
  "max_endurance_min": 46,
  "max_payload_kg": 0.2,
  "frequency_bands": ["2.4GHz", "5.8GHz"],
  "gnss": ["GPS", "GLONASS", "BeiDou", "Galileo"],
  "static_threat_base": 2.0,
  "rf_signature": {
    "protocol": "OcuSync 3.0",
    "modulation": "FHSS + OFDM",
    "bandwidth_mhz": 40
  },
  "vulnerable_to": ["rf_jamming_2.4g_5.8g", "gnss_spoofing"],
  "resistant_to": ["laser_blinding_consumer_grade"],
  "typical_mission": ["reconnaissance", "smuggling", "aerial_photography"],
  "source": "OPEN_INTELLIGENCE_2024",
  "confidence": "MEDIUM"
}
```

```json
{
  "drone_id": "fpv-diy-5inch",
  "name": "DIY FPV 5-inch Racing Drone",
  "name_cn": "自组5寸竞速FPV",
  "category": "diy_fpv_quadcopter",
  "max_speed_ms": 45,
  "max_altitude_m": 4000,
  "max_endurance_min": 8,
  "max_payload_kg": 0.5,
  "frequency_bands": ["5.8GHz", "900MHz"],
  "gnss": [],
  "static_threat_base": 3.5,
  "rf_signature": {
    "protocol": "Analog / HDZero / DJI FPV",
    "modulation": "FM / Digital HD",
    "bandwidth_mhz": 20
  },
  "vulnerable_to": ["rf_jamming_5.8g", "rf_jamming_900mhz", "net_capture"],
  "resistant_to": ["gnss_spoofing", "protocol_hijack"],
  "typical_mission": ["strike", "kamikaze_attack", "reconnaissance"],
  "note": "高机动性+可携带爆炸物，威胁度远高于消费级",
  "source": "OPEN_INTELLIGENCE_2024",
  "confidence": "MEDIUM"
}
```

### 3.6 规则冲突消解策略

```
当多个规则同时匹配且给出不同建议时的优先级：

1. 规则层优先级：L2（条令） > L3（战术） > L4（经验）
   - 条令是硬约束，不可被经验覆盖

2. 同级规则中：salience 值高的优先
   - Drools 原生 salience 机制

3. 同 salience 且结果冲突：
   → 置信度降低至 0.5
   → 触发 LLM Agent 深度推理
   → 标记 "RULE_CONFLICT" 不确定性标签

4. 安全侧原则（Tie-break）：
   - 威胁等级冲突 → 取高值（宁可误报高威胁）
   - 策略冲突 → 取保守方案（附带损伤更小）
   - 人类可覆盖任何决策
```

---

## 四、置信度门控机制

### 4.1 门控流水线

```
传感器融合数据（每 50ms 一帧）
        │
        ▼
┌─────────────────────────────────┐
│ 阶段1: 规则引擎（Drools）        │  ← 100% 的帧都走这里
│ - L1 物理计算                    │
│ - L2 条令规则匹配                 │
│ - L3 战术规则匹配                 │
│ - L4 经验规则匹配                 │
│ - 输出：威胁等级 + 推荐策略       │
│   + 置信度分数 [0, 1]            │
│ - 附带输出：TOPSIS 五维分数      │  ← 预计算，随 situation 注入 LLM
│   + 已匹配规则列表 + 冲突信息     │
└──────────┬──────────────────────┘
           │
    置信度 ≥ 0.80? ─── Yes ──→ 进入「操作风险分级」→ 写入建议方案队列
           │
          No
           │
           ▼
┌─────────────────────────────────┐
│ 阶段2: 限流器检查                │
│ - 全局冷却计时器                  │
│ - 分钟调用计数                    │
│ - 同目标调用计数                  │
│ - ★ 威胁等级感知: 高威胁可打断冷却 │
└──────────┬──────────────────────┘
           │
      未达限流? ─── No ──→ 降级：使用保守策略（全频段压制等）+
           │                     标记 "未深度推理"
          Yes
           │
           ▼
┌─────────────────────────────────┐
│ 阶段3: LLM Agent 深度推理        │
│ - ReAct 模式: 思考→工具调用循环  │
│ - 最大 5 轮有效推理 / 10 秒超时   │
│ - situation 预注入 TOPSIS 等结果  │
│ - 输出：决策 + 解释              │
└──────────┬──────────────────────┘
           │
           ▼
┌─────────────────────────────────┐
│ 阶段4: ROE 硬约束过滤 (新增)      │  ← LLM 输出不直接入队
│ - 复用 Drools L2 ROE 规则        │
│ - 检查 LLM 建议是否违反交战规则   │
│ - 违规 → 拦截 + 标记 BLOCKED_BY_ROE│
│   + 降级为规则引擎保守方案         │
│ - 通过 → 继续                    │
└──────────┬──────────────────────┘
           │
           ▼
    进入「操作风险分级」→ 写入建议方案队列 → 指挥员确认/自动执行
```

**操作风险分级（新增）**：

| 风险等级 | 操作类型 | 示例 | 执行方式 |
|---------|---------|------|---------|
| **L-可逆** | 可逆电子对抗 | 射频干扰、GNSS诱骗、通信压制 | 自动执行 + 通知指挥员 |
| **M-半可逆** | 有附带影响的电子对抗 | 全频段压制（可能影响己方通信）、高功率微波 | 自动执行 + 强制通知 + 5秒内可撤销 |
| **H-不可逆** | 硬杀伤 | 激光摧毁、动能打击 | **强制人工确认**，不可自动执行 |

> **设计原则**：可逆操作不浪费指挥员带宽，不可逆操作守住安全底线。所有 LLM 建议经过 ROE 过滤 + 风险分级后才进入执行队列。

### 4.2 置信度计算模型

```java
/**
 * 置信度计算器
 * 综合考虑多个维度，输出 [0, 1] 的综合置信度
 */
public class ConfidenceCalculator {

    /**
     * 计算规则引擎输出的综合置信度
     */
    public double calculate(Target target, List<Rule> matchedRules, SensorStatus sensors) {

        // 冷启动阶段: 维度5 权重降为0，释放权重分配给维度1和维度2
        // 热启动后 (feedback_log >= 100条记录): 恢复完整六维权重
        boolean isColdStart = decisionFeedbackRepo.count() < 100;
        double[] weights = isColdStart
            ? new double[]{0.35, 0.30, 0.20, 0.15, 0.00, 0.00}  // 冷启动: 历史+一致性暂无参考
            : new double[]{0.25, 0.20, 0.15, 0.15, 0.10, 0.15};  // 热启动: 六维完整权重
        double[] scores = new double[6];

        // 维度1: 规则一致性分数
        scores[0] = ruleConsistency(matchedRules);

        // 维度2: 传感器数据质量
        scores[1] = sensorQuality(sensors);

        // 维度3: 目标识别确定性
        scores[2] = target.getMaxClassConfidence();

        // 维度4: 规则覆盖完整度
        scores[3] = ruleCoverage(matchedRules);

        // 维度5: 历史相似案例匹配度
        // 冷启动阶段默认值 0.5，权重为0时不参与计算
        scores[4] = historicalAccuracy(target);

        // 维度6 (新增): 行为-型号一致性
        // 比较目标运动特征与识别型号的已知参数范围
        // 不一致时 → 低分 → 降低综合置信度 → 触发 LLM
        scores[5] = behaviorTypeConsistency(target);

        double confidence = 0;
        for (int i = 0; i < 6; i++) {
            confidence += weights[i] * scores[i];
        }

        return Math.min(1.0, Math.max(0.0, confidence));
    }

    private double ruleConsistency(List<Rule> rules) {
        if (rules.size() <= 1) return 0.5; // 单规则或无规则，不确定性高
        // 统计不同 action 的数量，越一致分数越高
        long distinctActions = rules.stream()
            .map(Rule::getActionType)
            .distinct().count();
        return distinctActions == 1 ? 1.0 : 1.0 / distinctActions;
    }

    private double sensorQuality(SensorStatus sensors) {
        return sensors.getAllSnrRatios().stream()
            .mapToDouble(snr -> Math.min(1.0, snr / 30.0)) // SNR<30 线性映射
            .average().orElse(0.0);
    }

    private double ruleCoverage(List<Rule> rules) {
        Set<Integer> layersCovered = rules.stream()
            .map(Rule::getLayer)
            .collect(Collectors.toSet());
        return layersCovered.size() / 4.0; // 4层
    }

    private double historicalAccuracy(Target target) {
        // 查询 decision_feedback 表
        // 返回相似场景下规则方案被指挥员确认的比例
        // 冷启动阶段返回 0.5（中性值）
        return decisionFeedbackRepo.findAccuracyByTargetProfile(target);
    }

    /**
     * 维度6: 行为-型号一致性检查
     *
     * 防止识别模块自信犯错:
     *   识别为 consumer_quadcopter (max_speed=21m/s) 但实际 radial_speed=35m/s
     *   → 不一致 → 低分 → 降低综合置信度 → 强制触发 LLM
     *
     * 检查逻辑:
     *   1. 从知识库加载识别型号的已知参数范围 (max_speed, max_altitude, typical_freq_bands)
     *   2. 将目标实际参数与型号参数范围逐一比对
     *   3. 每项一致得 1.0，不一致得 0.0，取平均
     */
    private double behaviorTypeConsistency(Target target) {
        DroneKnowledgeEntry kb = knowledgeBase.findByName(target.getClassification().getDroneType());
        if (kb == null) return 0.5; // 未知型号，中性值

        int checks = 0;
        int passed = 0;

        // 检查1: 速度一致性
        if (kb.getMaxSpeedMs() > 0) {
            checks++;
            if (target.getRadialSpeedMs() <= kb.getMaxSpeedMs() * 1.15) passed++;
            // 允许 15% 容差（顺风/俯冲等）
        }

        // 检查2: 高度一致性
        if (kb.getMaxAltitudeM() > 0) {
            checks++;
            if (target.getPosition().getAltM() <= kb.getMaxAltitudeM() * 1.10) passed++;
        }

        // 检查3: 频段一致性
        if (kb.getFrequencyBands() != null && !kb.getFrequencyBands().isEmpty()
            && target.getRfSignature() != null) {
            checks++;
            double targetFreq = target.getRfSignature().getFrequencyMhz();
            boolean freqMatch = kb.getFrequencyBands().stream()
                .anyMatch(band -> frequencyInBand(targetFreq, band));
            if (freqMatch) passed++;
        }

        if (checks == 0) return 0.5; // 无检查项，中性值
        return (double) passed / checks;
    }
}
```

### 4.3 触发 LLM Agent 的六种条件

| # | 条件 | 触发逻辑 | 数据来源 |
|---|------|---------|---------|
| 1 | **EVT 开集识别** | `max(class_confidence) < 0.65` | 目标识别模块 |
| 2 | **多规则冲突** | 两条以上同优先级规则给出不同 action 且冲突不可自动消解 | 规则引擎冲突检测器 |
| 3 | **复合威胁** | 单个目标同时触发 ≥3 个威胁行为标签 | 威胁行为检测模块 |
| 4 | **资源不足** | `high_threat_target_count > available_device_count` | 设备管理模块 |
| 5 | **传感器数据质量低** | 主传感器 SNR 低于各自阈值 | 传感器自检状态 |
| 6 | **行为-型号不一致** | `behaviorTypeConsistency < 0.50`（目标运动特征与识别型号参数范围矛盾） | 置信度计算器维度6 |

### 4.4 限流器（威胁等级感知 + 紧急通道）

```java
/**
 * LLM Agent 调用限流器
 * 威胁等级感知：高威胁目标可打断冷却、享有更高配额
 */
@Component
public class LLMCallRateLimiter {

    // ===== 限流参数 =====
    private static final int MAX_CALLS_PER_MINUTE = 10;        // 全局每分钟软上限
    private static final int MAX_CALLS_HIGH_THREAT_BONUS = 5;  // 高威胁额外配额
    private static final long COOLDOWN_MS = 5_000;             // 常规全局冷却 5 秒
    private static final long COOLDOWN_HIGH_THREAT_MS = 1_000; // 高威胁冷却仅 1 秒

    // ===== 滑动窗口计数器 =====
    private final Deque<Long> globalCallTimestamps = new ConcurrentLinkedDeque<>();
    private final Map<String, Deque<Long>> targetCallTimestamps = new ConcurrentHashMap<>();
    private final AtomicLong lastCallTimestamp = new AtomicLong(0);

    /**
     * 检查是否允许一次新的 LLM 调用
     * @param targetId 目标ID
     * @param threatLevel 目标当前威胁等级 (1-5)，用于动态调整限流策略
     * @param urgent 是否为紧急调用（指挥员手动触发或威胁等级=5）
     * @return true = 允许调用, false = 触发限流
     */
    public synchronized boolean tryAcquire(String targetId, int threatLevel, boolean urgent) {
        long now = System.currentTimeMillis();
        boolean isHighThreat = threatLevel >= 4;

        // 紧急通道: 威胁等级5 或 指挥员手动触发 → 直接放行
        if (urgent || threatLevel >= 5) {
            lastCallTimestamp.set(now);
            globalCallTimestamps.addLast(now);
            return true;
        }

        // 检查1: 全局冷却（高威胁可打断）
        long effectiveCooldown = isHighThreat ? COOLDOWN_HIGH_THREAT_MS : COOLDOWN_MS;
        if (now - lastCallTimestamp.get() < effectiveCooldown) {
            logLimitReached("GLOBAL_COOLDOWN", targetId);
            return false;
        }

        // 检查2: 全局分钟计数 (滑动窗口)
        globalCallTimestamps.addLast(now);
        while (!globalCallTimestamps.isEmpty()
               && now - globalCallTimestamps.peekFirst() > 60_000) {
            globalCallTimestamps.pollFirst();
        }
        int effectiveLimit = MAX_CALLS_PER_MINUTE
            + (isHighThreat ? MAX_CALLS_HIGH_THREAT_BONUS : 0);
        if (globalCallTimestamps.size() > effectiveLimit) {
            logLimitReached("GLOBAL_MINUTE_LIMIT", targetId);
            return false;
        }

        // 检查3: 同目标调用计数（距离越近限制越松）
        int maxPerTarget = getMaxCallsByThreatLevel(threatLevel);
        Deque<Long> targetTimestamps = targetCallTimestamps
            .computeIfAbsent(targetId, k -> new ConcurrentLinkedDeque<>());
        targetTimestamps.addLast(now);
        while (!targetTimestamps.isEmpty()
               && now - targetTimestamps.peekFirst() > 60_000) {
            targetTimestamps.pollFirst();
        }
        if (targetTimestamps.size() > maxPerTarget) {
            logLimitReached("TARGET_LIMIT", targetId);
            return false;
        }

        // 通过所有检查
        lastCallTimestamp.set(now);
        return true;
    }

    /**
     * 同目标每分钟 LLM 调用上限 — 威胁等级越高限制越松
     */
    private int getMaxCallsByThreatLevel(int threatLevel) {
        switch (threatLevel) {
            case 5: return Integer.MAX_VALUE; // 极危：不限制
            case 4: return 6;                  // 高危：每 10 秒可推理一次
            case 3: return 3;                  // 中危：每 20 秒
            default: return 2;                 // 低危：每 30 秒
        }
    }

    /**
     * 获取限流状态（用于前端展示）
     */
    public RateLimitStatus getStatus() {
        long now = System.currentTimeMillis();
        return new RateLimitStatus(
            globalCallTimestamps.size(),
            MAX_CALLS_PER_MINUTE,
            Math.max(0, COOLDOWN_MS - (now - lastCallTimestamp.get())) / 1000.0
        );
    }

    private void logLimitReached(String reason, String targetId) {
        log.warn("LLM 调用被限流 | reason={} | targetId={}", reason, targetId);
    }
}
```

---

## 五、LLM Agent 内部设计

### 5.1 ReAct 推理循环

```
┌─────────────────────────────────────────────────┐
│               ReAct 循环 (最大5轮)                │
│                                                 │
│  System Prompt（注入当前态势摘要 + 可用工具列表）   │
│         │                                       │
│         ▼                                       │
│  ┌──────────────────────────┐                  │
│  │ 循环: while rounds < 5   │                  │
│  │   ┌────────────────────┐ │                  │
│  │   │ Think: 分析当前信息  │ │                  │
│  │   │ 确定还需要什么信息    │ │                  │
│  │   └────────┬───────────┘ │                  │
│  │            ▼              │                  │
│  │   ┌────────────────────┐ │                  │
│  │   │ Action: 调用Tool    │ │                  │
│  │   │ (search_rules /    │ │                  │
│  │   │  query_kb /         │ │                  │
│  │   │  check_devices /   │ │                  │
│  │   │  run_topsis, etc.) │ │                  │
│  │   └────────┬───────────┘ │                  │
│  │            ▼              │                  │
│  │   ┌────────────────────┐ │                  │
│  │   │ Observe: 解析Tool   │ │                  │
│  │   │ 返回结果             │ │                  │
│  │   └────────┬───────────┘ │                  │
│  │            ▼              │                  │
│  │   信息足够做决策?          │                  │
│  │   ┌───Yes──→ 跳出循环     │                  │
│  │   │                       │                  │
│  │   No → 继续下一轮         │                  │
│  │   └──────────────────────┘                  │
│  └──────────────────────────────────────────┘  │
│         │                                       │
│         ▼                                       │
│  输出最终决策 JSON（经 Schema 校验）              │
│         │                                       │
│         ▼                                       │
│  写入建议方案队列 → 指挥员确认 → 执行/驳回        │
└─────────────────────────────────────────────────┘
```

### 5.2 推理示例

```
=== Round 1 ===

Think: 目标 T-073 距离 420m，径向速度 22m/s，高度 80m 且在下降。
目前识别为"未知型号"(EVT置信度0.42)。规则引擎输出了威胁等级5
但置信度只有0.62，低于门控阈值0.80。我需要更多信息来确认。

Action: search_rules("未知型号 AND 高速逼近 AND 低高度")
Action: query_knowledge_base(entity_type="drone", query="高速低空目标 未知信号特征")

Observe(search_rules): 找到规则 L2-001（威胁等级5）
  和规则 L3-unknown-001（"未知型号默认按最高威胁等级处理"）
  — 但只有2条匹配规则，覆盖度低

Observe(query_kb): 未匹配到已知型号，最近邻是"DIY FPV 5寸竞速"
  (余弦相似度 0.41)，但相似度不够确认。

=== Round 2 ===

Think: 型号无法确认。我需要检查可用设备情况，以及是否有其他
同类型情况的历史案例。同时确认一下传感器数据质量是否影响了识别。

Action: check_device_status()
Action: search_rules("历史案例 OR 相似场景 OR 复盘记录")

Observe(check_device_status):
  - RF干扰器 #1: 可用，距离目标1.2km，覆盖范围3km
  - GNSS诱骗 #1: 可用，距离目标1.5km，覆盖范围5km
  - 激光 #1: 可用，距离目标0.8km，有效射程2km

Observe(search_rules): 历史案例库为空（冷启动阶段）。

=== Round 3 ===

Think: 信息已足够。虽然型号不确定，但运动特征极度危险：
- 距离 <500m（关键威胁范围）
- 速度 22m/s（远超消费级无人机）
- 高度在急剧下降
- 信号特征非消费级

结合规则 L2-001 和可用设备情况，做出以下决策...

→ 输出最终决策 JSON
```

### 5.3 六个 Tool 定义

> **设计变更说明**：`propose_new_rule` 已从实时 Tool 列表中移除，改为战后异步批处理（见阶段 2 规则回填机制）。新增 `predict_trajectory`（轨迹预测）、`simulate_action`（行动效果预测）、`retrieve_similar_cases`（相似案例动态检索）。TOPSIS 结果由规则引擎预注入 situation JSON，`run_topsis` 改为可选假设分析模式。

#### Tool 1: search_rules

```python
def search_rules(query: str, layers: list[int] = None) -> list[dict]:
    """
    检索规则库中的匹配规则。

    参数:
        query: 自然语言查询或关键词
        layers: 限定检索的层 [1,2,3,4]，None 表示全部

    返回:
        匹配的规则列表，每条规则包含:
        - rule_id, name, layer, content, action_type, confidence
    """
    # 实现：Elasticsearch 全文检索 + 按 layer 过滤
    # 降级：SQL LIKE 查询 + 简单分词
```

#### Tool 2: query_knowledge_base

```python
def query_knowledge_base(entity_type: str, query: str, top_k: int = 5) -> list[dict]:
    """
    查询知识库（无人机型号、历史战例、地形数据等）。

    参数:
        entity_type: "drone" | "scenario" | "terrain" | "em_environment"
        query: 查询文本
        top_k: 返回最相似的 K 个结果

    返回:
        匹配的实体列表，每条包含相似度分数
    """
    # 实现：FAISS 向量检索（将 query 转为 embedding 后检索）
    # embedding 模型：bge-small-zh（~100MB，CPU友好）
```

#### Tool 3: run_topsis（可选假设分析）

```python
def run_topsis(target_id: str,
                exclude_indicators: list[str] = None,
                custom_weights: dict = None) -> dict:
    """
    执行 IFN-TOPSIS 威胁评估计算（可选假设分析模式）。

    注意：规则引擎在触发 LLM 时已将默认 TOPSIS 结果预注入 situation JSON
    的 precomputed 字段。Agent 通常无需调用此 Tool，除非需要：
    - 排除某个异常传感器维度后重新计算
    - 自定义指标权重进行灵敏度分析

    参数:
        target_id: 目标唯一标识
        exclude_indicators: 排除的指标维度列表（如 ["sensor_snr"]）
        custom_weights: 自定义权重 {"distance": 0.35, "speed": 0.30, ...}

    返回:
        {
            "target_id": "...",
            "threat_score": 0.0-1.0,
            "threat_level": 1-5,
            "indicator_scores": {...},
            "note": "假设分析结果，非默认参数"
        }
    """
    # 实现：通过 HTTP 调用 Java 后端的 TOPSIS 服务，传入可选参数
```

#### Tool 4: check_device_status

```python
def check_device_status() -> list[dict]:
    """
    查询当前所有反制设备的实时状态。

    返回:
        设备列表，每条包含:
        - device_id, type, status (ONLINE/OFFLINE/BUSY/FAULT)
        - position (lat, lon, alt)
        - effective_range_m, current_target_id (if busy)
        - health_metrics: {snr, power_level, temperature}
    """
```

#### Tool 5: predict_trajectory（新增）

```python
def predict_trajectory(target_id: str, horizon_s: float = 30.0) -> dict:
    """
    基于当前运动状态做线性外推轨迹预测。

    参数:
        target_id: 目标唯一标识
        horizon_s: 预测时间范围（秒），默认 30s

    返回:
        {
            "target_id": "...",
            "current_position": {"lat": ..., "lon": ..., "alt_m": ...},
            "predicted_positions": [
                {"t_s": 5,  "lat": ..., "lon": ..., "alt_m": ..., "distance_to_defense_m": ...},
                {"t_s": 10, "lat": ..., "lon": ..., "alt_m": ..., "distance_to_defense_m": ...},
                {"t_s": 15, "lat": ..., "lon": ..., "alt_m": ..., "distance_to_defense_m": ...},
                {"t_s": 30, "lat": ..., "lon": ..., "alt_m": ..., "distance_to_defense_m": ...}
            ],
            "cpa_m": 420,           # 最近接近距离 (Closest Point of Approach)
            "cpa_time_s": 8.5,      # 到达 CPA 的预计时间
            "will_enter_no_fly": true,
            "no_fly_violation_time_s": 6.2
        }
    """
    # 实现: L1 物理定律层的简单运动学公式（线性外推 + 地球曲率修正）
    # 核心逻辑:
    #   lat(t) = lat_0 + v * cos(heading) * t / 111320.0
    #   lon(t) = lon_0 + v * sin(heading) * t / (111320.0 * cos(lat_0))
    #   alt(t) = alt_0 + v_vertical * t
    #   distance_to_defense = haversine(predicted_pos, defense_center)
```

#### Tool 6: simulate_action（新增）

```python
def simulate_action(target_id: str, action_type: str,
                    device_id: str = None) -> dict:
    """
    预测某反制行动对目标的效果。

    参数:
        target_id: 目标唯一标识
        action_type: 反制行动类型 (rf_jamming_*, gnss_spoofing, laser_destruction, ...)
        device_id: 指定设备（可选，None 则自动匹配最近可用设备）

    返回:
        {
            "target_id": "...",
            "action_type": "...",
            "device_id": "...",
            "estimated_effectiveness": 0.0-1.0,  # 综合效果估计
            "effectiveness_factors": {
                "range_factor": 0.85,       # 目标是否在设备有效范围内
                "type_match_factor": 0.90,  # 行动类型与目标脆弱性匹配度
                "jam_to_signal_ratio_db": 12.5,  # 干扰/信号比
                "obstruction_factor": 0.95,  # 地形/建筑物遮挡
            },
            "risks": {
                "civilian_interference_risk": "LOW",
                "friendly_comm_interference": false,
                "collateral_damage_risk": "NONE",
                "escalation_risk": "退化为仅惯性导航，目标可能继续直线飞行"
            },
            "predicted_outcome": "预计干扰后 3-8 秒内目标失控/返航，成功率约 78%",
            "limitations": [
                "目标可能已预设自主航线（无 GNSS 仍可飞行）",
                "5.8GHz FPV 信号在高功率压制下 95% 概率中断"
            ]
        }
    """
    # 实现: 查表 + 简化的物理模型
    # - 型号匹配: 查询知识库 drone_types.json 中的 vulnerable_to / resistant_to
    # - 距离衰减: 自由空间路径损耗公式 L_fs = 32.45 + 20*log10(d_km) + 20*log10(f_MHz)
    # - 干扰/信号比: JSR = ERP_jammer - ERP_signal + G_jammer - L_propagation
```

#### Tool 7: retrieve_similar_cases（新增 — 动态 Few-shot）

```python
def retrieve_similar_cases(situation_desc: str, top_k: int = 3) -> list[dict]:
    """
    从历史成功案例库中检索与当前态势最相似的案例（动态 Few-shot）。

    参数:
        situation_desc: 当前态势的自然语言描述
        top_k: 返回最相似的 K 个案例

    返回:
        [
            {
                "case_id": "case-xxx",
                "similarity": 0.87,
                "scenario": "未知型号 FPV 高速逼近指挥中心...",
                "decision_summary": "全频段压制 + GNSS诱骗，威胁等级5",
                "commander_verdict": "APPROVED",
                "outcome": "目标失控坠毁，距离指挥中心 320m",
                "key_lessons": "全频段压制对 DIY FPV 有效，但需预留激光作为最后防线"
            },
            ...
        ]
    """
    # 实现: FAISS 向量检索（用 bge-small-zh embedding）
    # 数据来源: decision_log + feedback_log (仅包含 verdict=APPROVED 的记录)
    # 冷启动阶段: 返回手工精选的 15 个静态 Few-shot 示例
```

> **已移除的 Tool**: `propose_new_rule` — 规则提议不再作为实时 Tool，改为战后批处理任务。见阶段 2 "规则回填机制"。

### 5.4 System Prompt 模板

```
你是一个反无人机指挥控制系统的辅助决策 AI，代号"决策参谋"。
你的职责是在规则引擎无法高置信度决策时，提供威胁评估和反制策略的推理建议。

## 身份与权限
- 你是一个**建议者**，不是执行者。你的所有输出必须经 ROE 硬约束校验后才能进入执行队列
- 你做出的每个判断必须**引用来源**（规则编号、知识库条目、计算结果）
- 如果你对任何判断不确定，**必须明确标注不确定性**

## 硬约束（不可违反）
- 民用区域 (`is_over_civilian_area: true`) + 威胁等级 < 5 → 禁止推荐激光/动能等硬杀伤手段
- 威胁等级 < 4 → 禁止推荐激光摧毁（ROE L2-020）
- 任何硬杀伤建议都将被 ROE 过滤层二次校验，违规建议会被自动拦截

## 可用工具
1. search_rules(query, layers) — 检索规则库
2. query_knowledge_base(entity_type, query) — 查询知识库（无人机型号/战例/地形/电磁环境）
3. run_topsis(target_id, exclude_indicators?, custom_weights?) — 可选假设分析（默认结果已预注入）
4. check_device_status() — 查询反制设备实时状态
5. predict_trajectory(target_id, horizon_s?) — 预测目标轨迹 + CPA 时间
6. simulate_action(target_id, action_type, device_id?) — 预测反制行动效果与风险
7. retrieve_similar_cases(situation_desc, top_k?) — 检索历史相似成功案例

## 推理规则
- 最多进行 **5 轮有效推理**（格式错误重试不消耗轮数，最多额外重试 2 次）
- 如果 5 轮后仍无法决策，输出当前最佳判断并标注 "INCOMPLETE_ANALYSIS"
- 优先使用工具获取信息，**不要凭空猜测**
- **对于威胁等级 ≥3 的目标，必须至少调用一次 predict_trajectory**
- 威胁等级判定必须遵守 L2 条令规则，不可自行调整阈值
- 策略推荐时必须遵守 ROE 约束
- 态势 JSON 的 `precomputed` 字段包含规则引擎的 TOPSIS 结果和已匹配规则列表，可直接使用

## 当前态势
{current_situation_json}

## 当前任务
{task_description}

## 输出格式
最终决策必须输出有效的 JSON，包含以下字段：
{
  "decision_id": "唯一标识",
  "target_id": "目标ID",
  "timestamp": "ISO8601时间",
  "threat_assessment": {
    "level": 1-5,
    "label": "低危|中危|高危|极高|极危",
    "confidence": 0.0-1.0,
    "reasoning": "推理过程摘要"
  },
  "recommended_action": {
    "primary": "主要策略",
    "secondary": "备选策略",
    "priority": 1-N,
    "risk_level": "L-可逆|M-半可逆|H-不可逆",
    "timing": "immediate|<30s|<60s|<5min",
    "reasoning": "策略选择理由",
    "escalation_condition": "升级条件"
  },
  "uncertainty_flags": ["标记不确定性的标签列表"]
}
```

### 5.5 ReAct 引擎核心代码

```python
"""
ReAct 推理循环引擎
~500 行，自研，无外部 Agent 框架依赖
"""
import json
import time
import re
from typing import Optional
from dataclasses import dataclass, field

from llama_cpp import Llama
from tools import ToolRegistry

@dataclass
class ReActConfig:
    max_rounds: int = 5
    timeout_seconds: float = 10.0
    model_path: str = "models/qwen3-8b-q4_k_m.gguf"
    n_ctx: int = 8192
    temperature: float = 0.1  # 低温度保证输出稳定

class ReActEngine:
    """ReAct 推理循环引擎"""

    def __init__(self, config: ReActConfig, tools: ToolRegistry):
        self.config = config
        self.tools = tools
        self.llm = Llama(
            model_path=config.model_path,
            n_ctx=config.n_ctx,
            n_threads=8,
            verbose=False,
        )

    def run(self, task: str, situation: dict) -> dict:
        """
        执行一次 ReAct 推理循环

        参数:
            task: 当前任务描述
            situation: 当前态势 JSON (含 precomputed 字段)

        返回:
            结构化决策 JSON
        """
        messages = [
            {"role": "system", "content": self._build_system_prompt(situation)},
            {"role": "user", "content": task},
        ]
        valid_rounds = 0       # 有效推理轮数（不含格式错误重试）
        retry_count = 0        # Schema 校验失败重试计数
        MAX_RETRIES = 2        # 最多额外重试 2 次（不消耗有效轮数）
        start_time = time.time()

        while valid_rounds < self.config.max_rounds:
            # 调用 LLM
            response = self.llm.create_chat_completion(
                messages=messages,
                temperature=self.config.temperature,
                max_tokens=1024,
                stop=["</decision>", "\n\n\n"],
            )
            assistant_msg = response["choices"][0]["message"]["content"]
            messages.append({"role": "assistant", "content": assistant_msg})

            # 解析: 提取 Action 或 Final Decision
            action = self._parse_action(assistant_msg)
            final = self._parse_final(assistant_msg)

            if final is not None:
                validated = self._validate_output(final)
                if validated:
                    # 超时兜底: 即使超时，已有结果优先返回
                    if time.time() - start_time > self.config.timeout_seconds:
                        validated["uncertainty_flags"].append("RESULT_AFTER_TIMEOUT")
                    return validated
                # Schema 校验失败 → 不消耗有效轮数，消耗重试配额
                retry_count += 1
                if retry_count > MAX_RETRIES:
                    return self._generate_schema_failure_decision(final)
                messages.append({
                    "role": "user",
                    "content": f"输出 JSON Schema 校验失败 (重试 {retry_count}/{MAX_RETRIES})。请按正确格式重新输出。"
                })
                continue

            if action is not None:
                valid_rounds += 1  # 有效的工具调用消耗一轮
                retry_count = 0    # 重置重试计数
                # 超时检查：执行工具前先检查
                if time.time() - start_time > self.config.timeout_seconds:
                    return self._generate_timeout_decision(messages)
                # 执行工具调用
                tool_name = action.get("tool")
                tool_args = action.get("args", {})
                tool_result = self.tools.execute(tool_name, tool_args)
                messages.append({
                    "role": "user",
                    "content": f"工具 [{tool_name}] 返回结果:\n{json.dumps(tool_result, ensure_ascii=False, indent=2)}"
                })
                continue

            # 既无 Action 也无 Final → 消耗一轮，提示继续
            valid_rounds += 1
            retry_count = 0
            messages.append({
                "role": "user",
                "content": "请继续推理。如果已收集足够信息，请输出最终决策。"
            })

        # 达到最大轮数 → 强制输出
        return self._generate_max_rounds_decision(messages)

    def _build_system_prompt(self, situation: dict) -> str:
        """构建 System Prompt + 注入态势"""
        tools_desc = self.tools.get_descriptions()
        situation_json = json.dumps(situation, ensure_ascii=False, indent=2)
        with open("prompt_templates/system_prompt.txt", "r", encoding="utf-8") as f:
            template = f.read()
        return template.format(
            current_situation_json=situation_json,
            tools_descriptions=tools_desc,
        )

    def _parse_action(self, text: str) -> Optional[dict]:
        """解析 LLM 输出的工具调用"""
        # 支持两种格式:
        # 格式1: Action: tool_name(args)
        # 格式2: ```json {"tool": "tool_name", "args": {...}} ```
        pattern1 = r"Action:\s*(\w+)\(([^)]*)\)"
        match = re.search(pattern1, text)
        if match:
            return {"tool": match.group(1), "args": self._parse_args(match.group(2))}

        pattern2 = r'"tool"\s*:\s*"(\w+)".*?"args"\s*:\s*(\{[^}]+\})'
        match = re.search(pattern2, text, re.DOTALL)
        if match:
            return {
                "tool": match.group(1),
                "args": json.loads(match.group(2)),
            }

        return None

    def _parse_final(self, text: str) -> Optional[dict]:
        """解析 LLM 输出的最终决策 JSON"""
        pattern = r'```json\s*\n(.*?)\n```'
        match = re.search(pattern, text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                return None
        return None

    def _validate_output(self, decision: dict) -> Optional[dict]:
        """对 LLM 输出进行 JSON Schema 校验"""
        required_fields = [
            "decision_id", "target_id", "threat_assessment",
            "recommended_action", "uncertainty_flags"
        ]
        for field in required_fields:
            if field not in decision:
                return None

        # 校验威胁等级范围
        level = decision["threat_assessment"].get("level")
        if not isinstance(level, int) or level < 1 or level > 5:
            return None

        # 校验置信度范围
        confidence = decision["threat_assessment"].get("confidence")
        if not isinstance(confidence, (int, float)) or confidence < 0 or confidence > 1:
            return None

        return decision

    def _generate_timeout_decision(self, messages: list) -> dict:
        """超时情况下生成降级决策 — 先尝试解析已有输出"""
        # Step 1: 尝试从最近的 assistant 消息中提取已有的有效决策
        for msg in reversed(messages):
            if msg.get("role") == "assistant":
                final = self._parse_final(msg["content"])
                if final and self._validate_output(final):
                    final["uncertainty_flags"] = final.get("uncertainty_flags", [])
                    final["uncertainty_flags"].append("RESULT_AFTER_TIMEOUT")
                    return final
        # Step 2: 无法解析已有输出 → 保守策略降级
        return {
            "decision_id": f"timeout-{int(time.time())}",
            "target_id": "UNKNOWN",
            "error": "TIMEOUT_NO_VALID_OUTPUT",
            "threat_assessment": {
                "level": 5,
                "label": "极危",
                "confidence": 0.0,
                "reasoning": "LLM推理超时且无法解析已有输出，采用保守策略：默认最高威胁等级"
            },
            "recommended_action": {
                "primary": "FALLBACK_CONSERVATIVE",
                "reasoning": "超时降级，使用保守策略（全频段压制），宁可过度反应不可漏过",
            },
            "uncertainty_flags": ["TIMEOUT", "DEGRADED_TO_CONSERVATIVE"],
        }

    def _generate_schema_failure_decision(self, last_attempt: dict) -> dict:
        """Schema 校验多次失败后的降级 — 保留已解析的部分信息"""
        return {
            "decision_id": f"schema-fail-{int(time.time())}",
            "target_id": last_attempt.get("target_id", "UNKNOWN"),
            "error": "SCHEMA_VALIDATION_EXHAUSTED",
            "threat_assessment": last_attempt.get("threat_assessment", {
                "level": 5, "label": "极危", "confidence": 0.0
            }),
            "recommended_action": {
                "primary": "FALLBACK_RULE_ENGINE",
                "reasoning": "LLM 输出格式校验失败，降级使用规则引擎方案",
            },
            "uncertainty_flags": ["SCHEMA_FAILURE", "DEGRADED_TO_RULE_ENGINE"],
        }

    def _generate_max_rounds_decision(self, messages: list) -> dict:
        """达到最大轮数后强制生成决策"""
        # 向 LLM 发送最终指令
        messages.append({
            "role": "user",
            "content": "已达到最大推理轮数。请基于当前所有信息输出最佳决策。"
        })
        response = self.llm.create_chat_completion(
            messages=messages,
            temperature=0.0,  # 最低温度保证确定性
            max_tokens=512,
        )
        final_text = response["choices"][0]["message"]["content"]
        decision = self._parse_final(final_text)
        if decision:
            return decision
        # 解析失败 → 返回降级决策
        return {
            "decision_id": f"maxrounds-{int(time.time())}",
            "error": "MAX_ROUNDS_REACHED",
            "uncertainty_flags": ["INCOMPLETE_ANALYSIS"],
        }
```

---

## 六、分阶段实现路线图

### 阶段 0：规则库冷启动（1-2周，可用云端 LLM）

**目标**：产出 50-100 条初始规则 + 20-30 个型号知识条目

```
阶段 0（可在有互联网的环境进行）
│
├── Step 0.1: 文档挖掘 (2-3天)
│   ├── 工具：Claude / GPT-4
│   ├── 输入：《软件设计0708》全文 + 公开反无人机资料
│   ├── 过程：逐段分析，提取所有隐含的决策规则
│   ├── Prompt 示例：
│   │   "阅读以下反无人机系统设计文档，提取其中隐含的
│   │    威胁评估和策略调度的决策规则。每条规则包括：
│   │    - 触发条件（if）
│   │    - 执行动作（then）
│   │    - 优先级建议
│   │    - 规则来源（文档章节号）"
│   └── 输出：规则候选清单（预计 50-80 条）
│
├── Step 0.2: 知识补全 (2-3天)
│   ├── 工具：Claude / GPT-4 + WebSearch
│   ├── 内容：
│   │   ├── 常见无人机型号参数（DJI全系、Autel、Fimi、DIY FPV等）
│   │   ├── 典型威胁场景模板（单机侦察、集群突袭、要地防卫、蜂群等）
│   │   ├── 常见频段与干扰策略对应表
│   │   └── 反制设备参数与适用场景
│   └── 输出：20-30 个型号条目 + 10-15 个场景模板
│
├── Step 0.3: 规则形式化 (2-3天)
│   ├── 将候选规则转化为 Drop .drl + JSON
│   ├── 人工逐条审核，三类标签：
│   │   ├── [已验证] ── 基于已知物理/条令事实
│   │   ├── [LLM生成-待实弹验证] ── LLM推断，需实弹/仿真验证
│   │   └── [占位-需补充] ── 确认有空缺但LLM也无法推断
│   ├── 编写规则冲突消解策略
│   └── 输出：初始规则库 v0.1
│
└── Step 0.4: 测试用例生成 (1-2天)
    ├── 每条规则生成 3-5 个测试场景
    ├── 包含：正常场景 + 边界场景 + 错误场景
    ├── 预期输出：200-400 个测试用例
    └── 格式：JSON，可直接用于自动化测试
```

### 阶段 1：规则引擎 + LLM Agent MVP（3-4周）

**目标**：可运行的离线决策系统

```
Week 1-2: 确定性引擎（不依赖 LLM）
│
├── Day 1-3: Spring Boot + Drools 集成
│   ├── Maven 依赖配置
│   ├── Drools 配置类（KieContainer 初始化）
│   ├── 导入阶段 0 的 .drl 规则文件
│   └── 编写 RuleEngineService（统一的规则执行入口）
│
├── Day 4-7: 规则热加载 + 管理 API
│   ├── POST   /api/rules/reload     — 重新加载规则
│   ├── GET    /api/rules/list       — 列出所有规则
│   ├── GET    /api/rules/{id}       — 查看规则详情
│   ├── PUT    /api/rules/{id}       — 更新规则
│   └── DELETE /api/rules/{id}       — 下线规则
│
├── Day 8-10: TOPSIS 算法实现
│   ├── IFN-TOPSIS（直觉模糊数改进TOPSIS）
│   ├── 五维威胁指标计算（距离/速度/意图/驻留时间/机型）
│   ├── 动态权重计算（时间熵+信息熵+AHP组合赋权）
│   └── 单元测试
│
└── Day 11-14: 策略匹配算法
    ├── 基于威胁等级+目标特征+设备可用性的匹配
    ├── 多目标优先级排序算法
    ├── 设备资源分配（匈牙利算法/贪心）
    └── 单元测试

Week 3-4: LLM Agent
│
├── Day 15-17: 基础环境搭建 + 模型能力验证
│   ├── llama.cpp 编译（Windows/Linux双平台）
│   ├── Qwen3-8B GGUF 模型下载 + 量化（Q4_K_M）
│   ├── bge-small-zh embedding 模型部署
│   ├── FAISS 索引构建
│   └── ★ 模型能力验证关卡（新增）:
│       ├── 用阶段 0 生成的 200-400 个测试用例做端到端评估
│       ├── 关键指标:
│       │   ├── 威胁等级判定准确率 (目标 ≥85%)
│       │   ├── 策略推荐 Top-3 准确率 (目标 ≥80%)
│       │   ├── ROE 合规率 (目标 100% — 配合硬约束过滤层)
│       │   └── 平均推理轮数 + 超时率
│       ├── 如果 Qwen3-8B 准确率 < 80%:
│       │   └── 触发备选方案: Qwen3-14B Q4_K_M (~9GB) 或 双模型策略
│       └── 输出: 模型能力验证报告（通过/不通过 + 错误分类分析）
│
├── Day 18-21: ReAct 引擎开发
│   ├── ReAct 循环引擎（按 5.5 节设计）
│   ├── Tool 注册与调度框架
│   ├── 5 个 Tool 的逐个实现与测试
│   └── 单元测试
│
├── Day 22-24: Prompt 工程
│   ├── System Prompt 模板设计（含 ROE 硬约束声明 + 操作风险分级要求）
│   ├── 静态 Few-shot 示例编写（15 个手工精选典型场景，作为冷启动保底）
│   ├── 动态 Few-shot 检索机制:
│   │   ├── Tool 7: retrieve_similar_cases — 从历史成功案例库 FAISS 检索
│   │   ├── 冷启动阶段: 返回静态 15 个示例
│   │   ├── 热启动后 (≥50 个 APPROVED 案例): 切换为动态检索 Top-3
│   │   └── 双轨制: 动态检索失败时 fallback 到静态模板
│   ├── 术语表（军事/反无人机专用术语注入）
│   ├── 反复迭代测试（用阶段 0 的测试用例）
│   └── LLM 输出质量评估脚本
│
├── Day 25-26: LLM服务封装
│   ├── FastAPI REST 服务
│   ├── POST /api/llm/decide — 决策请求
│   ├── GET  /api/llm/health  — 健康检查
│   ├── GET  /api/llm/status  — 限流状态
│   └── 优雅关闭 + 超时处理
│
└── Day 27-28: 置信度门控集成
    ├── ConfidenceCalculator 实现
    ├── 门控路由器（阶段1↔阶段2路由）
    ├── LLM 限流器集成
    └── 端到端集成测试
```

### 阶段 2：闭环打磨（2-3周）

**目标**：可部署使用的完整系统

```
Week 5-6: 审核闭环
│
├── 建议方案展示 UI
│   ├── LLM 建议方案卡片式展示
│   ├── 推理链可视化（Think→Action→Observe 时间线）
│   ├── 不确定性标签高亮
│   ├── 指挥员确认/驳回按钮
│   └── 驳回原因选择（快速选项 + 自由文本）
│
├── 规则回填机制（★ 改进：战后异步批处理 + 量化升级标准 + 冲突检测）
│   ├── 战后批处理任务（替代原实时 propose_new_rule Tool）:
│   │   ├── 每次作战/演习后自动触发
│   │   ├── 扫描所有 APPROVED 的 LLM 决策
│   │   ├── 聚类相似场景 → 提炼为规则草案
│   │   └── 合并重复/冲突草案 → 写入 pending_rules 表
│   ├── 规则冲突自动检测（新增）:
│   │   ├── 新规则写入前与现有 L2/L3 规则交叉验证
│   │   ├── 发现矛盾 → 标记 CONFLICT_WARNING + 列出冲突规则
│   │   └── 冲突未解决 → 规则状态保持 PENDING_REVIEW，不允许提升
│   ├── 量化升级标准（新增）:
│   │   ├── L4 → L3 升级条件（AND 关系）:
│   │   │   ├── 规则在 ≥5 个不同场景中被匹配
│   │   │   ├── 指挥员确认率 ≥80%
│   │   │   ├── 与现有 L2/L3 规则无冲突
│   │   │   └── 至少一条实弹/仿真验证通过记录
│   │   ├── L3 → L2 升级条件：
│   │   │   ├── 在 ≥20 个场景中验证，确认率 ≥95%
│   │   │   └── 经领域专家委员会审核
│   │   └── 自动降级条件：
│   │       └── 任意规则的驳回率 >30% 时自动降一级
│   ├── 规则效果追踪（新增）:
│   │   └── rule_performance 表：记录每条规则的匹配次数/确认次数/驳回次数/最近一次匹配时间
│   ├── 管理员审核界面（规则对比 + diff视图）
│   ├── 审核通过 → 写入 L4 → 自动测试
│   └── 满足升级条件 → 自动触发提升审查
│
└── 规则版本管理
    ├── Git 管理所有 .drl 和 .json 规则文件
    ├── 规则变更日志
    └── 规则回滚机制

Week 6-7: 压力验证
│
├── 性能测试
│   ├── 50 并发目标 + 规则引擎延迟 <10ms (P99)
│   ├── LLM 推理延迟 <5s (P99)
│   ├── LLM 限流上限饱和下的降级行为
│   └── 持续运行 24 小时稳定性测试
│
├── 容错测试
│   ├── LLM 服务不可用 → 纯规则引擎降级
│   ├── Elasticsearch 不可用 → SQL 降级检索
│   ├── FAISS 索引损坏 → 重建索引
│   └── 网络中断 → 本地缓存恢复
│
└── 准确性验证（Phase 1: 离线数据回放 + 阈值校准 + 驳回闭环）
    ├── 准备标注过的测试场景（领域专家标注的正确决策）
    ├── 对比：纯规则引擎 vs LLM Agent vs 混合架构
    ├── 指标：Top-1准确率、Top-3准确率、平均置信度、ROE合规率
    ├── ★ 置信度阈值校准实验（新增）:
    │   ├── 绘制不同阈值 (0.60~0.95) 下的 Precision-Recall 曲线
    │   ├── 找到 F1-Score 最优的截断点
    │   ├── ROI 分析: LLM 调用次数 vs 准确率提升
    │   └── 阈值作为可配置参数 `app.decision.confidence_threshold`，支持热更新
    ├── ★ 驳回后自动重决策闭环（新增）:
    │   ├── 指挥员驳回 → LLM 收到驳回原因 → 自动重新推理一轮
    │   ├── 重新推理不消耗常规限流配额（走紧急通道）
    │   ├── 修正方案重新进入 ROE 过滤 → 指挥员确认
    │   └── 统计: 驳回重决策后的二次确认率
    └── 错误分析：按类型分类统计（规则缺陷/模型幻觉/知识缺失/行为型号不一致漏检）
```

---

## 七、关键目录与文件结构

```
counteruav-decision-agent/
│
├── rule-engine/                          # 规则引擎模块 (Java / Spring Boot)
│   ├── pom.xml
│   ├── src/main/java/com/counteruav/
│   │   ├── RuleEngineApplication.java    # Spring Boot 启动类
│   │   ├── config/
│   │   │   └── DroolsConfig.java         # Drools KieContainer 配置
│   │   ├── controller/
│   │   │   ├── DecisionController.java   # 决策请求入口
│   │   │   └── RuleManageController.java # 规则管理 CRUD
│   │   ├── service/
│   │   │   ├── RuleEngineService.java    # 规则引擎核心执行
│   │   │   ├── ThreatEvaluator.java      # IFN-TOPSIS 威胁评估
│   │   │   ├── StrategyMatcher.java      # 策略匹配与资源调度
│   │   │   ├── ConfidenceGate.java       # 置信度计算 + 门控路由
│   │   │   └── LLMClientService.java     # LLM Agent HTTP 客户端
│   │   ├── model/
│   │   │   ├── Target.java               # 目标实体
│   │   │   ├── Device.java               # 设备实体
│   │   │   ├── DecisionRequest.java      # 决策请求 DTO
│   │   │   ├── DecisionResponse.java     # 决策响应 DTO
│   │   │   ├── TargetDecision.java       # 单目标决策
│   │   │   ├── ActionPlan.java           # 行动计划
│   │   │   └── ThreatLevel.java          # 威胁等级枚举
│   │   └── util/
│   │       ├── PhysicsLibrary.java       # L1 物理定律计算
│   │       └── RateLimiter.java          # LLM 调用限流器
│   │
│   └── src/main/resources/
│       ├── application.yml
│       ├── rules/
│       │   ├── l2-doctrine/
│       │   │   ├── threat_classification.drl
│       │   │   ├── threat_escalation.drl
│       │   │   ├── rules_of_engagement.drl
│       │   │   └── strategy_match.drl
│       │   └── l3-tactical/
│       │       ├── drone_type_strategy.json
│       │       ├── swarm_strategy.json
│       │       └── terrain_adaptation.json
│       └── kmodule.xml                   # Drools 模块配置
│
├── llm-agent/                            # LLM Agent 模块 (Python)
│   ├── requirements.txt
│   ├── src/
│   │   ├── main.py                       # FastAPI 服务入口
│   │   ├── react_engine.py               # ReAct 推理循环引擎
│   │   ├── config.py                     # 配置管理
│   │   ├── tools/
│   │   │   ├── __init__.py
│   │   │   ├── registry.py               # Tool 注册与调度
│   │   │   ├── search_rules.py           # Tool 1: 规则检索
│   │   │   ├── query_kb.py               # Tool 2: 知识库查询
│   │   │   ├── run_topsis.py             # Tool 3: TOPSIS 假设分析
│   │   │   ├── check_devices.py          # Tool 4: 设备状态查询
│   │   │   ├── predict_trajectory.py     # Tool 5: 轨迹预测 (新增)
│   │   │   ├── simulate_action.py        # Tool 6: 行动效果预测 (新增)
│   │   │   └── retrieve_cases.py         # Tool 7: 相似案例检索 (新增)
│   │   ├── prompt_templates/
│   │   │   ├── system_prompt.txt         # System Prompt 模板
│   │   │   ├── few_shot_examples.json    # Few-shot 示例
│   │   │   └── terminology.json          # 军事术语表
│   │   ├── output_validator.py           # JSON Schema 校验
│   │   └── rate_limiter.py               # 调用限流器
│   ├── models/
│   │   ├── qwen3-8b-q4_k_m.gguf          # 推理模型
│   │   └── bge-small-zh/                 # Embedding 模型
│   └── tests/
│       ├── test_react_engine.py
│       ├── test_tools.py
│       └── test_prompts.py
│
├── knowledge-base/                       # 知识库
│   ├── drone_types.json                  # 无人机型号库（JSON）
│   ├── scenario_templates.json           # 场景模板库
│   ├── frequency_bands.json              # 频段-策略映射表
│   ├── terrain_db/                       # 地形数据（可选）
│   │   └── site_templates.json
│   ├── em_environment/                    # 电磁环境知识
│   │   └── common_interference.json
│   └── faiss_index/                      # FAISS 向量索引
│       ├── drone_types.index
│       └── scenario_templates.index
│
├── sql/                                  # 数据库初始化脚本
│   ├── 001_init_schema.sql               # 基础表结构
│   ├── 002_pending_rules.sql             # L4 候选规则表
│   ├── 003_decision_log.sql              # 决策日志表
│   ├── 004_feedback_log.sql              # 反馈记录表
│   └── 005_rule_versions.sql             # 规则版本表
│
├── tests/                                # 集成测试
│   ├── rule_tests/                       # 规则单元测试
│   │   ├── test_threat_classification.json
│   │   ├── test_roe.json
│   │   └── test_strategy_match.json
│   ├── scenario_tests/                   # 端到端场景测试
│   │   ├── scenario_01_single_drone.json
│   │   ├── scenario_02_swarm_attack.json
│   │   └── scenario_03_civilian_area.json
│   └── llm_tests/                        # LLM Agent 测试用例
│       └── agent_test_cases.json
│
├── docs/                                 # 文档
│   ├── rule_catalog.md                   # 规则完整目录（可追溯索引）
│   ├── decision_flow.md                  # 决策流详细文档
│   ├── knowledge_base_schema.md          # 知识库 Schema 说明
│   └── operations_manual.md              # 运维操作手册
│
├── scripts/                              # 运维脚本
│   ├── init_knowledge_base.py            # 知识库初始化
│   ├── build_faiss_index.py             # FAISS 索引构建
│   ├── validate_rules.py                 # 规则一致性校验
│   ├── export_rules.py                   # 规则导出
│   └── benchmark.py                      # 性能基准测试
│
├── docker-compose.yml                    # 容器编排
└── README.md                             # 项目说明
```

---

## 八、核心接口定义

### 8.1 决策请求（规则引擎/LLM 统一入口）

```
POST /api/decision/assess
Content-Type: application/json
```

```json
{
  "request_id": "req-20260713-00142",
  "timestamp": "2026-07-13T14:32:10Z",
  "defense_center": {
    "lat": 39.9042,
    "lon": 116.4074,
    "alt_m": 50
  },
  "protected_zone": {
    "center": {"lat": 39.9042, "lon": 116.4074},
    "radius_m": 5000
  },
  "targets": [
    {
      "target_id": "T-073",
      "track_id": "TRK-073",
      "detection_time": "2026-07-13T14:30:00Z",
      "position": {"lat": 39.9100, "lon": 116.4100, "alt_m": 120},
      "velocity_ms": 22.0,
      "heading_deg": 270,
      "radial_speed_ms": -20.5,
      "classification": {
        "drone_type": "unknown",
        "max_class_confidence": 0.42,
        "is_evt_open_set": true,
        "top3_classes": [
          {"type": "diy_fpv_5inch", "confidence": 0.42},
          {"type": "consumer_quadcopter", "confidence": 0.21},
          {"type": "military_fixed_wing", "confidence": 0.15}
        ]
      },
      "threat_behaviors": [
        {
          "tag": "RAPID_APPROACH",
          "detected_at": "2026-07-13T14:31:00Z",
          "severity": 0.92
        },
        {
          "tag": "ALTITUDE_DIVE",
          "detected_at": "2026-07-13T14:31:50Z",
          "severity": 0.85
        },
        {
          "tag": "SIGNAL_ANOMALY",
          "detected_at": "2026-07-13T14:32:00Z",
          "severity": 0.70
        }
      ],
      "rf_signature": {
        "frequency_mhz": 5850,
        "bandwidth_mhz": 40,
        "modulation_type": "unknown_digital",
        "snr_db": 8.5
      },
      "is_over_civilian_area": false,
      "dwell_time_s": 120
    }
  ],
  "available_devices": [
    {
      "device_id": "RF-JAM-001",
      "type": "rf_jammer",
      "status": "ONLINE",
      "position": {"lat": 39.9050, "lon": 116.4080, "alt_m": 30},
      "effective_range_m": 3000,
      "frequency_coverage": ["2.4GHz", "5.8GHz", "900MHz"],
      "max_erp_w": 500,
      "current_target_id": null
    },
    {
      "device_id": "GNSS-SPOOF-001",
      "type": "gnss_spoofer",
      "status": "ONLINE",
      "position": {"lat": 39.9050, "lon": 116.4080, "alt_m": 30},
      "effective_range_m": 5000,
      "supported_constellations": ["GPS", "GLONASS", "BeiDou", "Galileo"],
      "current_target_id": null
    }
  ],
  "environment": {
    "terrain_type": "urban",
    "weather": "clear",
    "em_environment_noise_db": -85,
    "is_night": false
  },
  "mode": "auto"
}
```

### 8.2 决策响应

```json
{
  "request_id": "req-20260713-00142",
  "decision_id": "dec-20260713-00142",
  "timestamp": "2026-07-13T14:32:15Z",
  "source": "LLM_AGENT",
  "processing_time_ms": 3200,
  "decisions": [
    {
      "target_id": "T-073",
      "threat_assessment": {
        "level": 5,
        "label": "极危",
        "score": 0.94,
        "confidence": 0.78,
        "reasoning": "未知型号目标，径向速度22m/s高速逼近指挥中心（CPA<800m），同时触发高度骤降和信号异常两个威胁行为标签。采用保守策略：按极危处理。",
        "indicator_scores": {
          "distance_threat": 0.92,
          "speed_threat": 0.95,
          "intent_threat": 0.88,
          "dwell_time_threat": 0.30,
          "drone_type_threat": 0.50
        },
        "matched_rules": ["L2-001", "L2-010", "L3-unknown-001"],
        "rule_confidence": 0.62
      },
      "recommended_action": {
        "primary": {
          "action_type": "rf_jamming_full_band",
          "device_id": "RF-JAM-001",
          "params": {
            "frequency_range": "400MHz-6GHz",
            "power_level": "MAX",
            "modulation": "broadband_noise"
          }
        },
        "secondary": {
          "action_type": "gnss_spoofing",
          "device_id": "GNSS-SPOOF-001",
          "params": {
            "spoofing_mode": "gradual_offset",
            "target_constellation": "ALL"
          }
        },
        "avoid": ["laser_destruction"],
        "risk_level": "L-可逆",
        "auto_execute": true,
        "priority": 1,
        "timing": "immediate",
        "reasoning": "未知型号→无法确定最有效干扰频段→全频段压制保底。RF干扰覆盖所有常见频段，GNSS诱骗作为导航层第二道防线。避免激光摧毁因为目标类型不确定且非军事区。",
        "escalation_condition": "若干扰后5秒内目标未偏航或继续逼近至300m内，立即升级至激光摧毁（需指挥员确认，risk_level: H-不可逆）"
      },
      "uncertainty_flags": [
        "UNKNOWN_DRONE_TYPE",
        "SENSOR_SNR_LOW",
        "LLM_GENERATED_RECOMMENDATION"
      ],
      "needs_human_review": true,
      "review_reason": "LLM Agent 决策，源自信任度(0.62)低于门控阈值(0.80)，且包含 UNKNOWN_DRONE_TYPE 标记"
    }
  ]
}
```

### 8.3 反馈接口

```
POST /api/decision/feedback
Content-Type: application/json
```

```json
{
  "decision_id": "dec-20260713-00142",
  "target_id": "T-073",
  "commander_id": "CO-01",
  "timestamp": "2026-07-13T14:32:30Z",
  "verdict": "APPROVED",
  "override": null,
  "comments": "判断合理。全频段压制先手，观察效果后决定是否升级。"
}
```

```json
{
  "decision_id": "dec-20260713-00142",
  "target_id": "T-073",
  "commander_id": "CO-01",
  "timestamp": "2026-07-13T14:32:30Z",
  "verdict": "REJECTED",
  "override": {
    "action_type": "rf_jamming_5.8g_only",
    "device_id": "RF-JAM-001",
    "params": {
      "frequency_range": "5.725-5.875GHz",
      "power_level": "MEDIUM"
    }
  },
  "rejection_reason": "WRONG_FREQUENCY_BAND",
  "comments": "目标信号特征集中在5.8GHz FPV频段，全频段压制浪费功率且可能干扰己方通信。"
}
```

### 8.4 LLM Agent 内部接口

```
POST /api/llm/decide
Content-Type: application/json
```

```json
{
  "task_id": "task-20260713-00142",
  "trigger_reason": "LOW_CONFIDENCE",
  "trigger_detail": {
    "rule_confidence": 0.62,
    "trigger_conditions": ["UNKNOWN_DRONE_TYPE", "MULTI_BEHAVIOR_THREAT"],
    "target_id": "T-073"
  },
  "situation": {
    "...": "与决策请求相同的态势 JSON",
    "precomputed": {
      "topsis": {
        "threat_score": 0.94,
        "threat_level": 5,
        "indicator_scores": {
          "distance": 0.92, "speed": 0.95, "intent": 0.88,
          "dwell_time": 0.30, "drone_type": 0.50
        }
      },
      "matched_rules": [
        {"rule_id": "L2-001", "name": "ThreatLevel_CriticalRange_HighSpeed", "layer": 2},
        {"rule_id": "L2-010", "name": "ThreatEscalation_MultiBehavior", "layer": 2},
        {"rule_id": "L3-unknown-001", "name": "未知型号默认最高威胁", "layer": 3}
      ],
      "rule_confidence": 0.62,
      "confidence_breakdown": {
        "rule_consistency": 0.80,
        "sensor_quality": 0.28,
        "class_confidence": 0.42,
        "rule_coverage": 0.50,
        "historical_accuracy": 0.50,
        "behavior_type_consistency": 0.33
      },
      "conflicts": [],
      "behavior_type_consistency_issues": [
        "目标径向速度 22m/s 超过识别型号 'unknown' 无法校验",
        "建议关注: 速度特征与消费级无人机不匹配"
      ]
    }
  },
  "task_description": "目标 T-073 规则引擎置信度 0.62，低于阈值。请对 T-073 进行深度威胁评估并推荐反制策略。"
}
```

---

## 九、数据库表设计

### 9.1 决策日志表

```sql
CREATE TABLE decision_log (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    decision_id     VARCHAR(64) NOT NULL UNIQUE,
    request_id      VARCHAR(64) NOT NULL,
    target_id       VARCHAR(32) NOT NULL,
    source          VARCHAR(32) NOT NULL COMMENT 'RULE_ENGINE | LLM_AGENT | FALLBACK',
    trigger_reason  VARCHAR(128) COMMENT '触发LLM的原因',
    threat_level    TINYINT NOT NULL COMMENT '1-5威胁等级',
    threat_score    DECIMAL(4,3) COMMENT 'TOPSIS威胁分数',
    confidence      DECIMAL(4,3) NOT NULL COMMENT '决策置信度',
    primary_action  VARCHAR(64) NOT NULL,
    secondary_action VARCHAR(64),
    decision_json   JSON NOT NULL COMMENT '完整决策JSON',
    processing_time_ms INT NOT NULL,
    uncertainty_flags JSON COMMENT '不确定性标签列表',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_target_id (target_id),
    INDEX idx_created_at (created_at),
    INDEX idx_source (source),
    INDEX idx_confidence (confidence)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 9.2 反馈记录表

```sql
CREATE TABLE feedback_log (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    decision_id     VARCHAR(64) NOT NULL,
    target_id       VARCHAR(32) NOT NULL,
    commander_id    VARCHAR(32) NOT NULL,
    verdict         VARCHAR(16) NOT NULL COMMENT 'APPROVED | REJECTED | MODIFIED',
    override_json   JSON COMMENT '指挥员覆盖的方案(JSON)',
    rejection_reason VARCHAR(64) COMMENT '驳回原因编码',
    comments        TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_decision_id (decision_id),
    INDEX idx_verdict (verdict),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 9.3 候选规则表

```sql
CREATE TABLE pending_rules (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    proposal_id     VARCHAR(64) NOT NULL UNIQUE,
    source_decision_id VARCHAR(64) COMMENT '触发此规则提议的决策ID',
    rule_text       TEXT NOT NULL COMMENT '规则自然语言描述',
    rule_json       JSON COMMENT '结构化规则(JSON)',
    rule_drl        TEXT COMMENT 'Drools规则(.drl格式)',
    reason          TEXT COMMENT '提议理由',
    layer           TINYINT NOT NULL DEFAULT 4 COMMENT '目标层级 L3/L4',
    status          VARCHAR(32) NOT NULL DEFAULT 'PENDING_REVIEW'
                    COMMENT 'PENDING_REVIEW | APPROVED | REJECTED | PROMOTED_TO_L3',
    reviewer_id     VARCHAR(32) COMMENT '审核人ID',
    review_comment  TEXT,
    promoted_version INT DEFAULT 0,
    proposal_source VARCHAR(32) NOT NULL COMMENT 'LLM_AGENT | COMMANDER | AUTO_ANALYSIS',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    reviewed_at     TIMESTAMP,
    INDEX idx_status (status),
    INDEX idx_layer (layer),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 9.4 规则版本表

```sql
CREATE TABLE rule_versions (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    rule_id         VARCHAR(64) NOT NULL,
    version         INT NOT NULL,
    layer           TINYINT NOT NULL COMMENT '1-4',
    file_path       VARCHAR(256) NOT NULL COMMENT 'Git仓库中的文件路径',
    content_hash    VARCHAR(64) NOT NULL COMMENT 'SHA256',
    commit_message  TEXT,
    changed_by      VARCHAR(32),
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_rule_version (rule_id, version),
    INDEX idx_rule_id (rule_id),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 9.5 威胁评估历史表

```sql
CREATE TABLE threat_history (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    target_id       VARCHAR(32) NOT NULL,
    track_id        VARCHAR(32) NOT NULL,
    timestamp       TIMESTAMP NOT NULL COMMENT '评估时间点',
    position_lat    DECIMAL(10,7),
    position_lon    DECIMAL(10,7),
    position_alt_m  DECIMAL(8,2),
    velocity_ms     DECIMAL(6,2),
    heading_deg     DECIMAL(6,2),
    radial_speed_ms DECIMAL(6,2),
    drone_type      VARCHAR(64),
    class_confidence DECIMAL(4,3),
    threat_level    TINYINT,
    threat_score    DECIMAL(4,3),
    threat_tags     JSON COMMENT '威胁行为标签列表',
    decision_source VARCHAR(32),
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_target_ts (target_id, timestamp),
    INDEX idx_track_ts (track_id, timestamp)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
COMMENT='威胁评估历史快照，用于回放分析和模型优化';
```

---

## 十、风险与对策

| # | 风险 | 影响 | 概率 | 对策 |
|---|------|------|------|------|
| 1 | **LLM 幻觉** — 给出逻辑通顺但事实错误的建议 | 指挥员误判，可能导致错误处置 | 中 | ①强制人工确认 ②输出必须引用规则/知识库来源 ③不确定性自动标注 ④低温度(0.1)推理 |
| 2 | **LLM 推理超时** — 超过 10 秒未完成推理 | 错过处置窗口 | 低 | ①格式错误不消耗轮数 ②超时优先解析已有输出（不丢弃有效推理）③超时兜底采用保守策略（全频段压制，宁可过度反应） |
| 3 | **规则库初期稀疏** — 大量触发 LLM，频繁限流 | 决策延迟上升，可能遗漏威胁 | 高 | ①阶段 0 尽量生成足量规则(50-100条) ②威胁等级感知限流器（高威胁优先）③紧急通道可打断冷却 |
| 4 | **LLM 服务宕机** — Python 进程崩溃/模型加载失败 | LLM 决策通道不可用 | 低 | ①纯规则引擎独立运行，不受影响 ②健康检查 + 自动重启 ③降级标记自动附加 |
| 5 | **规则冲突未检测** — 多条规则给出矛盾建议 | 低置信度但可能未被正确路由到 LLM | 低 | ①Drools 冲突检测器 ②ConfidenceCalculator 中的 ruleConsistency 维度 ③冲突自动触发 LLM ④规则写入前交叉验证现有规则 |
| 6 | **llama.cpp 在国产芯片上兼容性问题** | 无法部署 | 低 | ①预留 ONNX Runtime 备选方案 ②CPU 推理作为最终降级 ③阶段 1 早期先做硬件兼容性验证 + 模型能力验证 |
| 7 | **Qwen3 对军事/反无人机术语理解不足** | LLM 推理质量下降 | 中 | ①术语表注入 System Prompt ②15 个静态 + 动态检索 Few-shot ③持续收集驳回案例微调模型 ④模型验证关卡不通过则换 Qwen3-14B |
| 8 | **知识库信息过时** — 新型号无人机不断出现 | EVT 开集识别率上升，LLM 调用增多 | 中 | ①定期情报更新流程 ②EVT 检测到的新型号自动归档 + 通知管理员 ③规则库持续增长覆盖 |
| 9 | **冷启动无历史数据** — HistoricalAccuracy 和行为-型号一致性维度无参考 | 置信度计算偏差 | 高(初期) | ①冷启动阶段该两维度权重降为 0，释放权重给规则一致性+传感器质量 ②随 feedback_log ≥100 条记录后自动切换完整六维权重 ③动态阈值的初始值使用校准实验确定 |
| 10 | **识别模块自信犯错** — 型号识别错误且置信度高 | 决策链全程无 LLM 审核，错误策略直接执行 | 中(新增) | ①行为-型号一致性检查（置信度维度6）②不一致时强制触发 LLM ③传感器交叉验证（雷达 RCS vs 光电分类） |
| 11 | **单一开发者瓶颈** — 所有模块依赖一人 | 进度风险，关键人力风险 | 中 | ①三阶段串行推进，优先保证核心可用 ②充分利用 Phase 0 云端 LLM 加速规则库建设 ③代码和设计文档完善，降低后续交接成本 |

---

## 十一、总结

### 三个核心问题的答案

| 问题 | 答案 |
|------|------|
| **选什么 Agent？** | **混合架构**：Drools 规则引擎（处理 80%+ 常规决策，<10ms）+ 自研 ReAct LLM Agent 搭载 Qwen3-8B（处理 20% 低置信度/异常案例，2-5s），通过六维置信度门控 + ROE 硬约束过滤 + 操作风险分级三重保障安全 |
| **如何建立规则库？** | **四层分层**：L1 物理定律(Java代码) → L2 作战条例(Drools .drl) → L3 战术策略(JSON) → L4 经验优化(战后异步批处理)。阶段 0 用云端 LLM 从文档挖掘 + 常识补全生成初始规则，人工审核标记置信度标签。战后批处理→冲突检测→量化标准升级（≥5次匹配+≥80%确认率 L4→L3）形成闭环 |
| **如何从零开始？** | **三阶段 7-10 周**：阶段 0（1-2周）规则冷启动 → 阶段 1（3-4周）规则引擎 + LLM Agent MVP（含模型验证关卡）→ 阶段 2（2-4周）审核闭环 + 阈值校准 + 压力验证。总计 7-10 周可由单一开发者完成可运行系统 |

### 关键设计决策回顾

```
架构:  混合（规则引擎 + LLM）     ── 不是纯规则，不是纯LLM
模型:  Qwen3-8B + llama.cpp      ── 离线、中文、CPU可跑（含模型验证关卡）
框架:  自研 ReAct (~600 行)       ── 不依赖 LangGraph/CrewAI
                                 ── 改进: 格式错误不消耗轮数 + 超时优先解析已有输出
门控:  置信度阈值（可配置+校准）   ── 六种触发条件，六维置信度计算
                                 ── + 行为-型号一致性检查（防识别模块自信犯错）
过滤:  ROE 硬约束过滤层 (新增)     ── LLM 输出不直接入队，经 Drools L2 二次校验
                                 ── 违规建议自动拦截 + 降级
执行:  操作风险分级 (新增)        ── 可逆操作自动执行，半可逆自动+可撤销，不可逆强制确认
输出:  建议方案                   ── 不直接下发武器，ROE 硬约束保底
规则:  四层分层 + 量化升级标准     ── 匹配≥5次+确认率≥80%+无冲突 L4→L3
                                 ── 规则提议改为战后异步批处理（非实时 Tool）
限流:  威胁等级感知 (改进)        ── 高威胁可打断冷却 + 紧急通道 + 随距离递减配额
检索:  动态 Few-shot (新增)       ── 双轨制: 冷启动静态模板 + 热启动 FAISS 动态检索
Tool:  6+1 个 (改进)             ── +predict_trajectory +simulate_action +retrieve_cases
                                 ── -propose_new_rule (改为战后批处理)
                                 ── run_topsis 改为可选假设分析（结果预注入）
实现:  三阶段串行                  ── 唯一开发者，6-9周可运行
```

---

> **文档版本**: v1.0  
> **生成日期**: 2026-07-13  
> **基于文档**: 《软件设计0708》反无人机一体化指挥控制系统软件设计  
> **适用范围**: 数据分析服务中心 — 威胁评估与决策优化模块的离线 Agent 实现
