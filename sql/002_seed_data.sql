-- =============================================================
-- Counter-UAV Decision Agent System - Seed Data
-- 反无人机决策智能体系统 - 初始种子数据
-- 使用 INSERT IGNORE 确保幂等执行
-- =============================================================

-- =============================================================
-- 1. 无人机知识库种子数据（5种无人机型号）
-- =============================================================

-- 1.1 DJI Mavic 3 — 消费级四旋翼，常见低慢小目标
INSERT INTO drone_knowledge_base (
    drone_id, name, name_cn, category, manufacturer,
    max_speed_ms, max_altitude_m, max_endurance_min, max_payload_kg, max_range_km, weight_kg,
    dimensions_json, frequency_bands_json, gnss_json, rf_signature_json,
    static_threat_base, vulnerable_to_json, resistant_to_json, typical_mission_json,
    operational_ceiling_m, notes, source, confidence, embedding_vector
) VALUES (
    'dji-mavic-3',
    'DJI Mavic 3',
    '大疆御3',
    'consumer_quadcopter',
    'DJI (大疆创新)',
    21.00,              -- 最大速度 21 m/s ≈ 75.6 km/h
    6000.00,            -- 最大起飞海拔 6000m
    46,                 -- 最大续航 46 分钟
    0.50,               -- 最大载荷约 0.5kg（无额外挂载）
    30.00,              -- 最大航程约 30km (O3+图传)
    0.895,              -- 起飞重量 895g
    '{"length_mm": 347, "width_mm": 283, "height_mm": 108}',
    '["2.4GHz", "5.8GHz"]',
    '["GPS", "GLONASS", "Galileo", "BeiDou"]',
    '{"protocol_family": "OcuSync", "occusync_version": "3.0", "tx_power_dbm": 26, "bandwidth_mhz": 40}',
    0.80,               -- 消费级，基础威胁较低
    '["rf_jammer", "gnss_spoofer", "protocol_hijacker", "net_gun"]',
    '["laser_dazzler"]',
    '{"primary_use": "reconnaissance", "typical_fly_alt_m": 120, "typical_pattern": "grid_scan"}',
    6000.00,
    '全球最常见的消费级无人机之一，广泛用于航拍、巡检和侦察。无加密跳频，易受射频干扰。',
    'OPEN_INTELLIGENCE_2024',
    'HIGH',
    NULL
) ON DUPLICATE KEY UPDATE
    name_cn = VALUES(name_cn),
    category = VALUES(category),
    updated_at = CURRENT_TIMESTAMP;


-- 1.2 DJI Phantom 4 Pro — 消费级四旋翼，具备一定载荷能力
INSERT INTO drone_knowledge_base (
    drone_id, name, name_cn, category, manufacturer,
    max_speed_ms, max_altitude_m, max_endurance_min, max_payload_kg, max_range_km, weight_kg,
    dimensions_json, frequency_bands_json, gnss_json, rf_signature_json,
    static_threat_base, vulnerable_to_json, resistant_to_json, typical_mission_json,
    operational_ceiling_m, notes, source, confidence, embedding_vector
) VALUES (
    'dji-phantom-4-pro',
    'DJI Phantom 4 Pro',
    '大疆精灵4 Pro',
    'consumer_quadcopter',
    'DJI (大疆创新)',
    20.00,              -- 最大速度 20 m/s (S模式)
    6000.00,            -- 最大起飞海拔 6000m
    30,                 -- 最大续航 30 分钟
    0.80,               -- 最大载荷约 0.8kg（含挂载）
    7.00,               -- 最大图传距离约 7km (FCC)
    1.388,              -- 起飞重量 1388g
    '{"length_mm": 350, "width_mm": 350, "height_mm": 196}',
    '["2.4GHz", "5.8GHz"]',
    '["GPS", "GLONASS"]',
    '{"protocol_family": "Lightbridge", "tx_power_dbm": 26, "bandwidth_mhz": 20}',
    0.75,
    '["rf_jammer", "gnss_spoofer", "protocol_hijacker", "net_gun"]',
    '["laser_dazzler"]',
    '{"primary_use": "reconnaissance", "typical_fly_alt_m": 120, "typical_pattern": "hover_and_stare"}',
    6000.00,
    '经典小型侦察平台，已被多支非正规武装改装用于投掷小型爆炸物，威胁评估需考虑改装可能性。',
    'OPEN_INTELLIGENCE_2024',
    'HIGH',
    NULL
) ON DUPLICATE KEY UPDATE
    name_cn = VALUES(name_cn),
    category = VALUES(category),
    updated_at = CURRENT_TIMESTAMP;


