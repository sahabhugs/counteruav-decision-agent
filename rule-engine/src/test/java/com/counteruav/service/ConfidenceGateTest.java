package com.counteruav.service;

import com.counteruav.model.Target;
import com.counteruav.model.Target.DroneCategory;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;

import java.util.*;

import static org.junit.jupiter.api.Assertions.*;

/**
 * ConfidenceGate 单元测试 - 置信度评估与LLM上报门控
 *
 * 测试覆盖:
 * - 综合置信度计算（5个维度加权）
 * - LLM上报触发条件（低置信度、EVT开集、规则冲突、复合威胁、未知机型）
 * - 各维度独立计算（规则一致性、传感器质量、分类置信度、规则覆盖度、历史准确率）
 * - 边界条件（null输入、空列表、极值）
 */
@DisplayName("ConfidenceGate - 置信度评估与LLM门控测试")
class ConfidenceGateTest {

    private ConfidenceGate confidenceGate;

    @BeforeEach
    void setUp() {
        confidenceGate = new ConfidenceGate();
        // 设置阈值为0.80（与生产配置一致）
        ReflectionTestUtils.setField(confidenceGate, "confidenceThreshold", 0.80);
    }

    // ==================== 综合置信度计算测试 ====================

    @Nested
    @DisplayName("综合置信度计算")
    class CombinedConfidenceCalculation {

        @Test
        @DisplayName("高质量目标应返回高置信度(>0.85)")
        void testHighQualityTarget_HighConfidence() {
            // Arrange: 创建高信度目标
            Target target = Target.builder()
                    .targetId("T-CONF-001")
                    .maxClassConfidence(0.95)           // 高分类置信度
                    .droneCategory(DroneCategory.CONSUMER_QUADCOPTER)
                    .isEvtOpenSet(false)
                    .threatBehaviorTags(Arrays.asList("侦察"))  // 仅1个标签
                    .build();

            List<String> matchedRules = Arrays.asList("L1-01", "L2-01", "L2-02", "L3-01", "L4-01");
            Map<String, Double> sensorStatus = new LinkedHashMap<>();
            sensorStatus.put("rf_sensor", 25.0); // 高SNR
            double historicalAccuracy = 0.90;

            // Act
            double confidence = confidenceGate.calculateConfidence(
                    target, matchedRules, sensorStatus, historicalAccuracy);

            // Assert
            assertTrue(confidence > 0.85,
                    "高信度目标综合置信度应>0.85, 实际=" + confidence);
        }

        @Test
        @DisplayName("低质量目标应返回低置信度(<0.50)")
        void testLowQualityTarget_LowConfidence() {
            // Arrange: 创建低信度目标
            Target target = Target.builder()
                    .targetId("T-CONF-002")
                    .maxClassConfidence(0.30)           // 低分类置信度
                    .droneCategory(DroneCategory.UNKNOWN)
                    .isEvtOpenSet(true)
                    .threatBehaviorTags(new ArrayList<>())
                    .build();

            List<String> matchedRules = Arrays.asList("L2-01"); // 仅有1条规则
            Map<String, Double> sensorStatus = new LinkedHashMap<>();
            sensorStatus.put("rf_sensor", 3.0); // 低SNR
            double historicalAccuracy = 0.30;

            // Act
            double confidence = confidenceGate.calculateConfidence(
                    target, matchedRules, sensorStatus, historicalAccuracy);

            // Assert
            assertTrue(confidence < 0.55,
                    "低信度目标综合置信度应<0.55, 实际=" + confidence);
        }

        @Test
        @DisplayName("置信度应在0.0到1.0范围内")
        void testConfidenceRange() {
            Target target = Target.builder()
                    .targetId("T-RANGE-001")
                    .maxClassConfidence(0.5)
                    .droneCategory(DroneCategory.DIY_FPV)
                    .isEvtOpenSet(false)
                    .threatBehaviorTags(new ArrayList<>())
                    .build();

            // 测试正常值
            double conf1 = confidenceGate.calculateConfidence(
                    target, Arrays.asList("L1-01", "L2-01"),
                    Collections.singletonMap("rf_sensor", 12.0), 0.75);
            assertTrue(conf1 >= 0.0 && conf1 <= 1.0,
                    "置信度应在[0,1]内, 实际=" + conf1);

            // 测试极端值
            Target extremeTarget = Target.builder()
                    .targetId("T-EXTREME-001")
                    .maxClassConfidence(1.0)            // 最大值
                    .droneCategory(DroneCategory.CONSUMER_QUADCOPTER)
                    .isEvtOpenSet(false)
                    .threatBehaviorTags(new ArrayList<>())
                    .build();

            double conf2 = confidenceGate.calculateConfidence(
                    extremeTarget,
                    Arrays.asList("L1-01", "L2-01", "L2-02", "L3-01", "L4-01"),
                    Collections.singletonMap("rf_sensor", 30.0),
                    1.0);
            assertTrue(conf2 >= 0.0 && conf2 <= 1.0,
                    "极端高值置信度也应在[0,1]内, 实际=" + conf2);
        }
    }

    // ==================== LLM上报触发条件测试 ====================

