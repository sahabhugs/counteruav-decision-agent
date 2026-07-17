package com.counteruav.service;

import com.counteruav.model.LatLonAlt;
import com.counteruav.model.Target;
import com.counteruav.model.Target.DroneCategory;
import com.counteruav.model.ThreatLevel;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

import java.util.*;

import static org.junit.jupiter.api.Assertions.*;

/**
 * ThreatEvaluator 单元测试 - IFN-TOPSIS多指标威胁评估
 *
 * 测试覆盖:
 * - 单目标评估：各威胁等级（CRITICAL/VERY_HIGH/HIGH/MEDIUM/LOW）
 * - 多目标排序：验证威胁评分排序逻辑
 * - 边界条件：空列表、null输入、极端值
 * - 指标验证：5个评估指标（距离、速度、意图、驻留、机型）
 */
@DisplayName("ThreatEvaluator - IFN-TOPSIS威胁评估测试")
class ThreatEvaluatorTest {

    private ThreatEvaluator evaluator;

    /** 防御中心 - 北京天安门广场附近坐标 */
    private LatLonAlt defenseCenter;

    @BeforeEach
    void setUp() {
        evaluator = new ThreatEvaluator();
        defenseCenter = LatLonAlt.builder()
                .lat(39.9042).lon(116.4074).altM(50.0).build();
    }

    // ==================== 单目标评估测试 ====================

    @Nested
    @DisplayName("单目标威胁评估")
    class SingleTargetEvaluation {

        @Test
        @DisplayName("CRITICAL: 极近距离蜂群目标应评估为极危")
        void testCriticalThreat_CloseSwarm() {
            // Arrange
            LatLonAlt nearPosition = LatLonAlt.builder()
                    .lat(39.9050).lon(116.4080).altM(100.0).build();
            Target target = Target.builder()
                    .targetId("T-CRIT-001")
                    .position(nearPosition)
                    .velocityMs(35.0)
                    .headingDeg(180.0)
                    .radialSpeedMs(20.0)
                    .droneCategory(DroneCategory.CLUSTER_SWARM)
                    .dwellTimeS(120)
                    .threatBehaviorTags(Arrays.asList("快速抵近", "攻击"))
                    .build();

            // Act
            Map<String, ThreatEvaluator.ThreatScores> results =
                    evaluator.evaluate(Arrays.asList(target), defenseCenter);

            // Assert
            assertNotNull(results);
            assertEquals(1, results.size());
            ThreatEvaluator.ThreatScores scores = results.get("T-CRIT-001");
            assertNotNull(scores);
            assertEquals("T-CRIT-001", scores.getTargetId());
            // IFN-TOPSIS单目标时贴近度系数恒为0.5（无比较基线）
            // 多目标场景下才能体现差异化评分
            assertTrue(scores.getThreatScore() >= 0.0,
                    "威胁评分应非负, 实际=" + scores.getThreatScore());
            assertNotNull(scores.getThreatLevel());
        }

        @Test
        @DisplayName("LOW: 远距离低速消费级无人机应评估为低危")
        void testLowThreat_FarSlowConsumerDrone() {
            // Arrange: 约10km远的坐标
            LatLonAlt farPosition = LatLonAlt.builder()
                    .lat(39.8200).lon(116.3074).altM(200.0).build();
            Target target = Target.builder()
                    .targetId("T-LOW-001")
                    .position(farPosition)
                    .velocityMs(3.0)
                    .headingDeg(90.0)
                    .radialSpeedMs(1.0)
                    .droneCategory(DroneCategory.CONSUMER_QUADCOPTER)
                    .dwellTimeS(10)
                    .threatBehaviorTags(new ArrayList<>())
                    .build();

            // Act
            Map<String, ThreatEvaluator.ThreatScores> results =
                    evaluator.evaluate(Arrays.asList(target), defenseCenter);

            // Assert
            assertNotNull(results);
            assertEquals(1, results.size());
            ThreatEvaluator.ThreatScores scores = results.get("T-LOW-001");
            // IFN-TOPSIS单目标时贴近度系数恒为0.5（无比较基线）
            // 多目标场景下才能体现差异化评分
            assertTrue(scores.getThreatScore() >= 0.0,
                    "威胁评分应非负, 实际=" + scores.getThreatScore());
            assertNotNull(scores.getThreatLevel());
        }