-- 1.3 DIY 5-inch FPV — DIY穿越机，高速高机动，可用于自杀式攻击
INSERT INTO drone_knowledge_base (
    drone_id, name, name_cn, category, manufacturer,
    max_speed_ms, max_altitude_m, max_endurance_min, max_payload_kg, max_range_km, weight_kg,
    dimensions_json, frequency_bands_json, gnss_json, rf_signature_json,
    static_threat_base, vulnerable_to_json, resistant_to_json, typical_mission_json,
    operational_ceiling_m, notes, source, confidence, embedding_vector
) VALUES (
    'diy-5inch-fpv',
    'DIY 5-inch FPV Racing Drone',
    'DIY 5寸穿越机',
    'diy_fpv',
    '多厂商 (DIY组装)',
    45.00,              -- 最大速度约 162 km/h，竞速级
    3000.00,            -- 估计最大飞行高度 3000m
    8,                  -- 续航仅 8 分钟（高速飞行时更短）
    1.50,               -- 可挂载约 1.5kg 载荷（含RPG弹头等改装）
    5.00,               -- 模拟图传距离约 5km
    0.750,              -- 典型起飞重量 750g（裸机）
    '{"length_mm": 220, "width_mm": 220, "height_mm": 55}',
    '["5.8GHz", "2.4GHz", "915MHz", "1.3GHz"]',
    '["GPS", "BeiDou"]',
    '{"protocol_family": "Analog_FPV", "video_tx_power_mw": 800, "control_link": "Crossfire_ELRS"}',
    3.50,               -- 高威胁：高速、可改装为FPV自杀式无人机
    '["rf_jammer", "net_gun"]',
    '["gnss_spoofer", "protocol_hijacker"]',
    '{"primary_use": "kinetic_strike", "typical_fly_alt_m": 50, "typical_pattern": "high_speed_approach"}',
    3000.00,
    '俄乌冲突中广泛使用的小型FPV攻击无人机。速度极快，飞行高度低，雷达截面小，难以被传统防空系统探测。通常通过模拟图传，不受GNSS诱骗影响。',
    'OPEN_INTELLIGENCE_2024',
    'HIGH',
    NULL
) ON DUPLICATE KEY UPDATE
    name_cn = VALUES(name_cn),
    category = VALUES(category),
    updated_at = CURRENT_TIMESTAMP;


-- 1.4 Orlan-10 — 军用固定翼侦察无人机
INSERT INTO drone_knowledge_base (
    drone_id, name, name_cn, category, manufacturer,
    max_speed_ms, max_altitude_m, max_endurance_min, max_payload_kg, max_range_km, weight_kg,
    dimensions_json, frequency_bands_json, gnss_json, rf_signature_json,
    static_threat_base, vulnerable_to_json, resistant_to_json, typical_mission_json,
    operational_ceiling_m, notes, source, confidence, embedding_vector
) VALUES (
    'orlan-10',
    'Orlan-10',
    '海鹰-10',
    'military_fixed_wing',
    'Special Technology Centre (俄罗斯特种技术中心)',
    41.67,              -- 最大速度约 150 km/h
    5000.00,            -- 最大飞行高度 5000m
    960,                -- 最大续航 16 小时
    6.00,               -- 最大载荷约 6kg
    600.00,             -- 最大航程约 600km（数据链控制范围内）
    15.000,             -- 起飞重量约 15kg
    '{"length_mm": 2000, "width_mm": 3100, "height_mm": 400}',
    '["UHF", "2.4GHz", "3.3GHz"]',
    '["GPS", "GLONASS"]',
    '{"protocol_family": "Proprietary_Military", "tx_power_w": 10}',
    4.20,               -- 高威胁：军用级、长航时、可携带电子战载荷
    '["rf_jammer", "kinetic_interceptor", "laser_destructor"]',
    '["gnss_spoofer", "protocol_hijacker", "net_gun"]',
    '{"primary_use": "ISR", "typical_fly_alt_m": 1500, "typical_pattern": "orbit_loiter"}',
    5000.00,
    '俄军标准战术侦察无人机，可搭载电子战吊舱、信号情报(SIGINT)载荷和相机。具备CATV弹射起飞和降落伞回收能力。俄乌冲突中大量使用。',
    'OPEN_INTELLIGENCE_2024',
    'HIGH',
    NULL
) ON DUPLICATE KEY UPDATE
    name_cn = VALUES(name_cn),
    category = VALUES(category),
    updated_at = CURRENT_TIMESTAMP;


-- 1.5 Bayraktar TB2 — 中空长航时察打一体无人机
INSERT INTO drone_knowledge_base (
    drone_id, name, name_cn, category, manufacturer,
    max_speed_ms, max_altitude_m, max_endurance_min, max_payload_kg, max_range_km, weight_kg,
    dimensions_json, frequency_bands_json, gnss_json, rf_signature_json,
    static_threat_base, vulnerable_to_json, resistant_to_json, typical_mission_json,
    operational_ceiling_m, notes, source, confidence, embedding_vector
) VALUES (
    'bayraktar-tb2',
    'Bayraktar TB2',
    '拜拉克塔尔 TB2',
    'military_fixed_wing',
    'Baykar Technology (土耳其)',
    61.67,              -- 最大速度约 222 km/h (120 knots)
    8230.00,            -- 最大飞行高度 27000 ft ≈ 8230m
    1620,               -- 最大续航 27 小时
    150.00,             -- 最大载荷 150kg
    300.00,             -- 视距链路控制半径约 300km（可中继扩展）
    700.000,            -- 最大起飞重量 700kg
    '{"length_mm": 6500, "width_mm": 12000, "height_mm": 2200}',
    '["C-band", "Ku-band", "UHF"]',
    '["GPS", "GLONASS", "Galileo"]',
    '{"protocol_family": "Proprietary_Military_SATCOM", "satcom_supported": true}',
    4.80,               -- 极高威胁：察打一体，精确制导弹药
    '["kinetic_interceptor", "laser_destructor", "rf_jammer"]',
    '["gnss_spoofer", "net_gun", "laser_dazzler", "protocol_hijacker"]',
    '{"primary_use": "ISR_and_Strike", "typical_fly_alt_m": 5500, "typical_pattern": "orbit_loiter", "armament": ["MAM-L", "MAM-C"]}',
    8230.00,
    '土耳其制造的中空长航时(MALE)察打一体无人机。可携带4枚MAM-L/MAM-C精确制导弹药。在叙利亚、利比亚、纳卡、乌克兰等冲突中取得显著战果。具备SATCOM超视距作战能力。',
    'OPEN_INTELLIGENCE_2024',
    'HIGH',
    NULL
) ON DUPLICATE KEY UPDATE
    name_cn = VALUES(name_cn),
    category = VALUES(category),
    updated_at = CURRENT_TIMESTAMP;


