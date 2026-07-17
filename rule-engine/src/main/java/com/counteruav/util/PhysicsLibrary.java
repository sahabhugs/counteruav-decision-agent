package com.counteruav.util;

/**
 * 物理计算工具库
 * <p>
 * 提供雷达探测、光电传感、电子对抗等军事物理计算功能。
 * 所有方法均为静态方法，采用标准物理公式实现，适用于反无人机系统的实时计算。
 * </p>
 *
 * <h3>主要功能模块</h3>
 * <ul>
 *   <li>雷达方程 - 最大探测距离、指定距离信噪比</li>
 *   <li>光电传感器 - Johnson准则探测距离</li>
 *   <li>电子对抗 - 干扰机ERP、有效干扰距离</li>
 *   <li>电磁传播 - 自由空间路径损耗、多普勒频移</li>
 *   <li>单位换算 - dB与线性值互转</li>
 * </ul>
 *
 * @author counteruav
 * @since 1.0.0
 */
public final class PhysicsLibrary {

    /** 光速 (m/s) */
    public static final double SPEED_OF_LIGHT = 3.0e8;

    /** 玻尔兹曼常数 (J/K) */
    public static final double BOLTZMANN_CONSTANT = 1.38e-23;

    /** 标准噪声温度 (K)，ITU-R推荐值 */
    public static final double STANDARD_NOISE_TEMPERATURE = 290.0;

    /** 圆周率 */
    public static final double PI = Math.PI;

    /** (4π)³ 预计算常量，用于雷达方程 */
    private static final double FOUR_PI_CUBED = Math.pow(4.0 * PI, 3.0);

    /** 圆周率平方 预计算常量 */
    private static final double PI_SQUARED = PI * PI;

    private PhysicsLibrary() {
        throw new UnsupportedOperationException("工具类不允许实例化");
    }

    // ======================== 雷达探测 ========================

    /**
     * 计算雷达最大探测距离（雷达方程）。
     * <p>
     * 使用标准雷达距离方程：
     * </p>
     * <pre>
     * R_max = (Pt * Gt * Gr * λ² * σ / ((4π)³ * k * T₀ * B * F * SNR_min))^(1/4)
     * </pre>
     * <p>
     * 其中：
     * <ul>
     *   <li>Pt  - 发射功率 (W)</li>
     *   <li>Gt  - 发射天线增益（线性值，非dB）</li>
     *   <li>Gr  - 接收天线增益（线性值，非dB）</li>
     *   <li>λ   - 波长 (m)，通过 λ = c / f 计算</li>
     *   <li>σ   - 雷达截面积 RCS (m²)</li>
     *   <li>k   - 玻尔兹曼常数 1.38e-23 J/K</li>
     *   <li>T₀  - 标准噪声温度 290 K</li>
     *   <li>B   - 接收机带宽 1 MHz</li>
     *   <li>F   - 接收机噪声系数（线性值）</li>
     *   <li>SNR_min - 最小可检测信噪比（线性值）</li>
     * </ul>
     *
     * @param pt          发射功率 (W)，典型值 1e3 ~ 1e6
     * @param gt          发射天线增益（线性值），典型值 100 ~ 10000
     * @param gr          接收天线增益（线性值），典型值 100 ~ 10000
     * @param wavelength  波长 (m)，通过 光速/频率 计算，典型值 0.03m (X波段)
     * @param rcs         雷达截面积 (m²)，小型无人机典型值 0.01 ~ 0.1
     * @param noiseFigure 接收机噪声系数 (dB)，典型值 2 ~ 10
     * @param snrMin      最小可检测信噪比（线性值），典型值 10 (约10dB)
     * @return 最大探测距离 (m)
     */
    public static double radarMaxRange(double pt, double gt, double gr, double wavelength,
                                        double rcs, double noiseFigure, double snrMin) {
        double bandwidth = 1.0e6; // 标准接收机带宽 1 MHz
        double f = fromDb(noiseFigure); // 噪声系数线性值

        double numerator = pt * gt * gr * wavelength * wavelength * rcs;
        double denominator = FOUR_PI_CUBED * BOLTZMANN_CONSTANT
                * STANDARD_NOISE_TEMPERATURE * bandwidth * f * snrMin;

        if (denominator <= 0) {
            throw new IllegalArgumentException("雷达方程分母无效，请检查输入参数是否合法");
        }

        return Math.pow(numerator / denominator, 0.25);
    }