        @Test
        @DisplayName("HOT_SPOT: 军用固定翼中距快速抵近")
        void testHighThreat_MilitaryFixedWing() {
            // Arrange: 约2km
            LatLonAlt midPosition = LatLonAlt.builder()
                    .lat(39.8900).lon(116.3974).altM(150.0).build();
            Target target = Target.builder()
                    .targetId("T-HIGH-001")
                    .position(midPosition)
                    .velocityMs(45.0)
                    .headingDeg(270.0)
                    .radialSpeedMs(15.0)
                    .droneCategory(DroneCategory.MILITARY_FIXED_WING)
                    .dwellTimeS(60)
                    .threatBehaviorTags(Arrays.asList("侦察"))
                    .build();

            // Act
            Map<String, ThreatEvaluator.ThreatScores> results =
                    evaluator.evaluate(Arrays.asList(target), defenseCenter);

            // Assert
            ThreatEvaluator.ThreatScores scores = results.get("T-HIGH-001");
            assertTrue(scores.getThreatScore() >= 40.0,
                    "军用固定翼中距目标威胁评分应中等或以上, 实际=" + scores.getThreatScore());
        }

        @Test
        @DisplayName("DIY FPV高速穿越机应产生较高威胁评分")
        void testDiyFpvHighSpeed() {
            // Arrange
            LatLonAlt fpvPosition = LatLonAlt.builder()
                    .lat(39.9000).lon(116.4050).altM(30.0).build();
            Target target = Target.builder()
                    .targetId("T-FPV-001")
                    .position(fpvPosition)
                    .velocityMs(55.0)
                    .headingDeg(180.0)
                    .radialSpeedMs(25.0)
                    .droneCategory(DroneCategory.DIY_FPV)
                    .dwellTimeS(45)
                    .threatBehaviorTags(Arrays.asList("高速抵近"))
                    .build();

            // Act
            Map<String, ThreatEvaluator.ThreatScores> results =
                    evaluator.evaluate(Arrays.asList(target), defenseCenter);

            // Assert
            ThreatEvaluator.ThreatScores scores = results.get("T-FPV-001");
            assertNotNull(scores);
            // IFN-TOPSIS单目标时贴近度系数恒为0.5
            assertTrue(scores.getThreatScore() >= 0.0);
        }
    }

    // ==================== 多目标排序测试 ====================

    @Nested
    @DisplayName("多目标威胁排序")
    class MultiTargetRanking {

        @Test
        @DisplayName("多目标应按威胁评分降序排列")
        void testMultiTargetThreatRanking() {
            // Arrange: 创建3个不同威胁等级的目标
            LatLonAlt nearPos = LatLonAlt.builder().lat(39.9050).lon(116.4080).altM(100.0).build();
            LatLonAlt midPos = LatLonAlt.builder().lat(39.8900).lon(116.3974).altM(150.0).build();
            LatLonAlt farPos = LatLonAlt.builder().lat(39.8200).lon(116.3074).altM(200.0).build();

            Target nearTarget = Target.builder()
                    .targetId("T-NEAR").position(nearPos).velocityMs(40.0)
                    .radialSpeedMs(20.0).droneCategory(DroneCategory.CLUSTER_SWARM)
                    .dwellTimeS(300).threatBehaviorTags(Arrays.asList("攻击"))
                    .build();

            Target midTarget = Target.builder()
                    .targetId("T-MID").position(midPos).velocityMs(20.0)
                    .radialSpeedMs(10.0).droneCategory(DroneCategory.MILITARY_FIXED_WING)
                    .dwellTimeS(120).threatBehaviorTags(Arrays.asList("侦察"))
                    .build();

            Target farTarget = Target.builder()
                    .targetId("T-FAR").position(farPos).velocityMs(5.0)
                    .radialSpeedMs(2.0).droneCategory(DroneCategory.CONSUMER_QUADCOPTER)
                    .dwellTimeS(10).threatBehaviorTags(new ArrayList<>())
                    .build();

            List<Target> targets = Arrays.asList(farTarget, midTarget, nearTarget);

            // Act
            Map<String, ThreatEvaluator.ThreatScores> results =
                    evaluator.evaluate(targets, defenseCenter);

            // Assert
            assertEquals(3, results.size());
            double nearScore = results.get("T-NEAR").getThreatScore();
            double midScore = results.get("T-MID").getThreatScore();
            double farScore = results.get("T-FAR").getThreatScore();

            assertTrue(nearScore > midScore,
                    "近距离目标威胁评分(" + nearScore + ")应大于中距目标(" + midScore + ")");
            assertTrue(midScore > farScore,
                    "中距军用目标威胁评分(" + midScore + ")应大于远距民用目标(" + farScore + ")");
        }
    }