-- =============================================================
-- 2. 场景模板库种子数据（3个场景模板）
-- =============================================================

-- 2.1 单一低速侦察无人机入侵场景
INSERT INTO scenario_library (
    scenario_id, name, name_en, description,
    target_profile_json, threat_assessment_template_json, recommended_strategy_json,
    historical_success_rate, usage_count, last_used, source, is_active
) VALUES (
    'sc-001',
    '单一低速侦察入侵',
    'Single Slow Recon Intrusion',
    '单架消费级/民用级小型四旋翼无人机以低速（<30m/s）在低空（<500m）进入警戒区域，执行侦察或拍摄任务。典型目标：DJI Mavic/Phantom 系列。',
    '{
        "drone_count": 1,
        "drone_category": ["consumer_quadcopter"],
        "speed_range_ms": {"min": 0, "max": 30},
        "altitude_range_m": {"min": 10, "max": 500},
        "flight_pattern": ["hover_and_stare", "grid_scan", "direct_approach"],
        "payload_suspected": false,
        "rf_active": true,
        "gnss_active": true
    }',
    '{
        "threat_level_base": 1,
        "priority": "LOW",
        "engagement_time_window_s": 300,
        "auto_escalation_threshold": 3
    }',
    '{
        "primary_action": "rf_jamming",
        "fallback_action": "gnss_spoofing",
        "alert_level": "INFO",
        "require_operator_approval": false,
        "engagement_steps": [
            {"step": 1, "action": "detect_and_classify", "device": "rf_detector"},
            {"step": 2, "action": "track", "device": "radar"},
            {"step": 3, "action": "jam_rf", "device": "rf_jammer", "duration_s": 30},
            {"step": 4, "action": "assess_effect", "wait_s": 10},
            {"step": 5, "action": "spoof_gnss_if_needed", "device": "gnss_spoofer"}
        ],
        "success_criteria": "drone_lands_or_returns"
    }',
    0.9200,
    156,
    '2026-07-10 14:30:00',
    'GENERATED_TEMPLATE',
    1
) ON DUPLICATE KEY UPDATE
    name = VALUES(name),
    recommended_strategy_json = VALUES(recommended_strategy_json),
    updated_at = CURRENT_TIMESTAMP;


-- 2.2 高速FPV自杀式攻击场景
INSERT INTO scenario_library (
    scenario_id, name, name_en, description,
    target_profile_json, threat_assessment_template_json, recommended_strategy_json,
    historical_success_rate, usage_count, last_used, source, is_active
) VALUES (
    'sc-002',
    '高速FPV自杀式攻击',
    'High-Speed FPV Suicide Strike',
    '单架或多架（<5架）DIY FPV穿越机以高速（>30m/s）低空（<200m）直接逼近关键设施，可能挂载爆炸物执行自杀式攻击。典型目标：5寸/7寸FPV穿越机。',
    '{
        "drone_count": {"min": 1, "max": 5},
        "drone_category": ["diy_fpv"],
        "speed_range_ms": {"min": 20, "max": 60},
        "altitude_range_m": {"min": 5, "max": 200},
        "flight_pattern": ["high_speed_approach", "evasive_maneuver", "terrain_following"],
        "payload_suspected": true,
        "rf_active": true,
        "gnss_active": false
    }',
    '{
        "threat_level_base": 5,
        "priority": "CRITICAL",
        "engagement_time_window_s": 30,
        "auto_escalation_threshold": 1,
        "immediate_actions_required": true
    }',
    '{
        "primary_action": "rf_jamming_wideband",
        "fallback_action": "kinetic_intercept",
        "alert_level": "CRITICAL",
        "require_operator_approval": false,
        "engagement_steps": [
            {"step": 1, "action": "detect_and_classify", "device": "rf_detector", "max_latency_ms": 500},
            {"step": 2, "action": "track_high_speed", "device": "radar", "update_rate_hz": 10},
            {"step": 3, "action": "activate_wideband_jamming", "device": "rf_jammer", "bands": ["5.8GHz", "2.4GHz", "915MHz", "1.3GHz"]},
            {"step": 4, "action": "activate_laser_dazzler", "device": "laser_dazzler"},
            {"step": 5, "action": "launch_kinetic_interceptor", "device": "kinetic_interceptor", "condition": "jam_ineffective"}
        ],
        "success_criteria": "drone_destroyed_or_disabled",
        "max_response_time_ms": 3000
    }',
    0.6500,
    42,
    '2026-07-12 08:15:00',
    'GENERATED_TEMPLATE',
    1
) ON DUPLICATE KEY UPDATE
    name = VALUES(name),
    recommended_strategy_json = VALUES(recommended_strategy_json),
    updated_at = CURRENT_TIMESTAMP;