    /**
     * 计算指定距离处的信噪比 SNR。
     * <p>
     * 使用雷达信噪比方程：
     * </p>
     * <pre>
     * SNR = Pt * Gt * Gr * λ² * σ / ((4π)³ * R⁴ * k * T₀ * B * F)
     * </pre>
     * <p>
     * 返回值以 dB 为单位。此公式可用于评估雷达对特定距离目标的探测能力。
     * 对于单基地雷达，假设 Gt = Gr = G（收发共用天线），则公式简化为：
     * </p>
     * <pre>
     * SNR = Pt * G² * λ² * σ / ((4π)³ * R⁴ * k * T₀ * B * F)
     * </pre>
     *
     * @param txPower      发射功率 (W)
     * @param antennaGain  天线增益（线性值，收发共用时）
     * @param rcs          雷达截面积 (m²)
     * @param range        目标距离 (m)
     * @param frequency    雷达工作频率 (Hz)，典型值 1e9 ~ 1e10 (X波段)
     * @param bandwidth    接收机带宽 (Hz)，典型值 1e6
     * @param noiseFigure  接收机噪声系数 (dB)，典型值 2 ~ 10
     * @return 信噪比 (dB)
     */
    public static double snrAtRange(double txPower, double antennaGain, double rcs,
                                     double range, double frequency, double bandwidth,
                                     double noiseFigure) {
        double wavelength = SPEED_OF_LIGHT / frequency;
        double f = fromDb(noiseFigure);
        double r4 = Math.pow(range, 4.0);

        double numerator = txPower * antennaGain * antennaGain
                * wavelength * wavelength * rcs;
        double denominator = FOUR_PI_CUBED * r4 * BOLTZMANN_CONSTANT
                * STANDARD_NOISE_TEMPERATURE * bandwidth * f;

        if (denominator <= 0) {
            throw new IllegalArgumentException("SNR计算分母无效，请检查输入参数是否合法");
        }

        double snrLinear = numerator / denominator;
        return toDb(snrLinear);
    }

    // ======================== 光电传感器 ========================

    /**
     * 计算光电（可见光/红外）传感器对目标的探测/识别/辨认距离。
     * <p>
     * 使用 Johnson 准则计算：
     * </p>
     * <pre>
     * R = H * N_pixels / (2 * N_required * tan(FOV / 2))
     * </pre>
     * <p>
     * 其中：
     * <ul>
     *   <li>H          - 目标在传感器方向的尺寸 (m)，通常用目标高度</li>
     *   <li>N_pixels   - 传感器单方向像素数（如1920）</li>
     *   <li>N_required - Johnson准则所需线对数/像素数：</li>
     *   <ul>
     *     <li>检测(Detection)  ≈ 1 线对 = 2 像素</li>
     *     <li>识别(Recognition) ≈ 4 线对 = 8 像素</li>
     *     <li>辨认(Identification) ≈ 8 线对 = 16 像素</li>
     *   </ul>
     *   <li>FOV       - 传感器视场角 (度)，单方向</li>
     * </ul>
     * <h4>Johnson准则说明</h4>
     * <table border="1">
     *   <tr><th>任务等级</th><th>所需线对数</th><th>等效像素数(50%概率)</th></tr>
     *   <tr><td>检测</td><td>1.0 ± 0.25</td><td>2</td></tr>
     *   <tr><td>识别</td><td>4.0 ± 0.8</td><td>8</td></tr>
     *   <tr><td>辨认</td><td>8.0 ± 1.6</td><td>16</td></tr>
     * </table>
     *
     * @param targetHeight   目标在传感器方向的尺寸 (m)，通常为目标高度
     * @param requiredPixels Johnson准则所需像素数，识别=8，辨认=16
     * @param fovDegrees     传感器视场角 (度)，单方向
     * @param sensorPixels   传感器单方向像素数（如1920用于水平方向）
     * @return 探测/识别/辨认距离 (m)
     */
    public static double electroOpticalRange(double targetHeight, double requiredPixels,
                                              double fovDegrees, double sensorPixels) {
        if (requiredPixels <= 0) {
            throw new IllegalArgumentException("所需像素数必须大于0");
        }
        if (fovDegrees <= 0 || fovDegrees >= 180) {
            throw new IllegalArgumentException("视场角必须在(0, 180)度范围内");
        }

        double fovRadians = Math.toRadians(fovDegrees);
        double halfFov = fovRadians / 2.0;
        double tanHalfFov = Math.tan(halfFov);

        if (tanHalfFov <= 0) {
            throw new IllegalArgumentException("视场角正切值无效");
        }

        return targetHeight * sensorPixels / (2.0 * requiredPixels * tanHalfFov);
    }

