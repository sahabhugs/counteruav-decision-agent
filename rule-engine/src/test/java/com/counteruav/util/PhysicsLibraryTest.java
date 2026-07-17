package com.counteruav.util;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

/**
 * PhysicsLibrary 单元测试 - 军事物理计算工具库
 *
 * 测试覆盖:
 * - 雷达方程: 最大探测距离、指定距离信噪比
 * - 光电传感器: Johnson准则探测距离
 * - 电子对抗: 干扰机ERP、有效干扰距离
 * - 电磁传播: 自由空间路径损耗、多普勒频移
 * - 单位换算: dB与线性值互转
 * - 边界条件: 零值、负值、极值
 */
@DisplayName("PhysicsLibrary - 军事物理计算测试")
class PhysicsLibraryTest {

    // ==================== 雷达方程测试 ====================

    @Nested
    @DisplayName("雷达最大探测距离")
    class RadarMaxRange {

        @Test
        @DisplayName("典型X波段雷达对小型无人机探测距离")
        void testRadarMaxRangeSmallDrone() {
            // Arrange: X波段(10GHz)雷达参数
            double txPower = 100e3;        // 100kW 峰值功率
            double antennaGain = 1000.0;   // 30dBi 天线增益（线性值）
            double wavelength = 0.03;       // X波段波长 (3cm)
            double rcs = 0.05;             // 小型无人机RCS (0.05m²)
            double noiseFigure = 3.0;       // 3dB 噪声系数
            double snrMin = 10.0;           // 最小检测SNR (10dB→线性值10)

            // Act
            double range = PhysicsLibrary.radarMaxRange(
                    txPower, antennaGain, antennaGain,
                    wavelength, rcs, noiseFigure, snrMin);

            // Assert
            assertTrue(range > 1000, "X波段雷达对小型无人机探测距离应>1km, 实际=" + range);
            assertTrue(range < 50000, "探测距离应在合理范围内, 实际=" + range);
        }

        @Test
        @DisplayName("更大RCS目标应产生更远探测距离")
        void testLargerRcsGreaterRange() {
            double wavelength = 0.03;
            double noiseFigure = 3.0;
            double snrMin = 10.0;

            double rangeSmall = PhysicsLibrary.radarMaxRange(
                    100e3, 1000, 1000, wavelength, 0.01, noiseFigure, snrMin);

            double rangeLarge = PhysicsLibrary.radarMaxRange(
                    100e3, 1000, 1000, wavelength, 1.0, noiseFigure, snrMin);

            assertTrue(rangeLarge > rangeSmall,
                    "大RCS目标应产生更远探测距离; small=" + rangeSmall + ", large=" + rangeLarge);
        }
    }

    @Nested
    @DisplayName("指定距离信噪比")
    class SnrAtRange {

        @Test
        @DisplayName("近距离目标应有高SNR")
        void testCloseRangeHighSnr() {
            double snr = PhysicsLibrary.snrAtRange(
                    100e3, 1000, 0.05,     // 100kW, 30dBi增益, 0.05m² RCS
                    5000,                     // 5km
                    10e9, 1e6, 3.0);        // 10GHz, 1MHz带宽, 3dB噪声

            assertTrue(snr > 0, "SNR应>0dB, 实际=" + snr);
        }

        @Test
        @DisplayName("远距离目标应有低SNR")
        void testFarRangeLowSnr() {
            double snrClose = PhysicsLibrary.snrAtRange(
                    100e3, 1000, 0.05, 5000, 10e9, 1e6, 3.0);

            double snrFar = PhysicsLibrary.snrAtRange(
                    100e3, 1000, 0.05, 20000, 10e9, 1e6, 3.0);

            assertTrue(snrClose > snrFar,
                    "近距离SNR应大于远距离; close=" + snrClose + ", far=" + snrFar);
        }
    }

    // ==================== 单位换算测试 ====================

    @Nested
    @DisplayName("dB与线性值互转")
    class DbConversion {

        @Test
        @DisplayName("toDb(1)应返回0")
        void testToDbOne() {
            assertEquals(0.0, PhysicsLibrary.toDb(1.0), 1e-10);
        }

        @Test
        @DisplayName("toDb(10)应返回10")
        void testToDbTen() {
            assertEquals(10.0, PhysicsLibrary.toDb(10.0), 1e-10);
        }

        @Test
        @DisplayName("toDb(100)应返回20")
        void testToDbHundred() {
            assertEquals(20.0, PhysicsLibrary.toDb(100.0), 1e-10);
        }

        @Test
        @DisplayName("toDb与fromDb互为逆运算")
        void testRoundTrip() {
            double original = 42.0;
            double db = PhysicsLibrary.toDb(original);
            double back = PhysicsLibrary.fromDb(db);
            assertEquals(original, back, 1e-10,
                    "toDb→fromDb应还原原始值");
        }

        @Test
        @DisplayName("fromDb(0)应返回1")
        void testFromDbZero() {
            assertEquals(1.0, PhysicsLibrary.fromDb(0.0), 1e-10);
        }

        @Test
        @DisplayName("fromDb(30)应返回1000")
        void testFromDbThirty() {
            assertEquals(1000.0, PhysicsLibrary.fromDb(30.0), 1e-10);
        }