-- 2.3 无人机蜂群协同攻击场景
INSERT INTO scenario_library (
    scenario_id, name, name_en, description,
    target_profile_json, threat_assessment_template_json, recommended_strategy_json,
    historical_success_rate, usage_count, last_used, source, is_active
) VALUES (
    'sc-003',
    '无人机蜂群协同攻击',
    'Drone Swarm Coordinated Attack',
    '大规模无人机蜂群（>10架）从多方向同时逼近，可能包含多种机型组合（侦察型+攻击型），具备协同通信和自主编队能力。典型场景：军事级蜂群攻击。',
    '{
        "drone_count": {"min": 10, "max": 100},
        "drone_category": ["autonomous_swarm", "military_quadcopter", "military_fixed_wing"],
        "speed_range_ms": {"min": 10, "max": 80},
        "altitude_range_m": {"min": 20, "max": 3000},
        "flight_pattern": ["swarm_formation", "multi_axis_attack", "distributed_coordination", "decoy_and_strike"],
        "payload_suspected": true,
        "rf_active": true,
        "gnss_active": true,
        "swarm_protocol_detected": true,
        "multi_spectrum_signature": true
    }',
    '{
        "threat_level_base": 5,
        "priority": "CRITICAL",
        "engagement_time_window_s": 120,
        "auto_escalation_threshold": 1,
        "immediate_actions_required": true,
        "recommend_llm_consultation": true
    }',
    '{
        "primary_action": "multi_layer_defense",
        "fallback_action": "area_denial",
        "alert_level": "CRITICAL",
        "require_operator_approval": true,
        "engagement_steps": [
            {"step": 1, "action": "activate_all_sensors", "devices": ["radar", "rf_detector", "eo_ir_camera", "acoustic_sensor"]},
            {"step": 2, "action": "fly_swarm_formation", "intent": "identify_leader_nodes"},
            {"step": 3, "action": "wide_area_jamming", "device": "rf_jammer", "mode": "all_bands_max_power"},
            {"step": 4, "action": "deploy_gnss_spoofing", "device": "gnss_spoofer", "mode": "area_deception"},
            {"step": 5, "action": "activate_laser_systems", "devices": ["laser_dazzler", "laser_destructor"]},
            {"step": 6, "action": "launch_kinetic_interceptors", "device": "kinetic_interceptor", "targeting": "priority_queue"},
            {"step": 7, "action": "consult_llm_for_strategy", "trigger": "operator_escalation"}
        ],
        "success_criteria": "swarm_defeated_or_repelled",
        "max_response_time_ms": 10000
    }',
    0.3800,
    12,
    '2026-06-28 22:45:00',
    'GENERATED_TEMPLATE',
    1
) ON DUPLICATE KEY UPDATE
    name = VALUES(name),
    recommended_strategy_json = VALUES(recommended_strategy_json),
    updated_at = CURRENT_TIMESTAMP;


-- =============================================================
-- 3. 设备注册表种子数据（6个反制设备）
-- =============================================================

-- 3.1 相控阵雷达 — 探测与跟踪
INSERT INTO device_registry (
    device_id, device_name, device_type, manufacturer, model, status,
    position_lat, position_lon, altitude_m, coverage_radius_m,
    frequency_range_mhz_json, max_power_w, capabilities_json,
    last_health_check, firmware_version, ip_address, port, configuration_json, notes
) VALUES (
    'radar-001',
    '反无人相控阵雷达 1号',
    'radar',
    '中国电子科技集团 (CETC)',
    'CETC-SR-6000',
    'online',
    39.9042000,         -- 纬度 (北京示例)
    116.4074000,        -- 经度
    50.00,              -- 部署海拔 50m
    8000,               -- 覆盖半径 8km
    '[{"band": "Ku", "min_mhz": 12000, "max_mhz": 18000}]',
    2000.00,            -- 峰值功率 2kW
    '{
        "targets_tracked_max": 200,
        "min_rcs_sqm": 0.01,
        "update_rate_hz": 5,
        "elevation_cover_deg": {"min": -5, "max": 90},
        "azimuth_cover_deg": 360,
        "doppler_available": true,
        "micro_doppler_available": true,
        "classification_supported": true,
        "track_modes": ["TWS", "STT", "MTT"]
    }',
    '2026-07-13 06:00:00',
    'v3.2.1',
    '192.168.10.101',
    8001,
    '{"rotation_speed_rpm": 30, "sector_scan_enabled": false, "anti_jamming_mode": "adaptive"}',
    'Ku波段相控阵雷达，专门优化用于探测低空慢速小目标(LSS)。具备微多普勒特征识别能力，可区分旋翼/固定翼无人机。'
) ON DUPLICATE KEY UPDATE
    status = VALUES(status),
    last_health_check = VALUES(last_health_check),
    updated_at = CURRENT_TIMESTAMP;