    // ======================== 电子对抗（干扰） ========================

    /**
     * 计算干扰机等效辐射功率 ERP（Effective Radiated Power）。
     * <p>
     * ERP 是衡量干扰机实际辐射能力的关键指标，计算公式：
     * </p>
     * <pre>
     * ERP(dBm) = TxPower(dBm) + AntennaGain(dBi) - CableLoss(dB)
     * </pre>
     * <p>
     * 所有参数均以 dB 为单位直接相加/减。这是对数域的标准链路预算计算。
     * </p>
     *
     * @param txPower     发射机输出功率 (dBm)
     * @param antennaGain 天线增益 (dBi)，全向天线为 0 dBi
     * @param cableLoss   馈线损耗 (dB)，正值表示损耗
     * @return 等效辐射功率 ERP (dBm)
     */
    public static double jammerERP(double txPower, double antennaGain, double cableLoss) {
        return txPower + antennaGain - cableLoss;
    }

    /**
     * 计算干扰机有效干扰距离。
     * <p>
     * 基于干扰-信号比的自由空间传播模型：
     * </p>
     * <pre>
     * R_j = R_c * sqrt(ERP_j / ERP_s / JSR_min)
     * </pre>
     * <p>
     * 其中：
     * <ul>
     *   <li>R_j     - 有效干扰距离 (m)，即在此距离内干扰可成功压制通信</li>
     *   <li>R_c     - 通信链路距离 (m)，目标与通信接收机之间的距离</li>
     *   <li>ERP_j   - 干扰机等效辐射功率（线性值，mW），通过 fromDb(ERP_dBm) 转换</li>
     *   <li>ERP_s   - 信号发射机等效辐射功率（线性值，mW）</li>
     *   <li>JSR_min - 最小干信比（线性值），即使干扰生效所需的最小J/S比</li>
     * </ul>
     * <p>
     * 注意：所有ERP参数传入时均为线性值（mW），如需从dBm转换请先调用 {@link #fromDb(double)}。
     * </p>
     *
     * @param commRange   通信链路距离 (m)，即接收机与信号发射源的距离
     * @param jammerERP   干扰机ERP（线性值，mW），使用 {@link #fromDb(double)} 从dBm转换
     * @param signalERP   信号发射机ERP（线性值，mW），使用 {@link #fromDb(double)} 从dBm转换
     * @param jsRatioMin  最小干信比 J/S（线性值），典型值 2 ~ 10
     * @return 有效干扰距离 (m)
     */
    public static double jammingRange(double commRange, double jammerERP, double signalERP,
                                       double jsRatioMin) {
        if (signalERP <= 0 || jsRatioMin <= 0) {
            throw new IllegalArgumentException("信号ERP和最小干信比必须大于0");
        }

        double ratio = jammerERP / (signalERP * jsRatioMin);
        return commRange * Math.sqrt(ratio);
    }

    // ======================== 电磁传播 ========================

    /**
     * 计算自由空间路径损耗 FSPL（Free Space Path Loss）。
     * <p>
     * 标准 Friis 传输方程的路径损耗形式：
     * </p>
     * <pre>
     * FSPL(dB) = 20 * log10(d) + 20 * log10(f) + 20 * log10(4π / c)
     * </pre>
     * <p>
     * 其中：
     * <ul>
     *   <li>d - 传播距离 (m)</li>
     *   <li>f - 信号频率 (Hz)</li>
     *   <li>c - 光速 3.0×10⁸ m/s</li>
     * </ul>
     * <p>
     * 等价形式（简化计算）：
     * </p>
     * <pre>
     * FSPL(dB) = 20 * log10(d) + 20 * log10(f) - 147.55
     * </pre>
     * <p>
     * 其中 -147.55 = 20 * log10(4π / c)，适用于 d 以 m 为单位、f 以 Hz 为单位。
     * </p>
     *
     * @param distance  传播距离 (m)
     * @param frequency 信号频率 (Hz)
     * @return 自由空间路径损耗 (dB)，始终为正数
     */
    public static double freeSpacePathLoss(double distance, double frequency) {
        if (distance <= 0) {
            throw new IllegalArgumentException("距离必须大于0");
        }
        if (frequency <= 0) {
            throw new IllegalArgumentException("频率必须大于0");
        }

        // FSPL = 20*log10(d) + 20*log10(f) + 20*log10(4π/c)
        double constantTerm = 20.0 * Math.log10(4.0 * PI / SPEED_OF_LIGHT);
        double distanceTerm = 20.0 * Math.log10(distance);
        double frequencyTerm = 20.0 * Math.log10(frequency);

        return distanceTerm + frequencyTerm + constantTerm;
    }

