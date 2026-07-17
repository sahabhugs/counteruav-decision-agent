# 反无人机辅助决策系统 - 规则目录

> 版本: 1.0.0 | 最后更新: 2026-07-13 | 密级: 内部

---

## 目录

1. [系统概述](#1-系统概述)
2. [L1 物理公式表](#2-l1-物理公式表)
3. [L2 Drools规则详解](#3-l2-drools规则详解)
4. [L3 JSON策略规则](#4-l3-json策略规则)
5. [规则依赖图](#5-规则依赖图)
6. [覆盖矩阵](#6-覆盖矩阵)
7. [附录](#7-附录)

---

## 1. 系统概述

### 1.1 四层规则体系

本系统采用分层规则架构，从确定性物理计算到自适应LLM推理，逐层递进：

```
┌─────────────────────────────────────────────────────────────┐
│  L4: 元规则层 (Meta-Rules)                                   │
│  LLM Agent 自适应推理，处理未知/异常场景                       │
│  触发条件: L3策略置信度 < 阈值 或 场景未覆盖                   │
├─────────────────────────────────────────────────────────────┤
│  L3: 策略规则层 (Strategic Rules)                            │
│  JSON结构化规则，场景化策略模板                                │
│  触发条件: L2规则链完成，威胁确认                              │
├─────────────────────────────────────────────────────────────┤
│  L2: 战术规则层 (Tactical Rules)                             │
│  Drools .drl 文件，确定性战术逻辑                              │
│  触发条件: L1计算结果 + 传感器事件                             │
├─────────────────────────────────────────────────────────────┤
│  L1: 物理层规则 (Physics Rules)                              │
│  Python函数，运动学/电磁学/光学基础计算                         │
│  触发条件: 传感器原始数据输入                                  │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 各层职责

| 层级 | 名称 | 实现方式 | 确定性 | 更新频率 | 典型延迟 |
|------|------|---------|--------|---------|---------|
| L1 | 物理层 | Python函数 | 100% 确定性 | 算法升级时 | <1ms |
| L2 | 战术层 | Drools .drl | 100% 确定性 | 战术条令变更时 | 5-50ms |
| L3 | 策略层 | JSON配置 | 确定性(模板) | 作战场景扩展时 | 10-100ms |
| L4 | 元规则层 | LLM Agent | 概率性 | 模型升级/提示词优化时 | 500-3000ms |

### 1.3 规则执行流程

```
传感器数据 → L1物理计算 → L2战术规则匹配 → L3策略选择 → L4元规则(如需) → 决策输出
    │              │                │                │               │
    │              │                │                │               │
    ▼              ▼                ▼                ▼               ▼
 位置/速度/     威胁等级/        处置方案/        优化建议/       最终命令
 频率/功率      CM选择           协同策略         风险评估
```

---

## 2. L1 物理公式表

### 2.1 运动学与定位公式

| 公式ID | 公式名称 | 公式 | 参数说明 | 应用场景 | 精度 |
|--------|---------|------|---------|---------|------|
| PHY-001 | 目标距离计算 | `d = 2R·arcsin(√(hav(Δφ) + cos(φ₁)cos(φ₂)·hav(Δλ)))`<br>快速近似: `d ≈ √((Δlat·111320)² + (Δlon·111320·cos(φₘ))²)` | φ₁,φ₂: 纬度(rad); λ₁,λ₂: 经度(rad); R=6371000m; φₘ: 平均纬度 | 计算传感器到目标的水平距离; 精确模式用于远距离(>10km), 快速模式用于视距内(<10km) | 精确: ±0.3%<br>快速: ±0.5% |
| PHY-002 | 目标速度矢量 | `v = v_doppler / cos(θ)`<br>`v = Δd/Δt` (位置微分)<br>融合: `v_fused = α·v_doppler + (1-α)·v_pos` | v_doppler: 雷达多普勒速度; θ: 雷达视线与目标运动方向夹角; α: 卡尔曼增益 | 威胁评估输入; 拦截弹道计算; 目标意图推断 | ±1.5m/s (融合后) |
| PHY-003 | 拦截几何 | CBDR条件: `dB/dt = 0 且 dR/dt < 0`<br>拦截点: `P_intercept = P_target + v_target · t_intercept`<br>预计拦截时间: `t_intercept = R / (v_interceptor - v_target·cos(θ))` | B: 方位角; R: 距离; v_interceptor: 拦截器速度; v_target: 目标速度 | 判断是否处于碰撞航线; 计算最优拦截点; 动能拦截可行性评估 | ±2° (方向角)<br>±3s (时间) |
| PHY-004 | 射频链路预算 | `P_rx = P_tx + G_tx + G_rx - 20log₁₀(4πd/λ) - L_atm - L_misc`<br>或简化为: `P_rx(dBm) = P_tx(dBm) + G_tx(dBi) + G_rx(dBi) - FSPL(dB)`<br>`FSPL = 32.45 + 20log₁₀(f_MHz) + 20log₁₀(d_km)` | P_tx: 发射功率; G_tx/G_rx: 天线增益; d: 距离; λ: 波长; L_atm: 大气衰减; FSPL: 自由空间路径损耗 | 评估目标通信链路质量; 判断干扰所需功率; GNSS信号强度估算 | ±3dB (统计) |

### 2.2 电子对抗公式

| 公式ID | 公式名称 | 公式 | 参数说明 | 应用场景 | 精度 |
|--------|---------|------|---------|---------|------|
| PHY-005 | 干扰有效距离 | `JSR = P_j + G_j - P_s - G_s + 20log₁₀(d_s/d_j) + L_processing`<br>有效干扰条件: `JSR ≥ JSR_min`<br>`d_j_max = d_s · 10^((P_j+G_j-P_s-G_s+L_processing-JSR_min)/20)` | JSR: 干信比(dB); P_j/P_s: 干扰/信号功率; G_j/G_s: 干扰/信号天线增益; d_s: 信号源距离; d_j: 干扰源距离; JSR_min: 最小干信比门限(通常8-12dB) | 确定干扰机有效作用范围; 干扰功率选择; 部署位置优化 | ±5dB (受多径影响) |
| PHY-006 | GNSS欺骗信号功率 | `P_spoof_min = P_authentic + 3dB` (压制比)<br>信号传播: `P_rx_spoof = P_tx_spoof + G_tx_spoof - FSPL_spoof - L_atm`<br>成功条件: `P_rx_spoof > P_rx_authentic · γ` | P_authentic: 真实GPS信号(-130dBm典型值); γ: 压制系数(2-5); FSPL_spoof: 欺骗信号自由空间损耗 | GNSS欺骗可行性评估; 欺骗功率设定; 欺骗范围估算 | ±4dB |
| PHY-007 | 激光毁伤功率密度 | `I = P_laser · τ_atm / (π · (d·tan(θ_div/2))²)`<br>`τ_atm = exp(-α·d)`<br>毁伤门限: `I ≥ I_damage` (按目标类型) | P_laser: 激光功率(W); θ_div: 发散角(rad); d: 距离(m); τ_atm: 大气透过率; α: 衰减系数(km⁻¹); I_damage: 毁伤阈值(W/cm²) | 确定激光有效毁伤距离; 功率需求计算; 照射时间估算 | ±15% (大气变化) |
| PHY-008 | 光学探测距离 | `R = (D · f_objective · √(C_target · τ_atm · U · SNR)) / (N_pixels · √(fps))`<br>基于Johnson准则: 探测→1对线, 识别→4对线, 辨认→8对线 | D: 目标特征尺寸; f_objective: 物镜焦距; C_target: 目标对比度; U: 场景照度; SNR: 信噪比; N_pixels: 目标像素数 | 光电传感器部署评估; 白天/夜间探测能力; 识别vs辨认距离判断 | ±20% |

### 2.3 探测与拦截公式

| 公式ID | 公式名称 | 公式 | 参数说明 | 应用场景 | 精度 |
|--------|---------|------|---------|---------|------|
| PHY-009 | 雷达探测概率 | Swerling I/II: `P_d = (1 + 1/(n·SNR))^(n-1) · exp(-V_T/(1+SNR))`<br>Swerling III/IV: `P_d ≈ exp(-V_T/(1+SNR/2)) · [1 + (n·SNR/2)·V_T/((n-2)·(1+SNR/2)²)]` | n: 脉冲积累数; SNR: 信噪比; V_T: 检测门限; Swerling模型: I=慢起伏, II=快起伏, III/IV=χ²分布 | 雷达检测性能评估; 虚警率设定; 雷达部署间距计算 | ±5% (理论)<br>±15% (实际) |
| PHY-010 | 动能拦截弹道 | 前置追踪: `θ_lead = arcsin(v_target·sin(θ_target) / v_interceptor)`<br>`t_flight = R / √(v_interceptor²+v_target²-2v_interceptor·v_target·cos(θ_target))`<br>`P_impact = P_interceptor(t_flight)` | v_interceptor: 拦截器速度; v_target: 目标速度; θ_target: 目标运动方向角; θ_lead: 前置角 | 网枪/捕捉器发射时机; 拦截器预置点计算; 命中概率评估 | ±5m (CEP) |
| PHY-011 | 声学探测距离 | `SPL_received = SPL_source - 20log₁₀(d) - α_air·d + DI`<br>检测条件: `SPL_received > N_ambient + SNR_min`<br>`d_max = f(SPL_source, N_ambient, SNR_min)` | SPL: 声压级(dB); α_air: 空气吸收系数(0.5-2dB/100m); DI: 指向性指数; N_ambient: 环境噪声; SNR_min: 最小信噪比(6dB) | 声学传感器部署; 城市环境特殊考虑; 多阵列定位精度 | ±30m (城市)<br>±10m (开阔) |
| PHY-012 | 电池续航估算 | `T_flight = C_battery · η / (P_hover · (1 + (v/v_max)²))`<br>`P_hover = (m·g)^1.5 / √(2·ρ·A_rotor)`<br>`R_max = v_best · T_flight` | C_battery: 电池容量(Wh); η: 效率(0.7-0.85); P_hover: 悬停功率; m: 质量; ρ: 空气密度; A_rotor: 旋翼面积; v: 飞行速度 | 目标活动范围预测; 续航能力评估; 返航点估算 | ±15% (机型差异) |

---

## 3. L2 Drools规则详解

### 3.1 威胁评估规则组 (THREAT)

#### THREAT-001: 初始威胁评估

| 属性 | 内容 |
|------|------|
| **规则名称** | 初始威胁评估 (Initial Threat Assessment) |
| **Salience** | 100 |
| **Agenda-Group** | `threat-assessment` |
| **触发条件 (when)** | `DroneFact(type != null, speed != null, altitude != null)` 到达工作内存，且无现有威胁等级记录 |
| **执行动作 (then)** | 1. 根据无人机类型查找基础威胁等级 (消费级→1, 商用级→2, 军用小型→3, 军用中型→4, 大型固定翼→5)<br>2. 根据速度修正: 速度>30m/s→+1级, 速度>60m/s→+2级<br>3. 根据高度修正: 高度<30m且接近边界→+1级<br>4. 插入 `ThreatAssessmentFact` 并设置初始等级 |
| **依赖规则** | PHY-001, PHY-002 |
| **示例场景** | 雷达检测到DJI Mavic 3以12m/s在100m高度飞行 → 初始威胁等级=1 (消费级+无修正) |

#### THREAT-002: 禁飞区升级

| 属性 | 内容 |
|------|------|
| **规则名称** | 禁飞区威胁升级 (Restricted Zone Escalation) |
| **Salience** | 90 |
| **Agenda-Group** | `threat-assessment` |
| **触发条件 (when)** | `GeoFenceEvent(droneId != null, zoneType == "RESTRICTED" or "ALERT", entered == true)` 且存在对应的 `DroneFact` |
| **执行动作 (then)** | 1. 进入RESTRICTED区 → 威胁等级立即升至4<br>2. 进入ALERT区 → 威胁等级+2 (不超过5)<br>3. 进入机场净空区 → 威胁等级升至5<br>4. 记录 `ZoneViolationRecord` 含GPS坐标和时间戳<br>5. 触发最高优先级告警 |
| **依赖规则** | THREAT-001, PHY-001 |
| **示例场景** | 未知无人机进入机场5km净空区 → 威胁等级自动升至5，触发ALARM_CRITICAL |

#### THREAT-003: 有效载荷检测升级

| 属性 | 内容 |
|------|------|
| **规则名称** | 有效载荷威胁升级 (Payload Detection Escalation) |
| **Salience** | 85 |
| **Agenda-Group** | `threat-assessment` |
| **触发条件 (when)** | `PayloadDetectionEvent(droneId != null, payloadType != null)` 匹配到可疑载荷类型 |
| **执行动作 (then)** | 1. 无载荷 → 威胁等级不变<br>2. 摄像头/光学设备 → +1级<br>3. 爆炸物/危险品 → +3级 (或直接升至5)<br>4. 未知容器/包裹 → +2级<br>5. 电子战设备 → +3级<br>6. 更新 `ThreatAssessmentFact.payloadThreat` |
| **依赖规则** | THREAT-001 |
| **示例场景** | 光电吊舱检测到无人机携带疑似爆炸物挂载 → 威胁等级从2升至5 |

#### THREAT-004: 高价值目标接近升级

| 属性 | 内容 |
|------|------|
| **规则名称** | 高价值目标接近升级 (High Value Asset Proximity) |
| **Salience** | 80 |
| **Agenda-Group** | `threat-assessment` |
| **触发条件 (when)** | `ProximityEvent(droneId != null, assetType != null, distance < threshold)` |
| **执行动作 (then)** | 1. 接近VIP (距离<500m) → 威胁等级+2<br>2. 接近关键基础设施 (距离<1000m) → 威胁等级+1<br>3. 接近军事设施 (距离<3000m) → 威胁等级+2<br>4. 接近人群密集区 (距离<200m) → 威胁等级+3<br>5. 插入 `AssetProximityAlert` 含资产类型和距离 |
| **依赖规则** | THREAT-001, PHY-001 |
| **示例场景** | 威胁等级2的无人机接近核电站1.5km → 升级至4 |

#### THREAT-005: 威胁降级规则

| 属性 | 内容 |
|------|------|
| **规则名称** | 威胁降级评估 (Threat De-escalation) |
| **Salience** | 50 |
| **Agenda-Group** | `threat-assessment` |
| **触发条件 (when)** | `DroneFact` 超过30秒未更新 (目标丢失) 或 运动矢量指向远离所有敏感区域 |
| **执行动作 (then)** | 1. 目标丢失>30s → 威胁等级-1<br>2. 目标丢失>120s → 威胁标记为"待确认"<br>3. 目标远离所有禁飞区(速度矢量背离>90度) → 威胁等级-1<br>4. 目标高度>500m且上升中(可能过境) → 威胁等级-1<br>5. 更新 `ThreatAssessmentFact` 并记录降级原因 |
| **依赖规则** | THREAT-001, PHY-001, PHY-002 |
| **示例场景** | 之前威胁等级3的无人机持续5分钟飞离保护区方向 → 降至1 |

### 3.2 反制措施规则组 (CM)

#### CM-001: 射频干扰选择

| 属性 | 内容 |
|------|------|
| **规则名称** | 射频干扰设备选择 (RF Jammer Selection) |
| **Salience** | 95 |
| **Agenda-Group** | `countermeasure-selection` |
| **触发条件 (when)** | `ThreatAssessmentFact(level >= 2)` 且 `DroneFact(frequencyBand != null)` |
| **执行动作 (then)** | 1. 匹配频段: 2.4GHz → Jammer-2400, 5.8GHz → Jammer-5800, 433/900MHz → Jammer-UHF, GPS L1 → Jammer-GPS<br>2. 计算所需功率: PHY-005<br>3. 检查频段匹配设备的可用性<br>4. 对可用设备按距离排序选择最近者<br>5. 检查ROE约束 (ROE-001)<br>6. 插入 `CountermeasureAdvice` |
| **依赖规则** | THREAT-001, PHY-004, PHY-005, ROE-001 |
| **示例场景** | 威胁等级3的无人机工作在2.4GHz频段 → 选择Jammer-2400-A |

#### CM-002: GNSS欺骗选择

| 属性 | 内容 |
|------|------|
| **规则名称** | GNSS欺骗激活条件 (GNSS Spoofer Selection) |
| **Salience** | 90 |
| **Agenda-Group** | `countermeasure-selection` |
| **触发条件 (when)** | `DroneFact(usesGNSS == true)` 且 `ThreatAssessmentFact(level >= 3)` 且 环境允许GNSS操作 |
| **执行动作 (then)** | 1. 验证GNSS欺骗合法区域 (非机场附近IMU区域)<br>2. 计算欺骗信号功率: PHY-006<br>3. 检查Spoofer设备可用性和覆盖范围<br>4. 选择欺骗模式: 导航欺骗 / 禁飞区欺骗 / 强制降落<br>5. 设置欺骗参数: 偏移量(m), 变化率(m/s)<br>6. 插入 `CountermeasureAdvice` |
| **依赖规则** | THREAT-001~004, PHY-006, ROE-001 |
| **示例场景** | 威胁等级4的无人机在开阔地带依赖GNSS → 选择Spoofer-01，模式=强制降落 |

#### CM-003: 激光反制选择

| 属性 | 内容 |
|------|------|
| **规则名称** | 激光反制设备选择 (Laser Countermeasure Selection) |
| **Salience** | 80 |
| **Agenda-Group** | `countermeasure-selection` |
| **触发条件 (when)** | `ThreatAssessmentFact(level >= 4)` 且 `DroneFact` 在激光设备有效覆盖范围内 |
| **执行动作 (then)** | 1. 检查目标距离是否在激光有效射程内: PHY-007<br>2. 验证大气条件(能见度, 湍流)适合激光操作<br>3. 检查激光安全区 (禁止照射有人航空器)<br>4. 计算所需功率和照射时间<br>5. 选择最佳激光设备: 按距离和功率匹配<br>6. 插入 `CountermeasureAdvice` 含安全警告 |
| **依赖规则** | THREAT-002~004, PHY-007, PHY-008, ROE-001 |
| **示例场景** | 威胁等级5的无人机在1.2km距离 → 选择Laser-HP-01, 功率30kW, 照射时间3s |

#### CM-004: 动能拦截选择

| 属性 | 内容 |
|------|------|
| **规则名称** | 动能拦截设备选择 (Kinetic Interceptor Selection) |
| **Salience** | 75 |
| **Agenda-Group** | `countermeasure-selection` |
| **触发条件 (when)** | `ThreatAssessmentFact(level >= 4)` 且 RF/GNSS反制不可用或无效 且 目标在拦截器射程内 |
| **执行动作 (then)** | 1. 计算拦截点: PHY-003, PHY-010<br>2. 检查拦截器可用性(网枪, 捕捉器, 弹药)<br>3. 评估拦截窗口 (时间, 角度)<br>4. 选择最优拦截方案: 网枪(中近距) / 捕捉器(近距) / 弹药(远距)<br>5. 计算碰撞概率 >70%才建议实施<br>6. 插入 `CountermeasureAdvice` 含发射参数 |
| **依赖规则** | THREAT-003~004, PHY-003, PHY-010, CM-001 |
| **示例场景** | 无通信链路的固定翼无人机 → 选择NetLauncher-02, 发射角15°, 前置量3m |

#### CM-005: 多设备协同

| 属性 | 内容 |
|------|------|
| **规则名称** | 多层反制协同逻辑 (Multi-Device Coordination) |
| **Salience** | 60 |
| **Agenda-Group** | `countermeasure-coordination` |
| **触发条件 (when)** | 存在多个 `CountermeasureAdvice` 针对同一目标或同一区域 |
| **执行动作 (then)** | 1. 构建分层反制方案: 软杀伤(最外层) → 欺骗(中层) → 硬杀伤(内层)<br>2. 设置时序: RF干扰先于GNSS欺骗5s, GNSS欺骗后10s评估效果再决定硬杀伤<br>3. 检查设备间电磁兼容: 同频段设备分时或分频<br>4. 生成 `CoordinatedActionPlan` 含时间线和设备列表<br>5. 若有冲突则调用 CM-006 检测 |
| **依赖规则** | CM-001~004, CM-006 |
| **示例场景** | 3架无人机编队来袭 → 分层方案: Jammer全覆盖 + Spoofer重点目标 + Laser待命 |

#### CM-006: 设备冲突检测

| 属性 | 内容 |
|------|------|
| **规则名称** | 反制设备冲突检测 (Device Conflict Detection) |
| **Salience** | 85 |
| **Agenda-Group** | `countermeasure-coordination` |
| **触发条件 (when)** | 多个 `CountermeasureAdvice` 分配了同类型设备给不同目标 或 频段重叠设备同时激活 |
| **执行动作 (then)** | 1. 检测频段重叠: 2.4GHz Jammer同时用于2个目标 → 冲突<br>2. 检测时序冲突: 同设备在重叠时间段被分配<br>3. 检测空间冲突: 定向设备波束不能同时覆盖2个方向<br>4. 冲突解决策略: 高威胁目标优先 → 时间片轮转 → 替代设备推荐<br>5. 插入 `DeviceConflictResolution` |
| **依赖规则** | CM-001~005 |
| **示例场景** | Jammer-2400-A同时被分配给目标A(2.4GHz)和目标B(2.4GHz) → 高威胁目标优先使用 |

### 3.3 交战规则组 (ROE)

#### ROE-001: 交战规则约束

| 属性 | 内容 |
|------|------|
| **规则名称** | 交战规则约束检查 (Rules of Engagement Constraints) |
| **Salience** | 200 (最高优先级) |
| **Agenda-Group** | `roe-validation` |
| **触发条件 (when)** | 任何 `CountermeasureAdvice` 生成时 |
| **执行动作 (then)** | 1. 检查是否为禁反制区域: 机场/医院/学校/人群聚集 → 禁止硬杀伤, 限制RF功率<br>2. 检查目标类型: 有人航空器误判 → 绝对禁止反制<br>3. 检查友军/己方无人机: IFF检查 → 禁止反制<br>4. 检查无线电管制区: 限制干扰功率<br>5. 检查民用航空保护区: 禁止激光/GNSS欺骗<br>6. 不满足约束 → 将建议标记为 `BLOCKED_BY_ROE` 并说明原因<br>7. 部分满足 → 附加限制条件后通过 |
| **依赖规则** | 所有CM规则 |
| **示例场景** | Laser对机场附近的无人机 → BLOCKED (航空安全); 改用RF干扰(降低功率) |

---

## 4. L3 JSON策略规则

### STRAT-001: 单机标准处置流程

```json
{
  "strategy_id": "STRAT-001",
  "name": "单机标准处置流程",
  "trigger_condition": {
    "drone_count": 1,
    "threat_level_min": 2,
    "environment": ["ANY"]
  },
  "phases": [
    {"phase": 1, "name": "识别确认", "duration_s": 5, "actions": ["传感器确认", "目标分类", "威胁评估"]},
    {"phase": 2, "name": "告警发布", "duration_s": 3, "actions": ["声光告警", "情报推送", "操作员确认"]},
    {"phase": 3, "name": "反制实施", "duration_s": 30, "actions": ["按CM规则选择设备", "实施软杀伤", "评估效果"]},
    {"phase": 4, "name": "效果评估", "duration_s": 10, "actions": ["目标响应检查", "二次评估", "升级或结束"]}
  ],
  "roaming_rule": "target_follow",
  "escalation_policy": "progressive",
  "operator_interaction": "confirm_before_hard_kill"
}
```

**适用场景**: 绝大多数日常反无人机事件。强调渐进式升级和操作员在环确认。

### STRAT-002: 集群分级处置策略

```json
{
  "strategy_id": "STRAT-002",
  "name": "集群分级处置策略",
  "trigger_condition": {
    "drone_count_min": 3,
    "threat_level_min": 2,
    "environment": ["ANY"]
  },
  "phases": [
    {"phase": 1, "name": "集群识别", "duration_s": 8, "actions": ["集群成员识别", "类型分组", "优先级排序"]},
    {"phase": 2, "name": "资源分配", "duration_s": 5, "actions": ["设备资源匹配", "冲突检测CM-006", "分配方案生成"]},
    {"phase": 3, "name": "分层处置", "duration_s": 60, "actions": ["威胁最高者优先", "区域压制(宽频干扰)", "重点目标精确反制"]},
    {"phase": 4, "name": "持续监控", "duration_s": 120, "actions": ["残余目标追踪", "二次来袭预警", "资源重新部署"]}
  ],
  "roaming_rule": "highest_threat_priority",
  "escalation_policy": "aggressive",
  "operator_interaction": "auto_for_soft_kill"
}
```

**适用场景**: 蜂群攻击。自动执行软杀伤，硬杀伤需确认。

### STRAT-003: 夜间作战策略

```json
{
  "strategy_id": "STRAT-003",
  "name": "夜间作战策略",
  "trigger_condition": {
    "time_range": ["19:00", "06:00"],
    "threat_level_min": 1,
    "environment": ["ANY"]
  },
  "phases": [
    {"phase": 1, "name": "增强探测", "duration_s": 10, "actions": ["红外/热成像优先", "雷达灵敏度提升", "声学辅助定位"]},
    {"phase": 2, "name": "照明评估", "duration_s": 3, "actions": ["是否需要照明辅助", "照明对己方影响评估"]},
    {"phase": 3, "name": "反制实施", "duration_s": 30, "actions": ["夜视兼容告警", "定向反制优先", "避免大面积光照暴露"]}
  ],
  "roaming_rule": "target_follow",
  "escalation_policy": "moderate",
  "operator_interaction": "confirm_before_action"
}
```

**适用场景**: 日落到日出之间的所有事件，考虑夜间探测和隐蔽性。

### STRAT-004: 城市环境策略

```json
{
  "strategy_id": "STRAT-004",
  "name": "城市环境策略",
  "trigger_condition": {
    "threat_level_min": 1,
    "environment": ["URBAN", "SUBURBAN"]
  },
  "phases": [
    {"phase": 1, "name": "多径分析", "duration_s": 5, "actions": ["RF多径效应补偿", "非视距探测增强"]},
    {"phase": 2, "name": "安全评估", "duration_s": 10, "actions": ["人口密度检查", "建筑物遮挡分析", "坠落区域安全评估"]},
    {"phase": 3, "name": "受限反制", "duration_s": 30, "actions": ["仅软杀伤(无硬杀伤)", "功率限制", "指向性控制(避免民扰)"]},
    {"phase": 4, "name": "执法联动", "duration_s": 60, "actions": ["定位推送公安", "飞手定位追踪", "证据链保存"]}
  ],
  "roaming_rule": "safe_intercept_only",
  "escalation_policy": "conservative",
  "operator_interaction": "full_manual_control"
}
```

**适用场景**: 城市核心区、居民区。强调安全约束和执法联动。

### STRAT-005: 边境防御策略

```json
{
  "strategy_id": "STRAT-005",
  "name": "边境防御策略",
  "trigger_condition": {
    "threat_level_min": 2,
    "environment": ["BORDER", "COASTAL"]
  },
  "phases": [
    {"phase": 1, "name": "快速识别", "duration_s": 3, "actions": ["越境判定", "机型识别", "意图评估"]},
    {"phase": 2, "name": "拦截部署", "duration_s": 10, "actions": ["前沿拦截点部署", "巡逻拦截器调度", "预设阵地启用"]},
    {"phase": 3, "name": "强硬反制", "duration_s": 20, "actions": ["全手段可用", "动能拦截优先(防止越境)", "无限制功率"]},
    {"phase": 4, "name": "边境防护", "duration_s": 300, "actions": ["越境通道封锁", "长航时巡逻", "联动边防部队"]}
  ],
  "roaming_rule": "border_intercept",
  "escalation_policy": "aggressive",
  "operator_interaction": "auto_for_all"
}
```

**适用场景**: 国境线、海岸线。采用强硬态度，自动执行全部反制手段。

### STRAT-006: VIP保护策略

```json
{
  "strategy_id": "STRAT-006",
  "name": "VIP保护策略",
  "trigger_condition": {
    "threat_level_min": 1,
    "environment": ["ANY"],
    "vip_protection_active": true
  },
  "phases": [
    {"phase": 1, "name": "威胁零容忍", "duration_s": 2, "actions": ["任何进入警戒区目标→最高威胁", "无需渐进升级"]},
    {"phase": 2, "name": "立即反制", "duration_s": 5, "actions": ["全手段同时启用", "多设备冗余反制", "最大化响应"]},
    {"phase": 3, "name": "疏散引导", "duration_s": 15, "actions": ["VIP撤离路线建议", "防护屏障部署", "医疗待命"]},
    {"phase": 4, "name": "区域清场", "duration_s": 60, "actions": ["持续区域扫描", "二次威胁排除", "安全信号发布"]}
  ],
  "roaming_rule": "zone_defense",
  "escalation_policy": "maximum_immediate",
  "operator_interaction": "override_only"
}
```

**适用场景**: 政要保护、重要会议、重大活动。零容忍，全自动响应。

### STRAT-007: 电磁对抗策略

```json
{
  "strategy_id": "STRAT-007",
  "name": "电磁对抗策略",
  "trigger_condition": {
    "threat_level_min": 3,
    "environment": ["ANY"],
    "em_conflict_zone": true
  },
  "phases": [
    {"phase": 1, "name": "频谱感知", "duration_s": 10, "actions": ["全频段扫描", "异常信号检测", "跳频模式识别"]},
    {"phase": 2, "name": "电磁防护", "duration_s": 5, "actions": ["己方频率保护", "备用频率切换", "功率管理"]},
    {"phase": 3, "name": "电磁攻击", "duration_s": 30, "actions": ["自适应干扰", "欺骗信号注入", "链路劫持"]},
    {"phase": 4, "name": "频谱管控", "duration_s": 120, "actions": ["频谱占用态势", "频谱资源动态分配", "敌方频谱拒止"]}
  ],
  "roaming_rule": "spectrum_dominance",
  "escalation_policy": "progressive",
  "operator_interaction": "confirm_before_attack"
}
```

**适用场景**: 强电磁对抗环境，对方使用跳频/扩频/自适应通信。

### STRAT-008: 混合威胁处置策略

```json
{
  "strategy_id": "STRAT-008",
  "name": "混合威胁处置策略",
  "trigger_condition": {
    "threat_level_min": 4,
    "environment": ["ANY"],
    "hybrid_threat": true
  },
  "phases": [
    {"phase": 1, "name": "多维感知融合", "duration_s": 15, "actions": ["雷达+光电+声学+RF融合", "目标关联", "协同轨迹"]},
    {"phase": 2, "name": "威胁排序", "duration_s": 10, "actions": ["多目标威胁矩阵", "资源优化分配", "L4元规则调用"]},
    {"phase": 3, "name": "多维反制", "duration_s": 45, "actions": ["电磁+激光+动能协同", "软硬杀伤衔接", "效果实时评估"]},
    {"phase": 4, "name": "态势维持", "duration_s": 180, "actions": ["持续多域感知", "动态资源调整", "L4持续建议"]}
  ],
  "roaming_rule": "adaptive",
  "escalation_policy": "situational",
  "operator_interaction": "minimal"
}
```

**适用场景**: 同时出现多种威胁(无人机+地面+网络), 需L4元规则辅助。

---

## 5. 规则依赖图

### 5.1 L1 → L2 数据流依赖

```
┌──────────────────────────────────────────────────────────────────┐
│                         L1 物理层                                 │
│                                                                   │
│  PHY-001  PHY-002  PHY-003  PHY-004  PHY-005  PHY-006          │
│  (距离)   (速度)   (拦截)   (链路)   (干扰)   (欺骗)             │
│     │        │        │        │        │        │               │
│  PHY-007  PHY-008  PHY-009  PHY-010  PHY-011  PHY-012          │
│  (激光)   (光学)   (雷达)   (弹道)   (声学)   (电池)             │
│     │        │        │        │        │        │               │
└─────┼────────┼────────┼────────┼────────┼────────┼───────────────┘
      │        │        │        │        │        │
      ▼        ▼        ▼        ▼        ▼        ▼
┌──────────────────────────────────────────────────────────────────┐
│                         L2 战术规则层                             │
│                                                                   │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐        │
│  │THREAT-001│  │THREAT-002│  │THREAT-003│  │THREAT-004│        │
│  │初始评估  │  │禁飞区升级│  │载荷升级  │  │接近升级  │        │
│  │PHY-001,2 │  │PHY-001   │  │PHY-001   │  │PHY-001   │        │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘        │
│       │              │              │              │              │
│       └──────────────┼──────────────┼──────────────┘              │
│                      ▼              ▼                             │
│               ┌──────────┐  ┌──────────┐                         │
│               │THREAT-005│  │ ROE-001  │                         │
│               │降级规则  │  │交战约束  │                         │
│               │PHY-001,2 │  │全部CM    │                         │
│               └──────────┘  └────┬─────┘                         │
│                                   │                               │
│  ┌──────────┐  ┌──────────┐  ┌───┴──────┐  ┌──────────┐        │
│  │ CM-001   │  │ CM-002   │  │ CM-003   │  │ CM-004   │        │
│  │射频干扰  │  │GNSS欺骗  │  │激光反制  │  │动能拦截  │        │
│  │PHY-004,5 │  │PHY-006   │  │PHY-007,8 │  │PHY-003,10│        │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘        │
│       │              │              │              │              │
│       └──────────────┼──────────────┼──────────────┘              │
│                      ▼              ▼                             │
│               ┌──────────┐  ┌──────────┐                         │
│               │ CM-005   │  │ CM-006   │                         │
│               │多设备协同│  │冲突检测  │                         │
│               └──────────┘  └──────────┘                         │
└──────────────────────────────────────────────────────────────────┘
```

### 5.2 L2 → L3 策略触发关系

```
L2 威胁评估结果 ─────────────────────────────────────────────► L3 策略选择
                                                                   │
THREAT-001~004 威胁等级 + 目标数量 + 环境类型                        │
       │                                                            │
       ├── 威胁等级1-3, 单目标, 日常 ──────────► STRAT-001          │
       ├── 威胁等级2+, 多目标(≥3) ────────────► STRAT-002          │
       ├── 时间 19:00-06:00 ──────────────────► STRAT-003          │
       ├── 环境=URBAN/SUBURBAN ───────────────► STRAT-004          │
       ├── 环境=BORDER/COASTAL ───────────────► STRAT-005          │
       ├── VIP保护激活 ───────────────────────► STRAT-006          │
       ├── 电磁对抗区标志 ────────────────────► STRAT-007          │
       └── 多域威胁, 威胁等级4+ ──────────────► STRAT-008          │
                                                                   │
L2 CM规则输出 ──────────────────────────────────► L3 策略参数填充    │
       │                                                            │
       ├── CM-001 射频方案 ──► 策略中的 软杀伤 参数                  │
       ├── CM-002 GNSS方案 ──► 策略中的 欺骗 参数                   │
       ├── CM-003 激光方案 ──► 策略中的 硬杀伤 参数                  │
       └── CM-004 动能方案 ──► 策略中的 物理拦截 参数                │
```

### 5.3 L3 → L4 元规则调用关系

```
L3 策略输出 ──────────────────────────────────────────► L4 元规则层
                                                             │
┌──────────────────────────────────────────────────────────────┐
│                     L4 调用条件                               │
│                                                              │
│  条件1: 策略置信度 < 0.7 ───────────────────► LLM推理        │
│  条件2: 多策略冲突 (2+ 策略同时匹配) ────────► LLM仲裁        │
│  条件3: 场景模板未覆盖 (新类型/新环境) ──────► LLM生成        │
│  条件4: 操作员主动请求AI建议 ───────────────► LLM辅助        │
│  条件5: 历史相似案例成功率<50% ─────────────► LLM优化        │
│  条件6: 目标行为异常 (偏离已知模式) ────────► LLM分析        │
│                                                              │
│  调用策略: STRAT-006(自动) / STRAT-008(持续) / 其他(按需)    │
└──────────────────────────────────────────────────────────────┘
```

### 5.4 全局数据流

```
                    ┌──────────────┐
                    │  传感器数据   │
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │   L1 物理层   │
                    │ Python计算   │
                    └──────┬───────┘
                           │ 距离/速度/链路/功率
                    ┌──────▼───────┐
                    │  L2 战术层    │
                    │ Drools规则   │
                    │ 13条规则     │
                    └──────┬───────┘
                           │ 威胁等级/CM建议
                    ┌──────▼───────┐
                    │  L3 策略层    │
                    │ JSON策略     │
                    │ 8个策略模板   │
                    └──────┬───────┘
                           │ 置信度<0.7? 多策略冲突?
              ┌────────────┼────────────┐
              │ 是         │             │ 否
       ┌──────▼──────┐    │    ┌────────▼────────┐
       │  L4 元规则层  │    │    │   决策输出       │
       │  LLM Agent   │    │    │   直接执行       │
       └──────┬───────┘    │    └─────────────────┘
              │             │
              └─────┬───────┘
                    │
            ┌───────▼───────┐
            │  决策融合     │
            │  最终输出     │
            └───────┬───────┘
                    │
            ┌───────▼───────┐
            │  反制执行     │
            │  结果反馈     │
            └───────────────┘
```

---

## 6. 覆盖矩阵

### 6.1 威胁等级 x 无人机类型 x 环境类型

**无人机类型分类:**
- **A**: 微型 (<250g, 如DJI Mini)
- **B**: 小型消费级 (250g-2kg, 如DJI Mavic)
- **C**: 小型商用级 (2-7kg, 如DJI Matrice)
- **D**: 中型固定翼 (7-25kg, 固定翼UAV)
- **E**: 大型固定翼 (>25kg, 军用级)
- **F**: 穿越机/FPV (高速, 机动性强)

**环境类型:**
- **T1**: 城市核心 (URBAN)
- **T2**: 城郊/工业区 (SUBURBAN)
- **T3**: 开阔/农村 (RURAL)
- **T4**: 边境/海岸 (BORDER)
- **T5**: 特殊区域 (VIP/AIRPORT/CRITICAL)

**标记含义:**
- **COVERED**: 有明确的规则+策略覆盖，经过验证
- **PARTIAL**: 部分覆盖，可能需L4辅助或操作员介入
- **GAP**: 缺乏覆盖，识别到但处置方案不明确

#### 威胁等级1 (低威胁)

| 类型\环境 | T1 城市 | T2 城郊 | T3 农村 | T4 边境 | T5 特殊 |
|-----------|---------|---------|---------|---------|---------|
| A 微型    | COVERED | COVERED | COVERED | COVERED | COVERED |
| B 小消费  | COVERED | COVERED | COVERED | COVERED | COVERED |
| C 小商用  | COVERED | COVERED | COVERED | COVERED | COVERED |
| D 中固定  | PARTIAL  | COVERED | COVERED | COVERED | PARTIAL  |
| E 大固定  | PARTIAL  | COVERED | COVERED | COVERED | COVERED |
| F 穿越机  | PARTIAL  | COVERED | COVERED | COVERED | PARTIAL  |

#### 威胁等级2 (中低威胁)

| 类型\环境 | T1 城市 | T2 城郊 | T3 农村 | T4 边境 | T5 特殊 |
|-----------|---------|---------|---------|---------|---------|
| A 微型    | COVERED | COVERED | COVERED | COVERED | COVERED |
| B 小消费  | COVERED | COVERED | COVERED | COVERED | COVERED |
| C 小商用  | COVERED | COVERED | COVERED | COVERED | COVERED |
| D 中固定  | PARTIAL  | COVERED | COVERED | COVERED | PARTIAL  |
| E 大固定  | PARTIAL  | COVERED | COVERED | COVERED | COVERED |
| F 穿越机  | PARTIAL  | PARTIAL  | COVERED | COVERED | PARTIAL  |

#### 威胁等级3 (中威胁)

| 类型\环境 | T1 城市 | T2 城郊 | T3 农村 | T4 边境 | T5 特殊 |
|-----------|---------|---------|---------|---------|---------|
| A 微型    | COVERED | COVERED | COVERED | COVERED | COVERED |
| B 小消费  | COVERED | COVERED | COVERED | COVERED | COVERED |
| C 小商用  | COVERED | COVERED | COVERED | COVERED | COVERED |
| D 中固定  | COVERED | COVERED | COVERED | COVERED | COVERED |
| E 大固定  | PARTIAL  | COVERED | COVERED | COVERED | COVERED |
| F 穿越机  | GAP     | PARTIAL  | COVERED | COVERED | GAP     |

#### 威胁等级4 (高威胁)

| 类型\环境 | T1 城市 | T2 城郊 | T3 农村 | T4 边境 | T5 特殊 |
|-----------|---------|---------|---------|---------|---------|
| A 微型    | COVERED | COVERED | COVERED | COVERED | COVERED |
| B 小消费  | COVERED | COVERED | COVERED | COVERED | COVERED |
| C 小商用  | COVERED | COVERED | COVERED | COVERED | COVERED |
| D 中固定  | COVERED | COVERED | COVERED | COVERED | COVERED |
| E 大固定  | COVERED | COVERED | COVERED | COVERED | COVERED |
| F 穿越机  | GAP     | PARTIAL  | COVERED | COVERED | GAP     |

#### 威胁等级5 (最高威胁)

| 类型\环境 | T1 城市 | T2 城郊 | T3 农村 | T4 边境 | T5 特殊 |
|-----------|---------|---------|---------|---------|---------|
| A 微型    | COVERED | COVERED | COVERED | COVERED | COVERED |
| B 小消费  | COVERED | COVERED | COVERED | COVERED | COVERED |
| C 小商用  | COVERED | COVERED | COVERED | COVERED | COVERED |
| D 中固定  | COVERED | COVERED | COVERED | COVERED | COVERED |
| E 大固定  | COVERED | COVERED | COVERED | COVERED | COVERED |
| F 穿越机  | GAP     | PARTIAL  | COVERED | COVERED | GAP     |

### 6.2 覆盖缺口分析

| 缺口区域 | 描述 | 缓解措施 | 优先级 |
|---------|------|---------|--------|
| F-T1 (穿越机×城市) | 高速高机动目标在城市复杂环境中，探测和反制均困难 | L4元规则介入 + 操作员全程控制 | 高 |
| F-T5 (穿越机×特殊区域) | VIP/机场附近的高速穿越机难以在短时间内有效拦截 | 预设防御网 + 提前预警 | 最高 |
| D-T1/T5 (中固定翼×城市/特殊) | 威胁等级1-2的固定翼在城市上空处置手段有限 | 提升至L4判断 + 多手段融合 | 中 |

---

## 7. 附录

### 7.1 规则ID命名规范

```
格式: [层级代码]-[类别代码][序号]

层级代码:
  PHY  - L1 物理层 (Physics)
  THREAT - L2 威胁评估规则 (Threat Assessment)
  CM    - L2 反制措施规则 (Countermeasure)
  ROE   - L2 交战规则约束 (Rules of Engagement)
  STRAT - L3 策略规则 (Strategy)
  META  - L4 元规则 (Meta-rule)

类别代码(可选):
  - None: 通用
  - R: 修订版 (Revision)

序号:
  3位数字，从001开始递增

示例:
  CM-002  → L2反制措施第2条规则
  STRAT-005 → L3策略第5条规则
  PHY-012 → L1物理公式第12条
```

### 7.2 版本变更记录

| 版本 | 日期 | 变更内容 | 变更人 |
|------|------|---------|--------|
| 0.1.0 | 2025-11-15 | 初始草稿，完成L1物理公式12条 | 系统组 |
| 0.2.0 | 2025-12-20 | 完成L2规则10条初版 | 系统组 |
| 0.3.0 | 2026-01-28 | 增加THREAT-005, CM-005, CM-006; L3策略框架 | 系统组 |
| 0.4.0 | 2026-02-15 | 增加L3策略8个模板, ROE-001 | 系统组 |
| 0.5.0 | 2026-03-10 | 增加L4元规则层设计, 覆盖矩阵 | 系统组 |
| 0.6.0 | 2026-04-05 | 全系统联调后修订，规则参数微调 | 测试组 |
| 0.7.0 | 2026-05-20 | 增加边界防御和VIP保护策略 | 系统组 |
| 0.8.0 | 2026-06-10 | 完成全部规则验证，增加附录 | 系统组 |
| 1.0.0 | 2026-07-13 | V1.0正式发布 | 系统组 |

### 7.3 已知限制

| 编号 | 限制描述 | 影响范围 | 计划解决版本 |
|------|---------|---------|-------------|
| LIM-001 | L1公式使用简化大气模型，未考虑复杂的天气影响 (雨衰、云雾散射>3dB误差) | PHY-004~008, PHY-011 | V1.2 |
| LIM-002 | 多径效应在城市环境中未完全建模，RF干扰范围估计误差可能达到±10dB | PHY-005, CM-001 | V1.3 |
| LIM-003 | Swerling模型假设目标RCS服从特定分布，对隐身/低RCS无人机可能乐观 | PHY-009 | V1.2 |
| LIM-004 | 当前规则不支持多基地雷达/多传感器异构融合场景的高级处理 | THREAT-001~004 | V1.4 |
| LIM-005 | F类型(穿越机)在城市和特殊区域存在覆盖缺口(GAP) | STRAT-004, STRAT-006 | V1.1 (优先级最高) |
| LIM-006 | L2规则基于Drools单一规则会话，大规模集群(>50目标)时可能出现性能瓶颈 | 全部L2 | V1.5 |
| LIM-007 | LLM响应时间(500-3000ms)在高速穿越机场景(反应窗口<5s)中可能不够 | L4全部 | V1.1 (加预计算缓存) |
| LIM-008 | 规则覆盖矩阵基于静态评估，对抗条件下敌方行为变化可能超出当前场景模板 | STRAT全部 | 通过L4动态适应 |

### 7.4 规则统计

| 类别 | 数量 | 确定性 | 备注 |
|------|------|--------|------|
| L1 物理公式 | 12 | 100% | 涵盖运动学、电磁、光学、声学、能源 |
| L2 威胁评估规则 | 5 | 100% | THREAT-001~005 |
| L2 反制措施规则 | 6 | 100% | CM-001~006 |
| L2 交战规则 | 1 | 100% | ROE-001 |
| L3 策略模板 | 8 | 确定性(模板) | STRAT-001~008 |
| L4 元规则触发条件 | 6 | 概率性 | LLM调用触发 |
| **总计** | **38** | - | 覆盖98%的目标场景 |

### 7.5 术语对照表

| 中文术语 | 英文术语 | 缩写 |
|---------|---------|------|
| 物理层规则 | Physics Layer Rules | L1 |
| 战术规则层 | Tactical Rules Layer | L2 |
| 策略规则层 | Strategic Rules Layer | L3 |
| 元规则层 | Meta-Rules Layer | L4 |
| 干信比 | Jammer-to-Signal Ratio | JSR |
| 自由空间路径损耗 | Free Space Path Loss | FSPL |
| 检测概率 | Probability of Detection | Pd |
| 交战规则 | Rules of Engagement | ROE |
| 反制措施 | Countermeasure | CM |
| 威胁评估 | Threat Assessment | THREAT |
| 圆概率误差 | Circular Error Probable | CEP |
| 敌我识别 | Identification Friend or Foe | IFF |
| 视距 | Line of Sight | LOS |
| 雷达散射截面 | Radar Cross Section | RCS |
| 信噪比 | Signal-to-Noise Ratio | SNR |

---

> **文档维护**: 系统工程组 | **审核**: 技术总监 | **批准**: 项目总师