-- 3.2 射频探测器 — 频谱监测与识别
INSERT INTO device_registry (
    device_id, device_name, device_type, manufacturer, model, status,
    position_lat, position_lon, altitude_m, coverage_radius_m,
    frequency_range_mhz_json, max_power_w, capabilities_json,
    last_health_check, firmware_version, ip_address, port, configuration_json, notes
) VALUES (
    'rfdet-001',
    '宽带射频探测器 1号',
    'rf_detector',
    'Rohde & Schwarz (罗德与施瓦茨)',
    'R&S-PR200',
    'online',
    39.9045000,
    116.4078000,
    50.00,
    10000,              -- 覆盖半径 10km（取决于发射功率）
    '[{"min_mhz": 20, "max_mhz": 8000}]',
    0.10,               -- 接收设备，发射功率不适用
    '{
        "instantaneous_bandwidth_mhz": 40,
        "frequency_resolution_hz": 1,
        "sensitivity_dbm": -160,
        "protocol_library": ["OcuSync", "Lightbridge", "DJI_Aeroscope", "Autel_Skylink", "Crossfire", "ELRS", "Analog_FPV", "DJI_FPV_Digital"],
        "direction_finding_available": true,
        "df_accuracy_deg": 3,
        "scan_speed_ghz_per_sec": 40,
        "simultaneous_signals": 50
    }',
    '2026-07-13 05:55:00',
    'v2.4.0',
    '192.168.10.102',
    8002,
    '{"scan_mode": "continuous", "alert_threshold_dbm": -80, "recording_enabled": true}',
    '宽带射频监测接收机，覆盖20MHz-8GHz全频段。内置无人机协议特征库，支持TDOA测向定位。可同时跟踪50个独立信号源。'
) ON DUPLICATE KEY UPDATE
    status = VALUES(status),
    last_health_check = VALUES(last_health_check),
    updated_at = CURRENT_TIMESTAMP;


-- 3.3 射频干扰器 — 定向/全向通信干扰
INSERT INTO device_registry (
    device_id, device_name, device_type, manufacturer, model, status,
    position_lat, position_lon, altitude_m, coverage_radius_m,
    frequency_range_mhz_json, max_power_w, capabilities_json,
    last_health_check, firmware_version, ip_address, port, configuration_json, notes
) VALUES (
    'rfjam-001',
    '多频段射频干扰器 1号',
    'rf_jammer',
    '中国电子科技集团 (CETC)',
    'CETC-JM-8000',
    'online',
    39.9042000,
    116.4074000,
    50.00,
    5000,               -- 有效干扰半径 5km
    '[
        {"band_name": "VHF", "min_mhz": 30, "max_mhz": 300},
        {"band_name": "UHF", "min_mhz": 300, "max_mhz": 1000},
        {"band_name": "L-band", "min_mhz": 1000, "max_mhz": 2000},
        {"band_name": "S-band", "min_mhz": 2000, "max_mhz": 4000},
        {"band_name": "C-band", "min_mhz": 4000, "max_mhz": 8000}
    ]',
    500.00,             -- 最大发射功率 500W
    '{
        "antenna_type": "directional_phased_array",
        "azimuth_range_deg": 360,
        "elevation_range_deg": {"min": -10, "max": 60},
        "beam_width_deg": 15,
        "jamming_modes": ["spot", "barrage", "sweep", "reactive", "protocol_aware"],
        "simultaneous_targets": 20,
        "effective_erp_kw": 50,
        "polarization": ["vertical", "horizontal", "circular"]
    }',
    '2026-07-13 06:00:00',
    'v4.1.3',
    '192.168.10.103',
    8003,
    '{"default_mode": "reactive", "auto_trigger": true, "safe_freq_exclusions_mhz": [[88, 108], [960, 1215]]}',
    '宽带射频干扰系统，具备协议感知干扰能力。可选择性干扰无人机控制/图传链路，避免对民航/广播频段造成附带干扰。安全频段排除功能已配置。'
) ON DUPLICATE KEY UPDATE
    status = VALUES(status),
    last_health_check = VALUES(last_health_check),
    updated_at = CURRENT_TIMESTAMP;


