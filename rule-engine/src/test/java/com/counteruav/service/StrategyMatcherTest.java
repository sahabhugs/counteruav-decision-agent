package com.counteruav.service;

import com.counteruav.model.Device;
import com.counteruav.model.Device.DeviceStatus;
import com.counteruav.model.Device.DeviceType;
import com.counteruav.model.LatLonAlt;
import com.counteruav.model.Target;
import com.counteruav.model.Target.DroneCategory;
import com.counteruav.model.Target.StrategyType;
import com.counteruav.model.TargetDecision;
import com.counteruav.model.ThreatLevel;
import com.counteruav.service.ThreatEvaluator.ThreatScores;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

import java.util.*;

import static org.junit.jupiter.api.Assertions.*;

/**
 * StrategyMatcher 单元测试 - 策略匹配与设备分配
 *
 * 测试覆盖:
 * - 五级威胁响应策略 (CRITICAL → FULL_BAND_JAMMING, VERY_HIGH → RF_JAMMING, ...)
 * - 设备分配逻辑 (优先高威胁目标、设备状态过滤)
 * - ROE约束 (民用区域致命武器限制、人工审核标记)
 * - 边界条件 (空设备列表、null输入、无威胁评分)
 */
@DisplayName("StrategyMatcher - 策略匹配与设备分配测试")
class StrategyMatcherTest {

    private StrategyMatcher strategyMatcher;

    private LatLonAlt defenseCenter;

    private List<Device> availableDevices;

    @BeforeEach
    void setUp() {
        strategyMatcher = new StrategyMatcher();
        defenseCenter = LatLonAlt.builder()
                .lat(39.9042).lon(116.4074).altM(50.0).build();

        // 创建可用设备池
        availableDevices = new ArrayList<>();
        availableDevices.add(createDevice("DEV-RF-01", DeviceType.RF_JAMMER, DeviceStatus.ONLINE));
        availableDevices.add(createDevice("DEV-RF-02", DeviceType.RF_JAMMER, DeviceStatus.ONLINE));
        availableDevices.add(createDevice("DEV-GNSS-01", DeviceType.GNSS_SPOOFER, DeviceStatus.ONLINE));
        availableDevices.add(createDevice("DEV-LASER-01", DeviceType.LASER_WEAPON, DeviceStatus.ONLINE));
        availableDevices.add(createDevice("DEV-HPM-01", DeviceType.HPM_DEVICE, DeviceStatus.ONLINE));
    }

    // ==================== 分级响应策略测试 ====================

    @Nested
    @DisplayName("分级响应策略匹配")
    class TieredResponseStrategy {

        @Test
        @DisplayName("CRITICAL → 全频段干扰 + 激光摧毁")
        void testCriticalResponse_FullBandJammingAndLaser() {
            // Arrange
            Target target = createTarget("T-CRIT-01", DroneCategory.CLUSTER_SWARM, 95.0, ThreatLevel.CRITICAL);
            Map<String, ThreatScores> scores = createScores("T-CRIT-01", 0.95, ThreatLevel.CRITICAL);

            // Act
            Map<String, TargetDecision.ActionPlan> plans = strategyMatcher.matchStrategies(
                    Arrays.asList(target), scores, new ArrayList<>(availableDevices),
                    defenseCenter, false);

            // Assert
            TargetDecision.ActionPlan plan = plans.get("T-CRIT-01");
            assertNotNull(plan);
            assertEquals(10, plan.getPriority(), "CRITICAL优先级应为10");
            assertEquals("IMMEDIATE", plan.getTiming(), "CRITICAL应立即执行");
            assertNotNull(plan.getPrimary(), "主策略不应为null");
            assertEquals(StrategyType.FULL_BAND_JAMMING.getCode(), plan.getPrimary().getActionType(),
                    "CRITICAL主策略应为全频段干扰");
        }

        @Test
        @DisplayName("VERY_HIGH → 射频干扰 + GNSS欺骗")
        void testVeryHighResponse_RfJammingAndGnssSpoofing() {
            // Arrange
            Target target = createTarget("T-VH-01", DroneCategory.MILITARY_FIXED_WING, 82.0, ThreatLevel.VERY_HIGH);
            Map<String, ThreatScores> scores = createScores("T-VH-01", 0.82, ThreatLevel.VERY_HIGH);

            // Act
            Map<String, TargetDecision.ActionPlan> plans = strategyMatcher.matchStrategies(
                    Arrays.asList(target), scores, new ArrayList<>(availableDevices),
                    defenseCenter, false);

            // Assert
            TargetDecision.ActionPlan plan = plans.get("T-VH-01");
            assertNotNull(plan);
            assertEquals(8, plan.getPriority());
            assertEquals("WITHIN_30S", plan.getTiming());
            assertEquals(StrategyType.RF_JAMMING.getCode(), plan.getPrimary().getActionType());
            assertEquals(StrategyType.GNSS_SPOOFING.getCode(), plan.getSecondary().getActionType());
            // 确认禁止使用激光和动能拦截
            assertNotNull(plan.getAvoid());
            assertTrue(plan.getAvoid().size() >= 2, "应至少禁止2个致命策略");
        }