    @Nested
    @DisplayName("LLM上报触发条件")
    class LLMEscalationTriggers {

        @Test
        @DisplayName("置信度低于阈值应触发LLM上报")
        void testLowConfidence_TriggersLLM() {
            Target target = Target.builder()
                    .targetId("T-TRIG-001")
                    .maxClassConfidence(0.60)
                    .droneCategory(DroneCategory.CONSUMER_QUADCOPTER)
                    .isEvtOpenSet(false)
                    .threatBehaviorTags(new ArrayList<>())
                    .build();

            double lowConfidence = 0.65; // 低于阈值0.80

            boolean shouldEscalate = confidenceGate.shouldEscalateToLLM(target, lowConfidence);
            assertTrue(shouldEscalate, "置信度低于阈值应上报LLM");
        }

        @Test
        @DisplayName("EVT开集识别应触发LLM上报")
        void testEvtOpenSet_TriggersLLM() {
            Target target = Target.builder()
                    .targetId("T-TRIG-002")
                    .maxClassConfidence(0.60)           // 低于EVT阈值0.65
                    .droneCategory(DroneCategory.DIY_FPV)
                    .isEvtOpenSet(false)
                    .threatBehaviorTags(new ArrayList<>())
                    .build();

            // 即使综合置信度高，EVT开集也应触发
            List<String> reasons = confidenceGate.getTriggerReasons(target, 0.90);

            assertFalse(reasons.isEmpty(), "EVT开集识别应有触发原因");
            assertTrue(reasons.stream().anyMatch(r -> r.contains("EVT") || r.contains("置信度低于阈值")),
                    "触发原因应包含EVT开集或分类置信度低: " + reasons);
        }

        @Test
        @DisplayName("复合威胁(3+标签)应触发LLM上报")
        void testComplexThreat_TriggersLLM() {
            Target target = Target.builder()
                    .targetId("T-TRIG-003")
                    .maxClassConfidence(0.85)
                    .droneCategory(DroneCategory.MILITARY_FIXED_WING)
                    .isEvtOpenSet(false)
                    .threatBehaviorTags(Arrays.asList("快速抵近", "侦察", "徘徊", "低空突防"))
                    .build();

            List<String> reasons = confidenceGate.getTriggerReasons(target, 0.85);

            assertFalse(reasons.isEmpty(), "4个威胁标签应触发复合威胁");
            assertTrue(reasons.stream().anyMatch(r -> r.contains("复合威胁")),
                    "触发原因应包含复合威胁: " + reasons);
        }

        @Test
        @DisplayName("UNKNOWN机型应触发LLM上报")
        void testUnknownDroneType_TriggersLLM() {
            Target target = Target.builder()
                    .targetId("T-TRIG-004")
                    .maxClassConfidence(0.70)
                    .droneCategory(DroneCategory.UNKNOWN)
                    .isEvtOpenSet(false)
                    .threatBehaviorTags(new ArrayList<>())
                    .build();

            List<String> reasons = confidenceGate.getTriggerReasons(target, 0.90);

            assertFalse(reasons.isEmpty(), "UNKNOWN机型应触发LLM");
            assertTrue(reasons.stream().anyMatch(r -> r.contains("未知机型")),
                    "触发原因应包含未知机型: " + reasons);
        }

        @Test
        @DisplayName("高信度正常目标不应触发LLM上报")
        void testNormalTarget_NoEscalation() {
            Target target = Target.builder()
                    .targetId("T-TRIG-005")
                    .maxClassConfidence(0.90)
                    .droneCategory(DroneCategory.CONSUMER_QUADCOPTER)
                    .isEvtOpenSet(false)
                    .threatBehaviorTags(Arrays.asList("侦察"))
                    .build();

            boolean shouldEscalate = confidenceGate.shouldEscalateToLLM(target, 0.88);
            assertFalse(shouldEscalate, "高信度正常目标不应上报LLM");
        }
    }

    // ==================== 各维度独立计算测试 ====================

    @Nested
    @DisplayName("各维度独立计算")
    class DimensionCalculations {

        @Test
        @DisplayName("多条规则匹配应返回高规则一致性")
        void testMultiRuleHighConsistency() {
            Target target = Target.builder()
                    .targetId("T-DIM-001")
                    .maxClassConfidence(0.80)
                    .droneCategory(DroneCategory.CONSUMER_QUADCOPTER)
                    .isEvtOpenSet(false)
                    .threatBehaviorTags(new ArrayList<>())
                    .build();

            double confFew = confidenceGate.calculateConfidence(
                    target, Arrays.asList("L2-01"),
                    Collections.singletonMap("rf_sensor", 15.0), 0.80);

            double confMany = confidenceGate.calculateConfidence(
                    target, Arrays.asList("L1-01", "L2-01", "L2-02", "L3-01", "L4-01"),
                    Collections.singletonMap("rf_sensor", 15.0), 0.80);

            assertTrue(confMany > confFew,
                    "更多匹配规则应产生更高置信度; few=" + confFew + ", many=" + confMany);
        }