-- 3.4 GNSS诱骗器 — 卫星导航欺骗
INSERT INTO device_registry (
    device_id, device_name, device_type, manufacturer, model, status,
    position_lat, position_lon, altitude_m, coverage_radius_m,
    frequency_range_mhz_json, max_power_w, capabilities_json,
    last_health_check, firmware_version, ip_address, port, configuration_json, notes
) VALUES (
    'gnsssp-001',
    'GNSS导航诱骗器 1号',
    'gnss_spoofer',
    'Regulus Cyber',
    'Regulus-Pyramid',
    'standby',
    39.9042000,
    116.4074000,
    50.00,
    3000,               -- 诱骗覆盖半径 3km
    '[
        {"band_name": "GPS_L1", "freq_mhz": 1575.42},
        {"band_name": "GPS_L2", "freq_mhz": 1227.60},
        {"band_name": "GLONASS_L1", "freq_mhz": 1602.00},
        {"band_name": "BeiDou_B1", "freq_mhz": 1561.098},
        {"band_name": "Galileo_E1", "freq_mhz": 1575.42}
    ]',
    10.00,              -- 发射功率 10W
    '{
        "target_protocols": ["NMEA", "UBX", "RTCM"],
        "spoofing_methods": ["stationary_offset", "trajectory_injection", "time_synchronization_attack"],
        "simultaneous_gnss_systems": 4,
        "max_simulated_satellites": 64,
        "signal_delay_resolution_ns": 0.1,
        "safe_zone_configurable": true,
        "spoof_modes": ["gentle_drift", "aggressive_relocation", "geo_fence_violation", "return_to_home_hijack"]
    }',
    '2026-07-13 05:45:00',
    'v1.8.2',
    '192.168.10.104',
    8004,
    '{"power_dbm": 40, "spoof_mode": "gentle_drift", "safe_zone_configured": true, "drift_rate_m_per_sec": 5}',
    'GNSS导航信号诱骗系统，支持GPS/GLONASS/BeiDou/Galileo四大系统同步欺骗。具备缓变偏移/激进重定位/地理围栏触发返航等多种欺骗模式。注意：仅对有GNSS依赖的无人机有效。'
) ON DUPLICATE KEY UPDATE
    status = VALUES(status),
    last_health_check = VALUES(last_health_check),
    updated_at = CURRENT_TIMESTAMP;


-- 3.5 光电/红外相机 — 视觉跟踪与识别
INSERT INTO device_registry (
    device_id, device_name, device_type, manufacturer, model, status,
    position_lat, position_lon, altitude_m, coverage_radius_m,
    frequency_range_mhz_json, max_power_w, capabilities_json,
    last_health_check, firmware_version, ip_address, port, configuration_json, notes
) VALUES (
    'eoir-001',
    '光电红外跟踪系统 1号',
    'eo_ir_camera',
    'FLIR Systems (Teledyne FLIR)',
    'FLIR-Ranger-HDC-MR',
    'online',
    39.9043000,
    116.4075000,
    55.00,
    6000,               -- 探测半径 6km（对小型无人机）
    '[]',               -- 无射频发射
    0.50,               -- 设备功耗约 500W
    '{
        "sensors": {
            "daylight": {"type": "CMOS", "resolution_mp": 20, "zoom": "30x_optical", "fov_horiz_deg": {"min": 1.2, "max": 63}},
            "thermal": {"type": "Cooled_MWIR", "resolution_px": "1280x1024", "zoom": "15x_optical", "NETD_mK": 20, "waveband_um": [3, 5]},
            "swir": {"type": "InGaAs", "resolution_px": "640x512", "waveband_um": [0.9, 1.7]},
            "laser_rangefinder": {"type": "Erbium_Glass", "wavelength_nm": 1550, "max_range_m": 20000, "accuracy_m": 1}
        },
        "tracking": {"auto_track_targets": 10, "tracking_algorithms": ["centroid", "correlation", "KCF", "DeepSORT"]},
        "classification": {"ai_model": "YOLOv8-ResNet", "drone_classes": 25, "inference_time_ms": 50}
    }',
    '2026-07-13 06:00:00',
    'v5.2.1',
    '192.168.10.105',
    8005,
    '{"day_night_mode": "auto", "auto_track_enabled": true, "recording_enabled": true, "encoding": "H.265"}',
    '多光谱光电红外转塔系统，集成高清昼光/制冷型中波红外/SWIR短波红外三通道传感器，内置激光测距仪和AI视觉分类。可全天候自动检测、跟踪和分类无人机目标。'
) ON DUPLICATE KEY UPDATE
    status = VALUES(status),
    last_health_check = VALUES(last_health_check),
    updated_at = CURRENT_TIMESTAMP;


-- 3.6 激光炫目器 — 光学传感器致盲
INSERT INTO device_registry (
    device_id, device_name, device_type, manufacturer, model, status,
    position_lat, position_lon, altitude_m, coverage_radius_m,
    frequency_range_mhz_json, max_power_w, capabilities_json,
    last_health_check, firmware_version, ip_address, port, configuration_json, notes
) VALUES (
    'laser-001',
    '激光炫目反制系统 1号',
    'laser_dazzler',
    'Rafael Advanced Defense Systems',
    'Drone-Dome-LD',
    'standby',
    39.9042000,
    116.4074000,
    50.00,
    3000,               -- 有效炫目距离 3km
    '[]',               -- 无射频发射
    150.00,             -- 激光输出功率 150W
    '{
        "laser_type": "Fiber_Diode_Pumped_Solid_State",
        "wavelengths_nm": [532, 808, 1064],
        "beam_divergence_mrad": 0.1,
        "tracking_accuracy_urad": 20,
        "targeting_sensor": "built_in_eo_ir",
        "engagement_time_s": {"min": 1, "typical": 5, "max": 30},
        "effect_modes": ["dazzle", "temporary_blind", "sensor_damage"],
        "eye_safe_distance_m": 500,
        "atmospheric_compensation": true
    }',
    '2026-07-13 05:30:00',
    'v3.0.1',
    '192.168.10.106',
    8006,
    '{"mode": "dazzle", "power_limit_pct": 60, "safe_zone_configured": true, "auto_targeting_enabled": false}',
    '高能激光炫目系统，集成自备光电跟踪模块，可在日光条件下对无人机光学/红外传感器实施致盲。具备人眼安全距离保护机制（500m自动切断），需操作员确认后方可执行炫目攻击。'
) ON DUPLICATE KEY UPDATE
    status = VALUES(status),
    last_health_check = VALUES(last_health_check),
    updated_at = CURRENT_TIMESTAMP;