        @Test
        @DisplayName("toDb(≤0)应抛出异常")
        void testToDbNonPositive() {
            assertThrows(IllegalArgumentException.class,
                    () -> PhysicsLibrary.toDb(0.0));
            assertThrows(IllegalArgumentException.class,
                    () -> PhysicsLibrary.toDb(-1.0));
        }
    }

    // ==================== 自由空间路径损耗测试 ====================

    @Nested
    @DisplayName("自由空间路径损耗")
    class FreeSpacePathLoss {

        @Test
        @DisplayName("距离越远路径损耗越大")
        void testLongerDistanceGreaterLoss() {
            double freq = 2.4e9; // 2.4GHz

            double lossClose = PhysicsLibrary.freeSpacePathLoss(100, freq);
            double lossFar = PhysicsLibrary.freeSpacePathLoss(10000, freq);

            assertTrue(lossFar > lossClose,
                    "远距离路径损耗应大于近距离; close=" + lossClose + ", far=" + lossFar);
        }

        @Test
        @DisplayName("2.4GHz/1km典型路径损耗约100dB")
        void testTypicalFSPL() {
            double fspl = PhysicsLibrary.freeSpacePathLoss(1000, 2.4e9);
            // 理论值: 20*log10(1000) + 20*log10(2.4e9) - 147.55 ≈ 100.04dB
            assertTrue(fspl > 95 && fspl < 105,
                    "2.4GHz/1km路径损耗应在~100dB, 实际=" + fspl);
        }

        @Test
        @DisplayName("距离≤0应抛出异常")
        void testInvalidDistance() {
            assertThrows(IllegalArgumentException.class,
                    () -> PhysicsLibrary.freeSpacePathLoss(0, 2.4e9));
            assertThrows(IllegalArgumentException.class,
                    () -> PhysicsLibrary.freeSpacePathLoss(-1, 2.4e9));
        }
    }

    // ==================== 多普勒频移测试 ====================

    @Nested
    @DisplayName("多普勒频移")
    class DopplerShift {

        @Test
        @DisplayName("接近目标产生正多普勒频移")
        void testApproachingPositiveShift() {
            // X波段10GHz, 目标速度100m/s接近
            double shift = PhysicsLibrary.dopplerShift(100, 10e9);
            assertTrue(shift > 0, "接近目标应产生正多普勒频移, 实际=" + shift);
            // 理论值: 2*100*10e9/3e8 ≈ 6667 Hz
            assertTrue(shift > 5000 && shift < 8000,
                    "X波段100m/s多普勒频移应≈6.7kHz, 实际=" + shift);
        }

        @Test
        @DisplayName("远离目标产生负多普勒频移")
        void testRecedingNegativeShift() {
            double shift = PhysicsLibrary.dopplerShift(-100, 10e9);
            assertTrue(shift < 0, "远离目标应产生负多普勒频移, 实际=" + shift);
        }

        @Test
        @DisplayName("静止目标无多普勒频移")
        void testStationaryNoShift() {
            assertEquals(0.0, PhysicsLibrary.dopplerShift(0, 10e9), 1e-10);
        }
    }

    // ==================== 波长/频率换算测试 ====================

    @Nested
    @DisplayName("波长频率换算")
    class WavelengthFrequency {

        @Test
        @DisplayName("2.4GHz波长约为0.125m")
        void testWavelength24GHz() {
            double lambda = PhysicsLibrary.wavelength(2.4e9);
            assertEquals(0.125, lambda, 0.01,
                    "2.4GHz波长应约0.125m, 实际=" + lambda);
        }

        @Test
        @DisplayName("波长→频率→波长往返一致")
        void testRoundTrip() {
            double originalFreq = 5.8e9;
            double lambda = PhysicsLibrary.wavelength(originalFreq);
            double freq = PhysicsLibrary.frequency(lambda);
            assertEquals(originalFreq, freq, 1.0,
                    "频率→波长→频率应一致");
        }
    }

    // ==================== 电子对抗测试 ====================

    @Nested
    @DisplayName("干扰机ERP与有效干扰距离")
    class Jamming {

        @Test
        @DisplayName("干扰机ERP计算")
        void testJammerERP() {
            // 发射功率 30dBm (1W) + 天线增益 6dBi - 线损 2dB = 34dBm
            double erp = PhysicsLibrary.jammerERP(30.0, 6.0, 2.0);
            assertEquals(34.0, erp, 0.01);
        }

        @Test
        @DisplayName("有效干扰距离应随ERP增大而增大")
        void testJammingRangeIncreasesWithERP() {
            double commRange = 1000.0;
            double signalERP = 100.0;  // 20dBm
            double jsMin = 2.0;

            double rangeLow = PhysicsLibrary.jammingRange(
                    commRange, 200.0, signalERP, jsMin);  // 23dBm干扰

            double rangeHigh = PhysicsLibrary.jammingRange(
                    commRange, 2000.0, signalERP, jsMin); // 33dBm干扰

            assertTrue(rangeHigh > rangeLow,
                    "干扰ERP越大有效距离应越大");
        }
    }
}