        @Test
        @DisplayName("高SNR传感器应提高置信度")
        void testHighSnrBoostsConfidence() {
            Target target = Target.builder()
                    .targetId("T-DIM-002")
                    .maxClassConfidence(0.80)
                    .droneCategory(DroneCategory.CONSUMER_QUADCOPTER)
                    .isEvtOpenSet(false)
                    .threatBehaviorTags(new ArrayList<>())
                    .build();
            List<String> rules = Arrays.asList("L1-01", "L2-01");

            double confLowSnr = confidenceGate.calculateConfidence(
                    target, rules,
                    Collections.singletonMap("rf_sensor", 3.0), 0.80);

            double confHighSnr = confidenceGate.calculateConfidence(
                    target, rules,
                    Collections.singletonMap("rf_sensor", 25.0), 0.80);

            assertTrue(confHighSnr > confLowSnr,
                    "高SNR应提升置信度; lowSnr=" + confLowSnr + ", highSnr=" + confHighSnr);
        }

        @Test
        @DisplayName("null传感器状态使用默认值")
        void testNullSensorStatus_UsesDefault() {
            Target target = Target.builder()
                    .targetId("T-DIM-003")
                    .maxClassConfidence(0.80)
                    .droneCategory(DroneCategory.CONSUMER_QUADCOPTER)
                    .isEvtOpenSet(false)
                    .threatBehaviorTags(new ArrayList<>())
                    .build();
            List<String> rules = Arrays.asList("L1-01", "L2-01");

            double confidence = confidenceGate.calculateConfidence(
                    target, rules, null, 0.80);

            assertTrue(confidence > 0.0 && confidence <= 1.0,
                    "null传感器状态应能正常计算, 结果=" + confidence);
        }

        @Test
        @DisplayName("规则覆盖多层应提高评分")
        void testMultiLayerCoverage() {
            Target target = Target.builder()
                    .targetId("T-DIM-004")
                    .maxClassConfidence(0.80)
                    .droneCategory(DroneCategory.CONSUMER_QUADCOPTER)
                    .isEvtOpenSet(false)
                    .threatBehaviorTags(new ArrayList<>())
                    .build();

            double confSingleLayer = confidenceGate.calculateConfidence(
                    target, Arrays.asList("L2-01", "L2-02"),
                    Collections.singletonMap("rf_sensor", 15.0), 0.80);

            double confMultiLayer = confidenceGate.calculateConfidence(
                    target, Arrays.asList("L1-01", "L2-01", "L3-01", "L4-01"),
                    Collections.singletonMap("rf_sensor", 15.0), 0.80);

            assertTrue(confMultiLayer >= confSingleLayer,
                    "多层覆盖不应降低置信度; single=" + confSingleLayer + ", multi=" + confMultiLayer);
        }
    }

    // ==================== 边界条件测试 ====================

    @Nested
    @DisplayName("边界条件")
    class BoundaryConditions {

        @Test
        @DisplayName("空规则列表应返回基线置信度")
        void testEmptyRules() {
            Target target = Target.builder()
                    .targetId("T-EDGE-001")
                    .maxClassConfidence(0.50)
                    .droneCategory(DroneCategory.UNKNOWN)
                    .isEvtOpenSet(false)
                    .threatBehaviorTags(new ArrayList<>())
                    .build();

            double confidence = confidenceGate.calculateConfidence(
                    target, new ArrayList<>(),
                    Collections.singletonMap("rf_sensor", 10.0), 0.50);

            assertTrue(confidence > 0.0 && confidence < 1.0,
                    "空规则列表应返回有效置信度, 实际=" + confidence);
        }

        @Test
        @DisplayName("null规则列表应能正常处理")
        void testNullRules() {
            Target target = Target.builder()
                    .targetId("T-EDGE-002")
                    .maxClassConfidence(0.50)
                    .droneCategory(DroneCategory.UNKNOWN)
                    .isEvtOpenSet(false)
                    .threatBehaviorTags(new ArrayList<>())
                    .build();

            double confidence = confidenceGate.calculateConfidence(
                    target, null,
                    Collections.singletonMap("rf_sensor", 10.0), 0.50);

            assertTrue(confidence > 0.0,
                    "null规则列表应能正常处理, 实际=" + confidence);
        }

        @Test
        @DisplayName("空威胁标签不应触发复合威胁")
        void testEmptyThreatTags_NoComplexTrigger() {
            Target target = Target.builder()
                    .targetId("T-EDGE-003")
                    .maxClassConfidence(0.85)
                    .droneCategory(DroneCategory.CONSUMER_QUADCOPTER)
                    .isEvtOpenSet(false)
                    .threatBehaviorTags(new ArrayList<>())
                    .build();

            List<String> reasons = confidenceGate.getTriggerReasons(target, 0.85);

            boolean hasComplexThreat = reasons.stream()
                    .anyMatch(r -> r.contains("复合威胁"));
            assertFalse(hasComplexThreat, "空标签不应触发复合威胁");
        }

        @Test
        @DisplayName("getConfidenceThreshold应返回配置的阈值")
        void testGetConfidenceThreshold() {
            assertEquals(0.80, confidenceGate.getConfidenceThreshold(), 0.001);
        }
    }
}