-- =============================================================
-- 4. 规则版本种子数据（2条初始L2 DRL规则）
-- =============================================================

-- 4.1 规则版本 v1.0.0 — 低速消费级无人机处置规则
INSERT INTO rule_versions (
    version_id, rule_id, version_number, rule_content,
    change_description, changed_by, is_active, activation_date, created_at
) VALUES (
    'rule-low-slow-v1.0.0',
    'rule-low-slow',
    '1.0.0',
    '{
  "rule_id": "rule-low-slow",
  "rule_name": "低速消费级无人机处置规则",
  "description": "针对单一低速消费级四旋翼无人机在低空入侵时的标准处置流程。触发条件：目标分类为consumer_quadcopter，速度<30m/s，高度<500m，数量=1。",
  "version": "1.0.0",
  "type": "drl",
  "priority": 100,
  "conditions": {
    "all": [
      {"field": "target.category", "operator": "in", "value": ["consumer_quadcopter"]},
      {"field": "target.speed_ms", "operator": "lt", "value": 30},
      {"field": "target.altitude_m", "operator": "lt", "value": 500},
      {"field": "target.count", "operator": "eq", "value": 1}
    ]
  },
  "threat_assessment": {
    "base_threat_level": 1,
    "modifiers": [
      {"condition": "target.altitude_m < 50", "adjustment": 1},
      {"condition": "target.payload_suspected == true", "adjustment": 2},
      {"condition": "target.distance_to_critical_asset_m < 200", "adjustment": 2}
    ],
    "max_threat_level": 4
  },
  "actions": [
    {
      "priority": 1,
      "action": "rf_jamming_targeted",
      "params": {"device_id": "rfjam-001", "mode": "protocol_aware", "bands": ["2.4GHz", "5.8GHz"], "duration_s": 30},
      "expected_effect": "drone_enters_return_to_home",
      "success_indicator": "signal_loss_detected"
    },
    {
      "priority": 2,
      "action": "gnss_spoofing_gentle",
      "params": {"device_id": "gnsssp-001", "mode": "gentle_drift", "drift_rate_m_per_sec": 5, "duration_s": 60},
      "expected_effect": "drone_drifted_away",
      "success_indicator": "position_deviation_gt_50m",
      "condition": "action_1_failed"
    },
    {
      "priority": 3,
      "action": "notify_operator",
      "params": {"level": "WARN", "message": "低速消费级无人机处置失败，需人工介入"},
      "condition": "action_2_failed"
    }
  ],
  "time_constraints": {
    "max_total_engagement_s": 120,
    "action_interval_s": 5
  },
  "safe_mode": {
    "excluded_aircraft": ["民航客机", "通航飞行器", "警用无人机"],
    "geo_fence_check_required": true,
    "daylight_only": false
  }
}',
    '初始版本：定义低速消费级无人机标准处置流程。包含射频协议干扰、GNSS温和诱骗、操作员通知三级递进措施。',
    'sysadmin',
    1,
    '2026-07-01 00:00:00',
    '2026-07-01 00:00:00'
) ON DUPLICATE KEY UPDATE
    rule_content = VALUES(rule_content),
    is_active = VALUES(is_active),
    activation_date = VALUES(activation_date);