        @Test
        @DisplayName("HIGH → 单频段射频干扰")
        void testHighResponse_SingleBandRfJamming() {
            // Arrange
            Target target = createTarget("T-H-01", DroneCategory.CONSUMER_QUADCOPTER, 65.0, ThreatLevel.HIGH);
            Map<String, ThreatScores> scores = createScores("T-H-01", 0.65, ThreatLevel.HIGH);

            // Act
            Map<String, TargetDecision.ActionPlan> plans = strategyMatcher.matchStrategies(
                    Arrays.asList(target), scores, new ArrayList<>(availableDevices),
                    defenseCenter, false);

            // Assert
            TargetDecision.ActionPlan plan = plans.get("T-H-01");
            assertNotNull(plan);
            assertEquals(5, plan.getPriority());
            assertEquals("WITHIN_60S", plan.getTiming());
            assertEquals(StrategyType.RF_JAMMING.getCode(), plan.getPrimary().getActionType());
        }

        @Test
        @DisplayName("MEDIUM → 声光警告 + 增强跟踪")
        void testMediumResponse_WarnAndMonitor() {
            // Arrange
            Target target = createTarget("T-M-01", DroneCategory.CONSUMER_QUADCOPTER, 35.0, ThreatLevel.MEDIUM);
            Map<String, ThreatScores> scores = createScores("T-M-01", 0.35, ThreatLevel.MEDIUM);

            // Act
            Map<String, TargetDecision.ActionPlan> plans = strategyMatcher.matchStrategies(
                    Arrays.asList(target), scores, new ArrayList<>(availableDevices),
                    defenseCenter, false);

            // Assert
            TargetDecision.ActionPlan plan = plans.get("T-M-01");
            assertNotNull(plan);
            assertEquals(3, plan.getPriority());
            assertEquals("WITHIN_5MIN", plan.getTiming());
            assertEquals(StrategyType.WARN.getCode(), plan.getPrimary().getActionType());
        }

        @Test
        @DisplayName("LOW → 标准跟踪")
        void testLowResponse_Monitor() {
            // Arrange
            Target target = createTarget("T-L-01", DroneCategory.CONSUMER_QUADCOPTER, 10.0, ThreatLevel.LOW);
            Map<String, ThreatScores> scores = createScores("T-L-01", 0.10, ThreatLevel.LOW);

            // Act
            Map<String, TargetDecision.ActionPlan> plans = strategyMatcher.matchStrategies(
                    Arrays.asList(target), scores, new ArrayList<>(availableDevices),
                    defenseCenter, false);

            // Assert
            TargetDecision.ActionPlan plan = plans.get("T-L-01");
            assertNotNull(plan);
            assertEquals(1, plan.getPriority());
            assertEquals("MONITOR", plan.getTiming());
            assertEquals(StrategyType.MONITOR.getCode(), plan.getPrimary().getActionType());
        }
    }

    // ==================== ROE约束测试 ====================

    @Nested
    @DisplayName("交战规则(ROE)约束")
    class ROEConstraints {

        @Test
        @DisplayName("民用区域禁止致命武器 - CRITICAL降级为射频干扰")
        void testCivilianArea_BlocksLethalWeapons() {
            // Arrange
            Target target = createTarget("T-ROE-01", DroneCategory.CLUSTER_SWARM, 90.0, ThreatLevel.CRITICAL);
            target.setOverCivilianArea(true);
            Map<String, ThreatScores> scores = createScores("T-ROE-01", 0.90, ThreatLevel.CRITICAL);

            // Act
            Map<String, TargetDecision.ActionPlan> plans = strategyMatcher.matchStrategies(
                    Arrays.asList(target), scores, new ArrayList<>(availableDevices),
                    defenseCenter, true); // isOverCivilianArea = true

            // Assert
            TargetDecision.ActionPlan plan = plans.get("T-ROE-01");
            assertNotNull(plan);
            // 主策略应该是非致命手段（不应是LASER或KINETIC）
            String primaryAction = plan.getPrimary().getActionType();
            assertFalse(primaryAction.contains("LASER"),
                    "民用区域不应使用激光武器, 实际=" + primaryAction);
            assertFalse(primaryAction.contains("KINETIC"),
                    "民用区域不应使用动能拦截, 实际=" + primaryAction);
        }

