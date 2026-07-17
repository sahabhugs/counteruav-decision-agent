-- =============================================================
-- Counter-UAV Decision Agent System - Initial Schema
-- 反无人机决策智能体系统 - 数据库初始化脚本
-- MySQL 8.0+ / InnoDB / utf8mb4
-- =============================================================

-- 创建数据库（如尚未存在）
-- CREATE DATABASE IF NOT EXISTS counteruav_decision_agent
--   CHARACTER SET utf8mb4
--   COLLATE utf8mb4_unicode_ci;
-- USE counteruav_decision_agent;

-- =============================================================
-- 1. 无人机知识库表
-- 存储已知无人机型号及其规格参数，用于威胁评估
-- =============================================================
CREATE TABLE IF NOT EXISTS drone_knowledge_base (
    id                      BIGINT          AUTO_INCREMENT PRIMARY KEY              COMMENT '主键自增ID',
    drone_id                VARCHAR(64)     NOT NULL                                COMMENT '无人机唯一标识符，如 dji-mavic-3',
    name                    VARCHAR(128)    NOT NULL                                COMMENT '无人机英文名称',
    name_cn                 VARCHAR(128)    NOT NULL                                COMMENT '无人机中文名称',
    category                ENUM(
                                'consumer_quadcopter',      -- 消费级四旋翼
                                'diy_fpv',                  -- DIY穿越机
                                'military_fixed_wing',      -- 军用固定翼
                                'military_quadcopter',      -- 军用四旋翼
                                'hybrid_vtol',              -- 混合垂直起降
                                'autonomous_swarm'          -- 自主蜂群
                            )               NOT NULL                                COMMENT '无人机类别',
    manufacturer            VARCHAR(128)                                                COMMENT '制造商',
    max_speed_ms            DECIMAL(6,2)                                                COMMENT '最大速度 (m/s)',
    max_altitude_m          DECIMAL(8,2)                                                COMMENT '最大飞行高度 (m)',
    max_endurance_min       INT                                                         COMMENT '最大续航时间 (分钟)',
    max_payload_kg          DECIMAL(6,2)                                                COMMENT '最大载荷重量 (kg)',
    max_range_km            DECIMAL(8,2)                                                COMMENT '最大航程 (km)',
    weight_kg               DECIMAL(8,3)                                                COMMENT '自重 (kg)',
    dimensions_json         JSON                                                        COMMENT '外形尺寸 JSON，格式 [L, W, H] 单位 mm',
    frequency_bands_json    JSON                                                        COMMENT '通信频段 JSON，字符串数组',
    gnss_json               JSON                                                        COMMENT '支持的 GNSS 系统 JSON，字符串数组',
    rf_signature_json       JSON                                                        COMMENT '射频指纹特征 JSON 对象',
    static_threat_base      DECIMAL(3,2)   NOT NULL DEFAULT 1.00                       COMMENT '静态威胁基础分 (0.00~5.00)',
    vulnerable_to_json      JSON                                                        COMMENT '脆弱性 JSON，对哪些反制手段敏感',
    resistant_to_json       JSON                                                        COMMENT '抗性 JSON，对哪些反制手段有抵抗力',
    typical_mission_json    JSON                                                        COMMENT '典型任务模式 JSON',
    operational_ceiling_m   DECIMAL(8,2)                                                COMMENT '实用升限 (m)',
    notes                   TEXT                                                        COMMENT '备注说明',
    source                  VARCHAR(64)    DEFAULT 'OPEN_INTELLIGENCE_2024'             COMMENT '数据来源',
    confidence              ENUM('HIGH','MEDIUM','LOW') NOT NULL DEFAULT 'MEDIUM'      COMMENT '数据可信度：高/中/低',
    embedding_vector        JSON                                                        COMMENT '向量嵌入引用（占位）',
    created_at              TIMESTAMP      DEFAULT CURRENT_TIMESTAMP                    COMMENT '记录创建时间',
    updated_at              TIMESTAMP      DEFAULT CURRENT_TIMESTAMP
                                           ON UPDATE CURRENT_TIMESTAMP                  COMMENT '记录更新时间',

    UNIQUE KEY uk_drone_id (drone_id),
    INDEX idx_drone_category (category),
    INDEX idx_drone_threat (static_threat_base),
    INDEX idx_drone_confidence (confidence)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='无人机知识库 - 存储已知无人机型号及规格参数';


-- =============================================================
-- 2. 决策日志表
-- 记录系统每次做出的决策，用于审计和回溯
-- =============================================================
CREATE TABLE IF NOT EXISTS decision_log (
    id                      BIGINT          AUTO_INCREMENT PRIMARY KEY              COMMENT '主键自增ID',
    decision_id             VARCHAR(64)     NOT NULL                                COMMENT '决策唯一标识符',
    decision_time           TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP       COMMENT '决策时间',
    target_id               VARCHAR(64)     NOT NULL                                COMMENT '目标标识符',
    target_type             VARCHAR(64)                                             COMMENT '目标类型',
    drone_classification    VARCHAR(128)                                            COMMENT '无人机分类结果',
    threat_level_before     TINYINT UNSIGNED                                        COMMENT '处置前威胁等级 (1~5)',
    threat_level_after      TINYINT UNSIGNED                                        COMMENT '处置后威胁等级 (1~5)',
    scenario_id             VARCHAR(32)                                             COMMENT '场景模板ID',
    terrain_type            VARCHAR(32)                                             COMMENT '地形类型',
    rules_fired_json        JSON                                                    COMMENT '触发的规则ID列表 JSON',
    llm_consulted           TINYINT(1)      DEFAULT 0                               COMMENT '是否咨询了大模型 (0=否, 1=是)',
    llm_recommendation      JSON                                                    COMMENT '大模型推荐内容 JSON',
    final_action            VARCHAR(128)    NOT NULL                                COMMENT '最终执行的反制动作',
    action_parameters       JSON                                                    COMMENT '反制动作参数 JSON',
    confidence_score        DECIMAL(4,3)                                            COMMENT '决策置信度 (0.000~1.000)',
    execution_status        ENUM(
                                'pending',      -- 待审批
                                'approved',     -- 已批准
                                'executing',    -- 执行中
                                'success',      -- 执行成功
                                'failed',       -- 执行失败
                                'cancelled',    -- 已取消
                                'overturned'    -- 已推翻
                            )               DEFAULT 'pending'                        COMMENT '执行状态',
    operator_override       TINYINT(1)      DEFAULT 0                               COMMENT '操作员是否覆盖决策 (0=否, 1=是)',
    operator_id             VARCHAR(64)                                             COMMENT '操作员ID',
    session_id              VARCHAR(64)                                             COMMENT '会话ID，用于关联同一任务中的多个决策',
    trace_id                VARCHAR(128)                                            COMMENT '分布式追踪ID',
    latency_total_ms        INT                                                     COMMENT '决策总耗时 (ms)',
    latency_rule_engine_ms  INT                                                     COMMENT '规则引擎耗时 (ms)',
    latency_llm_ms          INT                                                     COMMENT '大模型调用耗时 (ms)',
    notes                   TEXT                                                    COMMENT '备注说明',
    created_at              TIMESTAMP       DEFAULT CURRENT_TIMESTAMP                COMMENT '记录创建时间',

    UNIQUE KEY uk_decision_id (decision_id),
    INDEX idx_decision_time (decision_time),
    INDEX idx_decision_target (target_id),
    INDEX idx_decision_threat (threat_level_before, threat_level_after),
    INDEX idx_decision_action (final_action),
    INDEX idx_decision_status (execution_status),
    INDEX idx_decision_session (session_id),
    INDEX idx_decision_scenario (scenario_id),
    INDEX idx_decision_trace (trace_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='决策日志 - 记录系统每次做出的反制决策';


-- =============================================================
-- 3. 反馈日志表
-- 存储操作员反馈与系统学习数据，用于持续优化决策模型
-- =============================================================
CREATE TABLE IF NOT EXISTS feedback_log (
    id                      BIGINT          AUTO_INCREMENT PRIMARY KEY              COMMENT '主键自增ID',
    feedback_id             VARCHAR(64)     NOT NULL                                COMMENT '反馈唯一标识符',
    decision_id             VARCHAR(64)     NOT NULL                                COMMENT '关联的决策ID',
    feedback_type           ENUM(
                                'approve',  -- 批准
                                'reject',   -- 拒绝
                                'correct',  -- 纠正
                                'comment',  -- 评论
                                'rating'    -- 评分
                            )               NOT NULL                                COMMENT '反馈类型',
    operator_id             VARCHAR(64)                                             COMMENT '操作员ID',
    rating                  TINYINT UNSIGNED                                        COMMENT '评分 (1~5)',
    comment                 TEXT                                                    COMMENT '反馈文字说明',
    correction_action       VARCHAR(128)                                            COMMENT '纠正后的反制动作',
    correction_params       JSON                                                    COMMENT '纠正后的动作参数 JSON',
    original_decision       JSON                                                    COMMENT '原始决策快照 JSON',
    was_effective           TINYINT(1)                                              COMMENT '决策是否有效 (0=否, 1=是, NULL=未知)',
    learning_applied        TINYINT(1)      DEFAULT 0                               COMMENT '是否已纳入学习 (0=否, 1=是)',
    created_at              TIMESTAMP       DEFAULT CURRENT_TIMESTAMP                COMMENT '记录创建时间',

    UNIQUE KEY uk_feedback_id (feedback_id),
    INDEX idx_feedback_decision (decision_id),
    INDEX idx_feedback_type (feedback_type),
    INDEX idx_feedback_rating (rating),
    INDEX idx_feedback_effective (was_effective),
    CONSTRAINT fk_feedback_decision
        FOREIGN KEY (decision_id) REFERENCES decision_log(decision_id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT chk_feedback_rating
        CHECK (rating IS NULL OR (rating >= 1 AND rating <= 5))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='反馈日志 - 存储操作员反馈与系统学习数据';


-- =============================================================
-- 4. 待审批规则表
-- 存储已提议但尚未激活的规则
-- =============================================================
CREATE TABLE IF NOT EXISTS pending_rules (
    id                      BIGINT          AUTO_INCREMENT PRIMARY KEY              COMMENT '主键自增ID',
    rule_id                 VARCHAR(64)     NOT NULL                                COMMENT '规则唯一标识符',
    rule_name               VARCHAR(256)    NOT NULL                                COMMENT '规则名称',
    rule_type               ENUM(
                                'drl',          -- 声明式规则语言
                                'json',         -- JSON格式规则
                                'python',       -- Python脚本规则
                                'llm_generated' -- 大模型生成规则
                            )               NOT NULL                                COMMENT '规则类型',
    rule_content            LONGTEXT        NOT NULL                                COMMENT '规则完整内容',
    rule_metadata           JSON                                                    COMMENT '规则元数据 JSON',
    proposed_by             VARCHAR(64)     NOT NULL                                COMMENT '提议人ID',
    approval_status         ENUM(
                                'pending',      -- 待审批
                                'approved',     -- 已批准
                                'rejected',     -- 已拒绝
                                'testing',      -- 测试中
                                'active',       -- 已激活
                                'deprecated'    -- 已废弃
                            )               DEFAULT 'pending'                        COMMENT '审批状态',
    testing_results         JSON                                                    COMMENT '测试结果 JSON',
    activation_date         TIMESTAMP       NULL                                    COMMENT '激活日期',
    deactivation_date       TIMESTAMP       NULL                                    COMMENT '停用日期',
    created_at              TIMESTAMP       DEFAULT CURRENT_TIMESTAMP                COMMENT '创建时间',
    updated_at              TIMESTAMP       DEFAULT CURRENT_TIMESTAMP
                                           ON UPDATE CURRENT_TIMESTAMP              COMMENT '更新时间',

    UNIQUE KEY uk_pr_rule_id (rule_id),
    INDEX idx_pr_status (approval_status),
    INDEX idx_pr_type (rule_type),
    INDEX idx_pr_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='待审批规则 - 存储已提议但尚未激活的规则';


-- =============================================================
-- 5. 规则版本历史表
-- 追踪规则的版本变更历史
-- =============================================================
CREATE TABLE IF NOT EXISTS rule_versions (
    id                      BIGINT          AUTO_INCREMENT PRIMARY KEY              COMMENT '主键自增ID',
    version_id              VARCHAR(128)    NOT NULL                                COMMENT '版本唯一标识符（如 rule-001_v1.0.0）',
    rule_id                 VARCHAR(64)     NOT NULL                                COMMENT '规则ID',
    version_number          VARCHAR(32)     NOT NULL                                COMMENT '版本号 (如 1.0.0)',
    rule_content            LONGTEXT        NOT NULL                                COMMENT '该版本的规则完整内容',
    change_description      TEXT                                                    COMMENT '变更说明',
    changed_by              VARCHAR(64)                                             COMMENT '变更人ID',
    is_active               TINYINT(1)      DEFAULT 0                               COMMENT '是否为当前激活版本 (0=否, 1=是)',
    activation_date         TIMESTAMP       NULL                                    COMMENT '激活日期',
    created_at              TIMESTAMP       DEFAULT CURRENT_TIMESTAMP                COMMENT '创建时间',

    UNIQUE KEY uk_rv_version_id (version_id),
    INDEX idx_rv_rule (rule_id),
    INDEX idx_rv_active (is_active),
    INDEX idx_rv_version (rule_id, version_number),
    INDEX idx_rv_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='规则版本历史 - 追踪规则的版本变更';


-- =============================================================
-- 6. 威胁历史表
-- 存储历史威胁评估记录，用于趋势分析和模型训练
-- =============================================================
CREATE TABLE IF NOT EXISTS threat_history (
    id                      BIGINT          AUTO_INCREMENT PRIMARY KEY              COMMENT '主键自增ID',
    history_id              VARCHAR(64)     NOT NULL                                COMMENT '历史记录唯一标识符',
    target_id               VARCHAR(64)     NOT NULL                                COMMENT '目标标识符',
    assessment_time         TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP       COMMENT '威胁评估时间',
    threat_level            TINYINT UNSIGNED NOT NULL                               COMMENT '威胁等级 (1~5)',
    drone_type              VARCHAR(128)                                            COMMENT '判定的无人机类型',
    position_lat            DECIMAL(10,7)                                           COMMENT '纬度',
    position_lon            DECIMAL(10,7)                                           COMMENT '经度',
    altitude_m              DECIMAL(8,2)                                            COMMENT '高度 (m)',
    speed_ms                DECIMAL(6,2)                                            COMMENT '速度 (m/s)',
    heading_deg             DECIMAL(5,1)                                            COMMENT '航向角 (度)',
    sensor_data             JSON                                                    COMMENT '传感器原始数据 JSON',
    rule_evaluation         JSON                                                    COMMENT '规则评估详情 JSON',
    llm_assessment          JSON                                                    COMMENT '大模型评估结果 JSON',
    session_id              VARCHAR(64)                                             COMMENT '会话ID',
    created_at              TIMESTAMP       DEFAULT CURRENT_TIMESTAMP                COMMENT '记录创建时间',

    UNIQUE KEY uk_th_history_id (history_id),
    INDEX idx_th_target (target_id),
    INDEX idx_th_time (assessment_time),
    INDEX idx_th_level (threat_level),
    INDEX idx_th_session (session_id),
    INDEX idx_th_drone_type (drone_type),
    INDEX idx_th_position (position_lat, position_lon),
    CONSTRAINT chk_th_threat_level
        CHECK (threat_level >= 1 AND threat_level <= 5)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='威胁历史 - 存储历史威胁评估用于趋势分析';


-- =============================================================
-- 7. 设备注册表
-- 存储反制设备及其能力信息
-- =============================================================
CREATE TABLE IF NOT EXISTS device_registry (
    id                      BIGINT          AUTO_INCREMENT PRIMARY KEY              COMMENT '主键自增ID',
    device_id               VARCHAR(64)     NOT NULL                                COMMENT '设备唯一标识符',
    device_name             VARCHAR(128)    NOT NULL                                COMMENT '设备名称',
    device_type             ENUM(
                                'radar',                -- 雷达
                                'rf_detector',          -- 射频探测器
                                'rf_jammer',            -- 射频干扰器
                                'gnss_spoofer',         -- GNSS诱骗器
                                'eo_ir_camera',         -- 光电/红外相机
                                'laser_dazzler',        -- 激光炫目器
                                'laser_destructor',     -- 激光摧毁器
                                'kinetic_interceptor',  -- 动能拦截器
                                'net_gun',              -- 网枪
                                'protocol_hijacker',    -- 协议劫持器
                                'acoustic_sensor',      -- 声学传感器
                                'command_link'          -- 指挥链路设备
                            )               NOT NULL                                COMMENT '设备类型',
    manufacturer            VARCHAR(128)                                            COMMENT '制造商',
    model                   VARCHAR(128)                                            COMMENT '设备型号',
    status                  ENUM(
                                'online',       -- 在线
                                'offline',      -- 离线
                                'maintenance',  -- 维护中
                                'degraded',     -- 性能降级
                                'standby'       -- 待机
                            )               DEFAULT 'online'                         COMMENT '设备状态',
    position_lat            DECIMAL(10,7)                                           COMMENT '部署纬度',
    position_lon            DECIMAL(10,7)                                           COMMENT '部署经度',
    altitude_m              DECIMAL(8,2)                                            COMMENT '部署海拔 (m)',
    coverage_radius_m       INT                                                     COMMENT '覆盖半径 (m)',
    frequency_range_mhz_json JSON                                                   COMMENT '工作频率范围 JSON，如 [{"min":2400,"max":2500}]',
    max_power_w             DECIMAL(8,2)                                            COMMENT '最大发射功率 (W)',
    capabilities_json       JSON                                                    COMMENT '设备能力详情 JSON',
    last_health_check       TIMESTAMP       NULL                                    COMMENT '最后一次健康检查时间',
    firmware_version        VARCHAR(32)                                             COMMENT '固件版本',
    ip_address              VARCHAR(45)                                             COMMENT 'IP地址 (IPv4/IPv6)',
    port                    INT                                                     COMMENT '通信端口',
    configuration_json      JSON                                                    COMMENT '设备配置参数 JSON',
    notes                   TEXT                                                    COMMENT '备注说明',
    created_at              TIMESTAMP       DEFAULT CURRENT_TIMESTAMP                COMMENT '记录创建时间',
    updated_at              TIMESTAMP       DEFAULT CURRENT_TIMESTAMP
                                           ON UPDATE CURRENT_TIMESTAMP              COMMENT '记录更新时间',

    UNIQUE KEY uk_dr_device_id (device_id),
    INDEX idx_dr_type (device_type),
    INDEX idx_dr_status (status),
    INDEX idx_dr_position (position_lat, position_lon)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='设备注册表 - 存储反制设备及其能力信息';


-- =============================================================
-- 8. 场景模板库
-- 存储已知场景及其响应策略模板
-- =============================================================
CREATE TABLE IF NOT EXISTS scenario_library (
    id                              BIGINT          AUTO_INCREMENT PRIMARY KEY      COMMENT '主键自增ID',
    scenario_id                     VARCHAR(64)     NOT NULL                        COMMENT '场景唯一标识符',
    name                            VARCHAR(128)    NOT NULL                        COMMENT '场景中文名称',
    name_en                         VARCHAR(128)                                    COMMENT '场景英文名称',
    description                     TEXT                                            COMMENT '场景描述',
    target_profile_json             JSON                                            COMMENT '目标特征 JSON',
    threat_assessment_template_json JSON                                            COMMENT '威胁评估模板 JSON',
    recommended_strategy_json       JSON                                            COMMENT '推荐反制策略 JSON',
    historical_success_rate         DECIMAL(5,4)                                    COMMENT '历史成功率 (0.0000~1.0000)',
    usage_count                     INT             DEFAULT 0                       COMMENT '使用次数',
    last_used                       TIMESTAMP       NULL                            COMMENT '上次使用时间',
    source                          VARCHAR(64)     DEFAULT 'GENERATED_TEMPLATE'    COMMENT '模板来源',
    is_active                       TINYINT(1)      DEFAULT 1                       COMMENT '是否启用 (0=禁用, 1=启用)',
    created_at                      TIMESTAMP       DEFAULT CURRENT_TIMESTAMP        COMMENT '创建时间',
    updated_at                      TIMESTAMP       DEFAULT CURRENT_TIMESTAMP
                                                   ON UPDATE CURRENT_TIMESTAMP      COMMENT '更新时间',

    UNIQUE KEY uk_sl_scenario_id (scenario_id),
    INDEX idx_sl_active (is_active),
    INDEX idx_sl_usage (usage_count),
    INDEX idx_sl_source (source)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='场景模板库 - 存储已知场景及其响应策略模板';


-- =============================================================
-- 9. 大模型调用日志表
-- 追踪每次大模型调用的详细信息
-- =============================================================
CREATE TABLE IF NOT EXISTS llm_call_log (
    id                      BIGINT          AUTO_INCREMENT PRIMARY KEY              COMMENT '主键自增ID',
    call_id                 VARCHAR(64)     NOT NULL                                COMMENT '调用唯一标识符',
    task_id                 VARCHAR(64)                                             COMMENT '任务ID',
    session_id              VARCHAR(64)                                             COMMENT '会话ID',
    trigger_reason          ENUM(
                                'rule_escalation',          -- 规则升级
                                'uncertain_classification', -- 分类不确定
                                'novel_threat',             -- 新型威胁
                                'operator_query',           -- 操作员查询
                                'periodic_review',          -- 定期复盘
                                'conflict_resolution',      -- 冲突解决
                                'strategy_refinement'       -- 策略优化
                            )               NOT NULL                                COMMENT '触发原因',
    target_id               VARCHAR(64)                                             COMMENT '目标ID',
    model_name              VARCHAR(64)     NOT NULL                                COMMENT '模型名称（如 claude-sonnet-4-20250514）',
    system_prompt_hash      VARCHAR(64)                                             COMMENT '系统提示词哈希值（用于版本追踪）',
    rounds_taken            INT             DEFAULT 1                               COMMENT '多轮对话轮次',
    prompt_tokens           INT             DEFAULT 0                               COMMENT '提示词Token数',
    completion_tokens       INT             DEFAULT 0                               COMMENT '补全Token数',
    total_tokens            INT             DEFAULT 0                               COMMENT '总Token数',
    latency_ms              INT             DEFAULT 0                               COMMENT '调用延迟 (ms)',
    success                 TINYINT(1)      DEFAULT 1                               COMMENT '是否调用成功 (0=失败, 1=成功)',
    response_type           ENUM(
                                'classification',   -- 分类
                                'recommendation',   -- 推荐
                                'analysis',         -- 分析
                                'refinement',       -- 优化
                                'error'             -- 错误
                            )               DEFAULT 'recommendation'                 COMMENT '响应类型',
    response_json           JSON                                                    COMMENT '响应内容 JSON',
    error_code              VARCHAR(32)                                             COMMENT '错误码',
    error_message           TEXT                                                    COMMENT '错误信息',
    cost_estimate           DECIMAL(10,6)                                           COMMENT '预估费用 (美元)',
    created_at              TIMESTAMP       DEFAULT CURRENT_TIMESTAMP                COMMENT '记录创建时间',

    UNIQUE KEY uk_llc_call_id (call_id),
    INDEX idx_llc_task (task_id),
    INDEX idx_llc_model (model_name),
    INDEX idx_llc_success (success),
    INDEX idx_llc_time (created_at),
    INDEX idx_llc_trigger (trigger_reason),
    INDEX idx_llc_session (session_id),
    INDEX idx_llc_target (target_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='大模型调用日志 - 追踪每次LLM调用的详细信息';

-- =============================================================
-- 初始化完成
-- =============================================================