-- 4.2 规则版本 v1.0.0 — 高速FPV自杀式攻击应急规则
INSERT INTO rule_versions (
    version_id, rule_id, version_number, rule_content,
    change_description, changed_by, is_active, activation_date, created_at
) VALUES (
    'rule-highspeed-fpv-v1.0.0',
    'rule-highspeed-fpv',
    '1.0.0',
    '{
  "rule_id": "rule-highspeed-fpv",
  "rule_name": "高速FPV自杀式攻击应急规则",
  "description": "针对高速FPV穿越机自杀式攻击场景的紧急处置规则。触发条件：目标分类为diy_fpv，速度>20m/s，低空飞行，检测到爆炸物载荷特征。",
  "version": "1.0.0",
  "type": "drl",
  "priority": 1,
  "conditions": {
    "all": [
      {"field": "target.category", "operator": "in", "value": ["diy_fpv"]},
      {"field": "target.speed_ms", "operator": "gt", "value": 20},
      {"field": "target.altitude_m", "operator": "lt", "value": 300},
      {"field": "target.flight_pattern", "operator": "in", "value": ["high_speed_approach", "evasive_maneuver"]}
    ]
  },
  "threat_assessment": {
    "base_threat_level": 5,
    "modifiers": [
      {"condition": "target.distance_to_critical_asset_m < 500", "adjustment": 0, "note": "威胁等级已达最高"},
      {"condition": "target.payload_suspected == true", "adjustment": 0, "note": "已按最高威胁处置"},
      {"condition": "target.count > 3", "adjustment": 0, "note": "参见蜂群攻击规则"}
    ],
    "max_threat_level": 5,
    "immediate_action_required": true
  },
  "actions": [
    {
      "priority": 1,
      "action": "rf_jamming_wideband_emergency",
      "params": {
        "device_id": "rfjam-001",
        "mode": "barrage",
        "bands": ["5.8GHz", "2.4GHz", "915MHz", "1.3GHz"],
        "power_mode": "max",
        "duration_s": "continuous"
      },
      "expected_effect": "fpv_video_feed_lost_and_control_link_disrupted",
      "success_indicator": "drone_enters_failsafe_or_crash",
      "timeout_s": 5
    },
    {
      "priority": 2,
      "action": "activate_laser_dazzler",
      "params": {
        "device_id": "laser-001",
        "mode": "dazzle",
        "target": "fpv_camera_optical_path",
        "duration_s": "until_confirm_destroyed"
      },
      "expected_effect": "fpv_pilot_blinded",
      "success_indicator": "erratic_flight_detected",
      "timeout_s": 10
    },
    {
      "priority": 3,
      "action": "deploy_kinetic_interceptor",
      "params": {
        "device_id": "kinetic-001",
        "intercept_mode": "head_on",
        "warhead": "blast_fragmentation",
        "max_intercept_distance_m": 2000
      },
      "expected_effect": "target_physically_destroyed",
      "success_indicator": "radar_track_lost_after_intercept",
      "condition": "action_1_failed AND action_2_failed"
    },
    {
      "priority": 4,
      "action": "activate_perimeter_alarm",
      "params": {"level": "CRITICAL", "zone_id": "all", "alert_personnel": true},
      "condition": "action_3_executed"
    }
  ],
  "time_constraints": {
    "max_total_engagement_s": 15,
    "action_interval_s": 0
  },
  "safe_mode": {
    "kinetic_interceptor_safety_check": true,
    "blast_zone_clearance_check": true,
    "airspace_deconfliction": true
  }
}',
    '初始版本：定义高速FPV攻击应急处置流程。采用宽带全频阻塞干扰、激光炫目致盲、动能拦截三级防护，总响应窗口<15秒。',
    'sysadmin',
    1,
    '2026-07-01 00:00:00',
    '2026-07-01 00:00:00'
) ON DUPLICATE KEY UPDATE
    rule_content = VALUES(rule_content),
    is_active = VALUES(is_active),
    activation_date = VALUES(activation_date);


-- =============================================================
-- 5. 待审批规则种子数据（1条示例规则，用于展示审批流程）
-- =============================================================
INSERT INTO pending_rules (
    rule_id, rule_name, rule_type, rule_content, rule_metadata,
    proposed_by, approval_status, testing_results, activation_date, deactivation_date
) VALUES (
    'rule-swarm-basic',
    '无人机蜂群初步处置规则（待测试）',
    'drl',
    '{
  "rule_id": "rule-swarm-basic",
  "rule_name": "蜂群初步处置规则",
  "description": "针对10架以上无人机蜂群协同攻击的初步处置方案。本规则尚在测试阶段，需经模拟验证后方可激活。",
  "version": "0.1.0",
  "type": "drl",
  "priority": 0,
  "conditions": {
    "all": [
      {"field": "target.category", "operator": "in", "value": ["autonomous_swarm", "military_quadcopter"]},
      {"field": "target.count", "operator": "gte", "value": 10},
      {"field": "target.coordinated_behavior", "operator": "eq", "value": true}
    ]
  },
  "threat_assessment": {
    "base_threat_level": 5,
    "require_operator_confirmation": true,
    "recommend_llm_consultation": true
  },
  "actions": [
    {"priority": 1, "action": "activate_all_defense_systems", "params": {"mode": "auto_sequential"}},
    {"priority": 2, "action": "wide_area_rf_jamming", "params": {"device_id": "rfjam-001", "mode": "barrage", "bands": "all"}},
    {"priority": 3, "action": "mass_gnss_spoofing", "params": {"device_id": "gnsssp-001", "mode": "area_deception"}},
    {"priority": 4, "action": "priority_laser_engagement", "params": {"device_id": "laser-001", "target_selection": "closest_threat"}},
    {"priority": 5, "action": "escalate_to_llm", "params": {"reason": "swarm_engagement_complex"}}
  ]
}',
    '{"author": "tactical_team", "proposed_date": "2026-07-10", "estimated_complexity": "high", "dependencies": ["rule-low-slow", "rule-highspeed-fpv"]}',
    'tactical_team',
    'testing',
    '{"simulation_runs": 150, "avg_success_rate": 0.42, "false_positive_rate": 0.03, "avg_latency_ms": 8500, "notes": "蜂群处理延迟较大，宽频干扰对友军通信存在潜在影响，需进一步优化干扰策略。"}',
    NULL,
    NULL
) ON DUPLICATE KEY UPDATE
    rule_content = VALUES(rule_content),
    approval_status = VALUES(approval_status),
    testing_results = VALUES(testing_results),
    updated_at = CURRENT_TIMESTAMP;


-- =============================================================
-- 种子数据导入完成
-- 共导入:
--   drone_knowledge_base:  5 条无人机记录
--   scenario_library:      3 条场景模板
--   device_registry:       6 条设备记录
--   rule_versions:         2 条规则版本
--   pending_rules:         1 条待审批规则
-- =============================================================