        @Test
        @DisplayName("民用区域高威胁目标需人工审核")
        void testCivilianAreaHighThreat_NeedsHumanReview() {
            // Arrange
            Target target = createTarget("T-ROE-02", DroneCategory.MILITARY_FIXED_WING, 85.0, ThreatLevel.VERY_HIGH);
            target.setOverCivilianArea(true);
            Map<String, ThreatScores> scores = createScores("T-ROE-02", 0.85, ThreatLevel.VERY_HIGH);

            // Act
            Map<String, TargetDecision.ActionPlan> plans = strategyMatcher.matchStrategies(
                    Arrays.asList(target), scores, new ArrayList<>(availableDevices),
                    defenseCenter, true);

            // Assert
            TargetDecision.ActionPlan plan = plans.get("T-ROE-02");
            assertNotNull(plan);
            assertTrue(plan.isNeedsHumanReview(),
                    "民用区域高威胁目标(level>=4)需人工审核");
        }
    }

    // ==================== 设备分配测试 ====================

    @Nested
    @DisplayName("设备分配逻辑")
    class DeviceAllocation {

        @Test
        @DisplayName("高威胁目标优先获取设备")
        void testHighThreatGetsPriorityDevice() {
            // Arrange
            Target criticalTarget = createTarget("T-PRI-01", DroneCategory.CLUSTER_SWARM, 95.0, ThreatLevel.CRITICAL);
            Target lowTarget = createTarget("T-PRI-02", DroneCategory.CONSUMER_QUADCOPTER, 10.0, ThreatLevel.LOW);

            Map<String, ThreatScores> scores = new LinkedHashMap<>();
            scores.put("T-PRI-01", createSingleScore("T-PRI-01", 0.95, ThreatLevel.CRITICAL));
            scores.put("T-PRI-02", createSingleScore("T-PRI-02", 0.10, ThreatLevel.LOW));

            // Act
            Map<String, TargetDecision.ActionPlan> plans = strategyMatcher.matchStrategies(
                    Arrays.asList(lowTarget, criticalTarget), scores,
                    new ArrayList<>(availableDevices), defenseCenter, false);

            // Assert
            TargetDecision.ActionPlan criticalPlan = plans.get("T-PRI-01");
            TargetDecision.ActionPlan lowPlan = plans.get("T-PRI-02");
            assertNotNull(criticalPlan);
            assertNotNull(lowPlan);
            // CRITICAL应有设备分配（deviceId不为null）
            assertNotNull(criticalPlan.getPrimary().getDeviceId(),
                    "CRITICAL目标应优先分配设备");
        }

        @Test
        @DisplayName("设备分配后应从可用池移除")
        void testDeviceRemovedAfterAllocation() {
            // Arrange: 创建大量CRITICAL目标，设备不够用
            List<Target> targets = new ArrayList<>();
            Map<String, ThreatScores> scores = new LinkedHashMap<>();
            for (int i = 0; i < 5; i++) {
                Target t = createTarget("T-MULTI-" + i, DroneCategory.CLUSTER_SWARM, 95.0, ThreatLevel.CRITICAL);
                targets.add(t);
                scores.put("T-MULTI-" + i, createSingleScore("T-MULTI-" + i, 0.95, ThreatLevel.CRITICAL));
            }

            // Act
            List<Device> devices = new ArrayList<>(availableDevices);
            Map<String, TargetDecision.ActionPlan> plans = strategyMatcher.matchStrategies(
                    targets, scores, devices, defenseCenter, false);

            // Assert: 所有目标都有计划
            assertEquals(5, plans.size());
        }

        @Test
        @DisplayName("仅分配在线设备")
        void testOnlyAllocatesOnlineDevices() {
            // Arrange
            Target target = createTarget("T-ONL-01", DroneCategory.MILITARY_FIXED_WING, 80.0, ThreatLevel.VERY_HIGH);
            Map<String, ThreatScores> scores = createScores("T-ONL-01", 0.80, ThreatLevel.VERY_HIGH);

            List<Device> mixedDevices = new ArrayList<>();
            mixedDevices.add(createDevice("DEV-OFFLINE", DeviceType.RF_JAMMER, DeviceStatus.OFFLINE));
            mixedDevices.add(createDevice("DEV-FAULT", DeviceType.RF_JAMMER, DeviceStatus.FAULT));
            mixedDevices.add(createDevice("DEV-ONLINE", DeviceType.RF_JAMMER, DeviceStatus.ONLINE));

            // Act
            Map<String, TargetDecision.ActionPlan> plans = strategyMatcher.matchStrategies(
                    Arrays.asList(target), scores, mixedDevices, defenseCenter, false);

            // Assert
            TargetDecision.ActionPlan plan = plans.get("T-ONL-01");
            assertNotNull(plan);
            if (plan.getPrimary().getDeviceId() != null) {
                assertEquals("DEV-ONLINE", plan.getPrimary().getDeviceId(),
                        "应分配在线设备而非离线/故障设备");
            }
        }
    }