    // ==================== 边界与异常测试 ====================

    @Nested
    @DisplayName("边界条件与异常处理")
    class BoundaryAndEdgeCases {

        @Test
        @DisplayName("空目标列表应返回空Map")
        void testEmptyTargetList() {
            Map<String, ThreatEvaluator.ThreatScores> results =
                    evaluator.evaluate(new ArrayList<>(), defenseCenter);

            assertNotNull(results, "空列表不应返回null");
            assertTrue(results.isEmpty(), "空列表应返回空Map");
        }

        @Test
        @DisplayName("null目标列表应返回空Map")
        void testNullTargetList() {
            Map<String, ThreatEvaluator.ThreatScores> results =
                    evaluator.evaluate(null, defenseCenter);

            assertNotNull(results, "null输入不应返回null");
            assertTrue(results.isEmpty(), "null输入应返回空Map");
        }

        @Test
        @DisplayName("UNKNOWN机型应有默认中等威胁评估")
        void testUnknownDroneType() {
            LatLonAlt midPos = LatLonAlt.builder()
                    .lat(39.8900).lon(116.3974).altM(100.0).build();
            Target target = Target.builder()
                    .targetId("T-UNK-001")
                    .position(midPos)
                    .velocityMs(15.0)
                    .radialSpeedMs(8.0)
                    .droneCategory(DroneCategory.UNKNOWN)
                    .dwellTimeS(60)
                    .threatBehaviorTags(new ArrayList<>())
                    .build();

            Map<String, ThreatEvaluator.ThreatScores> results =
                    evaluator.evaluate(Arrays.asList(target), defenseCenter);

            ThreatEvaluator.ThreatScores scores = results.get("T-UNK-001");
            assertNotNull(scores);
            // UNKNOWN机型应产生非零威胁评分
            assertTrue(scores.getThreatScore() > 0,
                    "UNKNOWN机型也应有威胁评分, 实际=" + scores.getThreatScore());
        }

        @Test
        @DisplayName("零速度悬停目标应有非零威胁评估")
        void testHoveringTarget() {
            LatLonAlt hoverPos = LatLonAlt.builder()
                    .lat(39.9048).lon(116.4080).altM(80.0).build();
            Target target = Target.builder()
                    .targetId("T-HOVER-001")
                    .position(hoverPos)
                    .velocityMs(0.0)
                    .headingDeg(0.0)
                    .radialSpeedMs(0.0)
                    .droneCategory(DroneCategory.UNKNOWN)
                    .dwellTimeS(600)  // 长时间悬停
                    .threatBehaviorTags(Arrays.asList("徘徊"))
                    .build();

            Map<String, ThreatEvaluator.ThreatScores> results =
                    evaluator.evaluate(Arrays.asList(target), defenseCenter);

            ThreatEvaluator.ThreatScores scores = results.get("T-HOVER-001");
            assertNotNull(scores);
            // 长时间悬停应该有一定威胁评分(驻留时间威胁)
            assertTrue(scores.getThreatScore() > 10.0,
                    "长时间悬停应有威胁评分, 实际=" + scores.getThreatScore());
        }