    /**
     * 计算多普勒频移。
     * <p>
     * 当雷达与目标之间存在相对径向运动时，反射信号的频率会发生偏移：
     * </p>
     * <pre>
     * f_d = 2 * v_r * f / c
     * </pre>
     * <p>
     * 其中：
     * <ul>
     *   <li>v_r - 径向相对速度 (m/s)，正值表示目标靠近雷达（频率升高）</li>
     *   <li>f   - 雷达载波频率 (Hz)</li>
     *   <li>c   - 光速 3.0×10⁸ m/s</li>
     * </ul>
     * <p>
     * 因子 2 是因为雷达信号经历了发射和接收两次多普勒效应（往返路径）。
     * 此公式适用于单基地雷达（收发同址）。
     * </p>
     * <p>
     * <b>典型值参考：</b><br>
     * X波段(10GHz)雷达，目标速度100m/s → f_d ≈ 6.67 kHz<br>
     * Ku波段(16GHz)雷达，目标速度50m/s  → f_d ≈ 5.33 kHz
     * </p>
     *
     * @param relativeVelocity 径向相对速度 (m/s)，正值表示目标接近雷达
     * @param frequency        雷达载波频率 (Hz)
     * @return 多普勒频移 (Hz)，正值表示频率升高
     */
    public static double dopplerShift(double relativeVelocity, double frequency) {
        return 2.0 * relativeVelocity * frequency / SPEED_OF_LIGHT;
    }

    // ======================== 单位换算 ========================

    /**
     * 线性值转换为分贝值 (dB)。
     * <p>
     * 转换公式：
     * </p>
     * <pre>
     * dB = 10 * log10(linear)
     * </pre>
     * <p>
     * 适用于功率类物理量（SNR、ERP、噪声系数等）。
     * 注意：对于电压/场强类物理量，应使用 20 * log10()。
     * </p>
     *
     * @param linear 线性值，必须大于0
     * @return 分贝值 (dB)
     * @throws IllegalArgumentException 如果 linear &lt;= 0
     */
    public static double toDb(double linear) {
        if (linear <= 0) {
            throw new IllegalArgumentException("线性值必须大于0才能转换为dB，当前值: " + linear);
        }
        return 10.0 * Math.log10(linear);
    }

    /**
     * 分贝值 (dB) 转换为线性值。
     * <p>
     * 转换公式：
     * </p>
     * <pre>
     * linear = 10^(dB / 10)
     * </pre>
     * <p>
     * 适用于功率类物理量（SNR、ERP、噪声系数等）。
     * 注意：对于电压/场强类物理量，应使用 10^(dB / 20)。
     * </p>
     *
     * @param db 分贝值 (dB)
     * @return 线性值
     */
    public static double fromDb(double db) {
        return Math.pow(10.0, db / 10.0);
    }

    // ======================== 便捷工具方法 ========================

    /**
     * 根据频率计算波长。
     * <pre>
     * λ = c / f
     * </pre>
     *
     * @param frequency 频率 (Hz)
     * @return 波长 (m)
     */
    public static double wavelength(double frequency) {
        if (frequency <= 0) {
            throw new IllegalArgumentException("频率必须大于0");
        }
        return SPEED_OF_LIGHT / frequency;
    }

    /**
     * 根据波长计算频率。
     * <pre>
     * f = c / λ
     * </pre>
     *
     * @param wavelength 波长 (m)
     * @return 频率 (Hz)
     */
    public static double frequency(double wavelength) {
        if (wavelength <= 0) {
            throw new IllegalArgumentException("波长必须大于0");
        }
        return SPEED_OF_LIGHT / wavelength;
    }
}