    // ==================== 边界条件测试 ====================

    @Nested
    @DisplayName("边界条件与异常处理")
    class BoundaryAndEdgeCases {

        @Test
        @DisplayName("空目标列表应返回空Map")
        void testEmptyTargetList() {
            Map<String, TargetDecision.ActionPlan> plans = strategyMatcher.matchStrategies(
                    new ArrayList<>(), new LinkedHashMap<>(),
                    availableDevices, defenseCenter, false);

            assertNotNull(plans);
            assertTrue(plans.isEmpty());
        }

        @Test
        @DisplayName("null目标列表应返回空Map")
        void testNullTargetList() {
            Map<String, TargetDecision.ActionPlan> plans = strategyMatcher.matchStrategies(
                    null, new LinkedHashMap<>(),
                    availableDevices, defenseCenter, false);

            assertNotNull(plans);
            assertTrue(plans.isEmpty());
        }

        @Test
        @DisplayName("缺少威胁评分时使用默认保守策略")
        void testMissingThreatScoresDefaultConservative() {
            // Arrange
            Target target = createTarget("T-NOSCORE-01", DroneCategory.UNKNOWN, 0, ThreatLevel.LOW);
            Map<String, ThreatScores> scores = new LinkedHashMap<>(); // 空

            // Act
            Map<String, TargetDecision.ActionPlan> plans = strategyMatcher.matchStrategies(
                    Arrays.asList(target), scores, availableDevices, defenseCenter, false);

            // Assert
            TargetDecision.ActionPlan plan = plans.get("T-NOSCORE-01");
            assertNotNull(plan, "缺少评分时应有默认策略");
            assertEquals(StrategyType.MONITOR.getCode(), plan.getPrimary().getActionType(),
                    "缺少评分时默认应为监视策略");
        }

        @Test
        @DisplayName("空设备列表仍应生成策略计划")
        void testEmptyDeviceList() {
            Target target = createTarget("T-NODEV-01", DroneCategory.CLUSTER_SWARM, 90.0, ThreatLevel.CRITICAL);
            Map<String, ThreatScores> scores = createScores("T-NODEV-01", 0.90, ThreatLevel.CRITICAL);

            Map<String, TargetDecision.ActionPlan> plans = strategyMatcher.matchStrategies(
                    Arrays.asList(target), scores, new ArrayList<>(),
                    defenseCenter, false);

            TargetDecision.ActionPlan plan = plans.get("T-NODEV-01");
            assertNotNull(plan, "即使无设备也应有策略计划");
            assertNotNull(plan.getPrimary(), "主策略不应为null");
            // 无设备时deviceId应为null
            assertNull(plan.getPrimary().getDeviceId(), "无设备时deviceId应为null");
        }
    }

    // ==================== 辅助方法 ====================

    private Device createDevice(String id, DeviceType type, DeviceStatus status) {
        return Device.builder()
                .deviceId(id)
                .type(type)
                .status(status)
                .position(LatLonAlt.builder().lat(39.9042).lon(116.4074).altM(50).build())
                .effectiveRangeM(3000.0)
                .frequencyCoverage(Arrays.asList("2.4GHz", "5.8GHz"))
                .build();
    }

    private Target createTarget(String id, DroneCategory category, double threatScore, ThreatLevel level) {
        return Target.builder()
                .targetId(id)
                .position(LatLonAlt.builder().lat(39.9050).lon(116.4080).altM(100).build())
                .velocityMs(25.0)
                .headingDeg(180.0)
                .radialSpeedMs(12.0)
                .droneCategory(category)
                .dwellTimeS(120)
                .threatScore(threatScore)
                .threatLevel(level)
                .threatBehaviorTags(new ArrayList<>())
                .isOverCivilianArea(false)
                .build();
    }

    private Map<String, ThreatScores> createScores(String targetId, double closeness, ThreatLevel level) {
        Map<String, ThreatScores> scores = new LinkedHashMap<>();
        scores.put(targetId, createSingleScore(targetId, closeness, level));
        return scores;
    }

    private ThreatScores createSingleScore(String targetId, double closeness, ThreatLevel level) {
        ThreatScores ts = new ThreatScores();
        ts.setTargetId(targetId);
        ts.setClosenessCoefficient(closeness);
        ts.setThreatScore(closeness * 100);
        ts.setThreatLevel(level);
        ts.setIndicatorScores(new LinkedHashMap<>());
        return ts;
    }
}