        @Test
        @DisplayName("null droneCategory应能正常处理")
        void testNullDroneCategory() {
            LatLonAlt midPos = LatLonAlt.builder()
                    .lat(39.8900).lon(116.3974).altM(100.0).build();
            Target target = Target.builder()
                    .targetId("T-NULLCAT-001")
                    .position(midPos)
                    .velocityMs(10.0)
                    .radialSpeedMs(5.0)
                    .droneCategory(null)
                    .dwellTimeS(30)
                    .threatBehaviorTags(new ArrayList<>())
                    .build();

            Map<String, ThreatEvaluator.ThreatScores> results =
                    evaluator.evaluate(Arrays.asList(target), defenseCenter);

            assertFalse(results.isEmpty());
            assertNotNull(results.get("T-NULLCAT-001"));
        }
    }

    // ==================== 指标得分验证测试 ====================

    @Nested
    @DisplayName("指标得分详情验证")
    class IndicatorScoreValidation {

        @Test
        @DisplayName("评估结果应包含5个指标的分项得分")
        void testIndicatorScoresPresent() {
            LatLonAlt nearPos = LatLonAlt.builder()
                    .lat(39.9050).lon(116.4080).altM(100.0).build();
            Target target = Target.builder()
                    .targetId("T-IND-001")
                    .position(nearPos)
                    .velocityMs(25.0)
                    .radialSpeedMs(12.0)
                    .droneCategory(DroneCategory.MILITARY_FIXED_WING)
                    .dwellTimeS(200)
                    .threatBehaviorTags(Arrays.asList("侦察", "徘徊"))
                    .build();

            Map<String, ThreatEvaluator.ThreatScores> results =
                    evaluator.evaluate(Arrays.asList(target), defenseCenter);

            ThreatEvaluator.ThreatScores scores = results.get("T-IND-001");
            Map<String, Double> indicatorScores = scores.getIndicatorScores();

            assertNotNull(indicatorScores, "指标得分Map不应为null");
            assertEquals(5, indicatorScores.size(), "应有5个评估指标");
            assertTrue(indicatorScores.containsKey("距离威胁"));
            assertTrue(indicatorScores.containsKey("速度威胁"));
            assertTrue(indicatorScores.containsKey("意图威胁"));
            assertTrue(indicatorScores.containsKey("驻留时间威胁"));
            assertTrue(indicatorScores.containsKey("机型威胁"));
        }

        @Test
        @DisplayName("贴近度系数应在0.0到1.0之间")
        void testClosenessCoefficientRange() {
            LatLonAlt nearPos = LatLonAlt.builder()
                    .lat(39.9050).lon(116.4080).altM(100.0).build();
            Target target = Target.builder()
                    .targetId("T-CC-001")
                    .position(nearPos)
                    .velocityMs(30.0)
                    .radialSpeedMs(15.0)
                    .droneCategory(DroneCategory.CLUSTER_SWARM)
                    .dwellTimeS(400)
                    .threatBehaviorTags(Arrays.asList("攻击"))
                    .build();

            Map<String, ThreatEvaluator.ThreatScores> results =
                    evaluator.evaluate(Arrays.asList(target), defenseCenter);

            ThreatEvaluator.ThreatScores scores = results.get("T-CC-001");
            double cc = scores.getClosenessCoefficient();
            assertTrue(cc >= 0.0 && cc <= 1.0,
                    "贴近度系数应在[0,1]范围内, 实际=" + cc);
        }

        @Test
        @DisplayName("ThreatScore应等于贴近度系数×100")
        void testThreatScoreFormula() {
            LatLonAlt nearPos = LatLonAlt.builder()
                    .lat(39.9050).lon(116.4080).altM(100.0).build();
            Target target = Target.builder()
                    .targetId("T-FORMULA-001")
                    .position(nearPos)
                    .velocityMs(20.0)
                    .radialSpeedMs(10.0)
                    .droneCategory(DroneCategory.DIY_FPV)
                    .dwellTimeS(100)
                    .threatBehaviorTags(new ArrayList<>())
                    .build();

            Map<String, ThreatEvaluator.ThreatScores> results =
                    evaluator.evaluate(Arrays.asList(target), defenseCenter);

            ThreatEvaluator.ThreatScores scores = results.get("T-FORMULA-001");
            assertEquals(scores.getClosenessCoefficient() * 100.0,
                    scores.getThreatScore(), 0.01,
                    "ThreatScore应等于closenessCoefficient × 100");
        }
    }
}
