package com.counteruav.service;

import com.counteruav.model.LatLonAlt;
import com.counteruav.model.Target;
import com.counteruav.model.Target.DroneCategory;
import com.counteruav.model.ThreatLevel;
import lombok.Data;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 威胁评估服务 - 基于IFN-TOPSIS的多指标威胁评估
 * <p>
 * 使用直觉模糊数(Intuitionistic Fuzzy Number) TOPSIS方法对目标进行多属性威胁排序。
 * 综合5个评估指标（距离威胁、速度威胁、意图威胁、驻留时间威胁、机型威胁），
 * 通过AHP主观权重、信息熵客观权重和时间熵权重的组合策略，计算每个目标的威胁贴近度系数。
 * </p>
 *
 * <h3>算法流程</h3>
 * <ol>
 *   <li>构建IFN决策矩阵 D = (d_ij)_{n×m}，其中 d_ij = (μ_ij, ν_ij)</li>
 *   <li>计算综合权重：时间熵 + 信息熵 + AHP 线性组合</li>
 *   <li>构建加权IFN决策矩阵</li>
 *   <li>确定正理想解(PIS)和负理想解(NIS)</li>
 *   <li>计算各目标到PIS和NIS的欧氏距离</li>
 *   <li>计算相对贴近度并映射到威胁等级</li>
 * </ol>
 *
 * @author counteruav
 * @since 1.0.0
 */
@Slf4j
@Service
public class ThreatEvaluator {

    /** 5个评估指标名称 */
    private static final String[] INDICATORS = {"距离威胁", "速度威胁", "意图威胁", "驻留时间威胁", "机型威胁"};

    /** 指标数量 */
    private static final int M = INDICATORS.length;

    /**
     * AHP判断矩阵 (5x5) - 基于专家经验的成对比较矩阵
     * <p>
     * 使用Saaty标度（1-9标度法）构建：
     * </p>
     * <pre>
     *           距离    速度    意图    驻留    机型
     *   距离     1       2      1/3     4       5
     *   速度    1/2      1      1/4     3       4
     *   意图     3       4       1      5       6
     *   驻留    1/4    1/3     1/5     1       2
     *   机型    1/5    1/4    1/6    1/2      1
     * </pre>
     * <p>
     * 一致性检验：最大特征值λ_max ≈ 5.19, CI ≈ 0.047, CR ≈ 0.042 (小于0.1，通过一致性检验)
     * </p>
     */
    private static final double[][] AHP_MATRIX = {
            {1.0, 2.0, 1.0 / 3.0, 4.0, 5.0},      // 距离
            {0.5, 1.0, 1.0 / 4.0, 3.0, 4.0},      // 速度
            {3.0, 4.0, 1.0, 5.0, 6.0},             // 意图
            {0.25, 1.0 / 3.0, 0.2, 1.0, 2.0},      // 驻留
            {0.2, 0.25, 1.0 / 6.0, 0.5, 1.0}       // 机型
    };

    /** 综合权重系数：时间熵权重占比 */
    private static final double ALPHA_TIME = 0.25;

    /** 综合权重系数：信息熵权重占比 */
    private static final double BETA_ENTROPY = 0.35;

    /** 综合权重系数：AHP主观权重占比 */
    private static final double GAMMA_AHP = 0.40;

    /** 对数计算常数 */
    private static final double EULER_E = Math.E;

    /**
     * 对目标列表执行IFN-TOPSIS威胁评估
     * <p>
     * 对于空列表或单目标场景，算法仍能正确执行。
     * 空列表返回空Map，单目标返回仅含该目标的评估结果。
     * </p>
     *
     * @param targets       待评估目标列表，不能为null但可以为空
     * @param defenseCenter 防御中心位置（经纬度+高度），用于计算距离威胁
     * @return 按目标ID索引的威胁评分结果Map，保持插入顺序
     */
    public Map<String, ThreatScores> evaluate(List<Target> targets, LatLonAlt defenseCenter) {
        if (targets == null || targets.isEmpty()) {
            log.warn("目标列表为空，跳过威胁评估");
            return new LinkedHashMap<>();
        }

        int n = targets.size();

        // Step 1: 构建IFN决策矩阵 D = (d_ij)_{n×m}
        // d_ij = (μ_ij, ν_ij) where μ is membership, ν is non-membership
        double[][][] ifnMatrix = buildIFNMatrix(targets, defenseCenter);

        // Step 2: 计算综合权重 (时间熵 + 信息熵 + AHP)
        double[][] combinedWeights = calculateCombinedWeights(ifnMatrix, n);

        // Step 3: 构建加权IFN决策矩阵
        double[][][] weightedMatrix = calculateWeightedMatrix(ifnMatrix, combinedWeights, n);

        // Step 4: 确定PIS（正理想解）和NIS（负理想解）
        double[][] pis = new double[M][2]; // (μ+, ν+)
        double[][] nis = new double[M][2]; // (μ-, ν-)
        determineIdealSolutions(weightedMatrix, n, pis, nis);

        // Step 5: 计算每个目标到PIS和NIS的欧氏距离
        double[] dPlus = new double[n];
        double[] dMinus = new double[n];
        calculateDistances(weightedMatrix, pis, nis, n, dPlus, dMinus);

        // Step 6: 计算相对贴近度系数
        double[] closeness = new double[n];
        for (int i = 0; i < n; i++) {
            double denominator = dPlus[i] + dMinus[i];
            if (denominator < 1e-10) {
                // 当正负距离均为零时（极端情况下所有方案与理想解重合），贴近度设为0.5
                closeness[i] = 0.5;
            } else {
                closeness[i] = dMinus[i] / denominator;
            }
        }

        // Step 7: 映射到威胁等级并构建结果
        Map<String, ThreatScores> results = new LinkedHashMap<>();
        for (int i = 0; i < n; i++) {
            Target t = targets.get(i);
            ThreatLevel level = ThreatLevel.fromClosenessCoefficient(closeness[i]);

            ThreatScores scores = new ThreatScores();
            scores.setTargetId(t.getTargetId());
            scores.setClosenessCoefficient(closeness[i]);
            scores.setThreatLevel(level);
            scores.setThreatScore(closeness[i] * 100.0);

            // 计算各指标得分 (使用IFN评分函数 S = μ - ν * π)
            Map<String, Double> indicatorScores = new LinkedHashMap<>();
            for (int j = 0; j < M; j++) {
                double mu = ifnMatrix[i][j][0];
                double nu = ifnMatrix[i][j][1];
                double pi = 1.0 - mu - nu;
                // 评分函数：隶属度减去非隶属度与犹豫度的乘积
                double score = mu - nu * pi;
                indicatorScores.put(INDICATORS[j], Math.max(0.0, Math.min(1.0, score)));
            }
            scores.setIndicatorScores(indicatorScores);
            results.put(t.getTargetId(), scores);
        }

        log.info("IFN-TOPSIS威胁评估完成，评估目标数: {}, 最高威胁等级: {}",
                n, findMaxThreatLevel(results));
        return results;
    }

    // ======================== IFN决策矩阵构建 ========================

    /**
     * 构建IFN决策矩阵
     * <p>
     * 对每个目标的5个评估指标分别计算隶属度μ和非隶属度ν。
     * 隶属度μ表示目标在该指标上"具有威胁"的程度，取值范围[0,1]；
     * 非隶属度ν表示目标在该指标上"不具有威胁"的程度，取值范围[0,1]；
     * 犹豫度π = 1 - μ - ν 表示不确定程度。
     * </p>
     *
     * @param targets       目标列表
     * @param defenseCenter 防御中心位置
     * @return 三维数组 [目标索引][指标索引][0=μ, 1=ν]
     */
    private double[][][] buildIFNMatrix(List<Target> targets, LatLonAlt defenseCenter) {
        int n = targets.size();
        double[][][] matrix = new double[n][M][2];

        for (int i = 0; i < n; i++) {
            Target t = targets.get(i);
            double distance = defenseCenter.distanceTo(t.getPosition());

            // 指标1: 距离威胁
            matrix[i][0] = calcDistanceThreat(distance);
            // 指标2: 速度威胁
            matrix[i][1] = calcSpeedThreat(t.getVelocityMs());
            // 指标3: 意图威胁
            matrix[i][2] = calcIntentThreat(t);
            // 指标4: 驻留时间威胁
            matrix[i][3] = calcDwellThreat(t.getDwellTimeS());
            // 指标5: 机型威胁
            matrix[i][4] = calcDroneTypeThreat(t.getDroneCategory());
        }
        return matrix;
    }

    // ======================== 单一指标威胁计算 ========================

    /**
     * 计算距离威胁指标的IFN值
     * <p>
     * 距离越近威胁越大。使用分段阶梯函数将物理距离映射到直觉模糊数。
     * 距离阈值基于典型反无人机防御圈设定：
     * </p>
     * <ul>
     *   <li>小于500m：核心防御圈，极高威胁</li>
     *   <li>500-1000m：警告圈，高威胁</li>
     *   <li>1000-3000m：警戒圈，中等威胁</li>
     *   <li>3000-5000m：监视圈，较低威胁</li>
     *   <li>5000-10000m：外围圈，低威胁</li>
     *   <li>大于10000m：安全距离，极低威胁</li>
     * </ul>
     *
     * @param distanceM 目标距离防御中心的距离（米）
     * @return 长度为2的数组 [μ, ν]
     */
    private double[] calcDistanceThreat(double distanceM) {
        double mu, nu;
        if (distanceM < 500) {
            mu = 0.95;
            nu = 0.03;
        } else if (distanceM < 1000) {
            mu = 0.85;
            nu = 0.10;
        } else if (distanceM < 3000) {
            mu = 0.60;
            nu = 0.30;
        } else if (distanceM < 5000) {
            mu = 0.35;
            nu = 0.55;
        } else if (distanceM < 10000) {
            mu = 0.15;
            nu = 0.75;
        } else {
            mu = 0.05;
            nu = 0.90;
        }
        return new double[]{mu, nu};
    }

    /**
     * 计算速度威胁指标的IFN值
     * <p>
     * 速度越快威胁越大。典型无人机速度范围：
     * 消费级四旋翼 &lt;20m/s，FPV穿越机 20-50m/s，固定翼 30-100m/s。
     * </p>
     *
     * @param speedMs 目标速度（米/秒）
     * @return 长度为2的数组 [μ, ν]
     */
    private double[] calcSpeedThreat(double speedMs) {
        double mu, nu;
        if (speedMs > 50) {
            mu = 0.95;
            nu = 0.02;
        } else if (speedMs > 30) {
            mu = 0.85;
            nu = 0.10;
        } else if (speedMs > 20) {
            mu = 0.70;
            nu = 0.20;
        } else if (speedMs > 10) {
            mu = 0.40;
            nu = 0.50;
        } else if (speedMs > 3) {
            mu = 0.15;
            nu = 0.75;
        } else {
            mu = 0.05;
            nu = 0.90;
        }
        return new double[]{mu, nu};
    }

    /**
     * 计算意图威胁指标的IFN值
     * <p>
     * 基于目标的威胁行为标签和径向速度综合判断意图威胁程度。
     * 行为标签如"快速抵近"、"攻击"、"侦察"、"徘徊"等提供意图信息；
     * 径向速度反映目标是否在接近防御中心。
     * </p>
     * <p>
     * 基线IFN: (μ=0.3, ν=0.6)，表示中性/低威胁意图。
     * 检测到攻击性标签时显著提高μ；检测到侦察标签时适度提高。
     * </p>
     *
     * @param t 目标对象
     * @return 长度为2的数组 [μ, ν]
     */
    private double[] calcIntentThreat(Target t) {
        double mu = 0.3;
        double nu = 0.6;
        List<String> tags = t.getThreatBehaviorTags();

        if (tags != null) {
            for (String tag : tags) {
                if (tag.contains("快速抵近") || tag.contains("攻击")) {
                    mu = Math.min(1.0, mu + 0.2);
                    nu = Math.max(0.0, nu - 0.15);
                }
                if (tag.contains("侦察") || tag.contains("徘徊")) {
                    mu = Math.min(1.0, mu + 0.1);
                    nu = Math.max(0.0, nu - 0.08);
                }
            }
        }

        // 径向速度大说明目标在快速接近
        if (t.getRadialSpeedMs() > 10) {
            mu = Math.min(1.0, mu + 0.1);
            nu = Math.max(0.0, nu - 0.05);
        }

        // 确保 μ + ν ≤ 1（IFN基本约束）
        if (mu + nu > 1.0) {
            nu = 1.0 - mu;
        }

        return new double[]{mu, nu};
    }

    /**
     * 计算驻留时间威胁指标的IFN值
     * <p>
     * 目标在防御区域上空驻留时间越长，威胁越大。
     * 长期驻留可能表示目标正在进行持续侦察或等待攻击窗口。
     * </p>
     *
     * @param dwellTimeS 驻留时间（秒）
     * @return 长度为2的数组 [μ, ν]
     */
    private double[] calcDwellThreat(int dwellTimeS) {
        double mu, nu;
        if (dwellTimeS > 600) {
            mu = 0.90;
            nu = 0.05;
        } else if (dwellTimeS > 300) {
            mu = 0.75;
            nu = 0.15;
        } else if (dwellTimeS > 120) {
            mu = 0.50;
            nu = 0.40;
        } else if (dwellTimeS > 30) {
            mu = 0.25;
            nu = 0.65;
        } else {
            mu = 0.10;
            nu = 0.85;
        }
        return new double[]{mu, nu};
    }

    /**
     * 计算机型威胁指标的IFN值
     * <p>
     * 不同机型类别对应不同的威胁基线：
     * </p>
     * <ul>
     *   <li>CLUSTER_SWARM (集群/蜂群)：最高威胁，蜂群攻击难以防御</li>
     *   <li>MILITARY_FIXED_WING (军用固定翼)：高威胁，通常携带有效载荷</li>
     *   <li>DIY_FPV (自制FPV)：中等威胁，常用于攻击</li>
     *   <li>CONSUMER_QUADCOPTER (消费级四旋翼)：较低威胁</li>
     *   <li>UNKNOWN (未知)：中等威胁，需进一步判断</li>
     * </ul>
     *
     * @param category 无人机类别枚举
     * @return 长度为2的数组 [μ, ν]
     */
    private double[] calcDroneTypeThreat(DroneCategory category) {
        double mu, nu;
        if (category == null) {
            mu = 0.50;
            nu = 0.40;
        } else {
            switch (category) {
                case CLUSTER_SWARM:
                    mu = 0.95;
                    nu = 0.02;
                    break;
                case MILITARY_FIXED_WING:
                    mu = 0.85;
                    nu = 0.10;
                    break;
                case DIY_FPV:
                    mu = 0.60;
                    nu = 0.30;
                    break;
                case CONSUMER_QUADCOPTER:
                    mu = 0.30;
                    nu = 0.60;
                    break;
                default:
                    mu = 0.50;
                    nu = 0.40;
                    break;
            }
        }
        return new double[]{mu, nu};
    }

    // ======================== 权重计算 ========================

    /**
     * 计算综合权重矩阵
     * <p>
     * 综合权重 = α * W_time + β * W_entropy + γ * W_ahp
     * 其中 α=0.25, β=0.35, γ=0.40
     * </p>
     * <p>
     * W_time: 时间熵权重，越近期的数据点权重越高<br>
     * W_entropy: 信息熵权重，数据离散度越大权重越高<br>
     * W_ahp: AHP主观权重，基于专家经验
     * </p>
     *
     * @param ifnMatrix IFN决策矩阵
     * @param n         目标数量
     * @return 二维数组 [目标索引][指标权重]
     */
    private double[][] calculateCombinedWeights(double[][][] ifnMatrix, int n) {
        // AHP主观权重：通过几何平均法计算判断矩阵的特征向量
        double[] ahpWeights = calculateAHPWeights();

        // 信息熵客观权重：数据自身信息量
        double[] entropyWeights = calculateEntropyWeights(ifnMatrix, n);

        // 时间熵权重：当前版本使用均等权重，后续可扩展为基于时间衰减
        double[] timeWeights = calculateTimeEntropyWeights();

        // 组合权重：对每个目标-指标对计算加权和
        // 当前实现中时间权重和熵权重对所有目标相同，AHP权重对所有指标相同
        double[][] combined = new double[n][M];
        for (int i = 0; i < n; i++) {
            for (int j = 0; j < M; j++) {
                combined[i][j] = ALPHA_TIME * timeWeights[j]
                        + BETA_ENTROPY * entropyWeights[j]
                        + GAMMA_AHP * ahpWeights[j];
            }
        }
        return combined;
    }

    /**
     * 使用几何平均法（方根法）计算AHP权重向量
     * <p>
     * 步骤：
     * </p>
     * <ol>
     *   <li>计算判断矩阵每行元素的几何平均值</li>
     *   <li>将几何平均值归一化得到权重向量</li>
     * </ol>
     * <p>
     * 几何平均法相比特征向量法计算更简单，且在实际应用中结果相近。
     * </p>
     *
     * @return AHP权重数组，长度等于指标数量(5)
     */
    private double[] calculateAHPWeights() {
        int dim = AHP_MATRIX.length;
        double[] weights = new double[dim];

        // 计算每行的几何平均值
        for (int i = 0; i < dim; i++) {
            double product = 1.0;
            for (int j = 0; j < dim; j++) {
                product *= AHP_MATRIX[i][j];
            }
            weights[i] = Math.pow(product, 1.0 / dim);
        }

        // 归一化
        double sum = 0.0;
        for (double w : weights) {
            sum += w;
        }
        for (int i = 0; i < dim; i++) {
            weights[i] /= sum;
        }

        log.debug("AHP权重计算结果: 距离={}, 速度={}, 意图={}, 驻留={}, 机型={}",
                String.format("%.4f", weights[0]), String.format("%.4f", weights[1]),
                String.format("%.4f", weights[2]), String.format("%.4f", weights[3]),
                String.format("%.4f", weights[4]));
        return weights;
    }

    /**
     * 基于信息熵计算客观权重
     * <p>
     * 信息熵反映数据的离散程度。某个指标下各目标得分差异越大，
     * 该指标提供的信息量越多，权重越高。
     * </p>
     * <p>
     * 计算公式：
     * E_j = -k * Σ(p_ij * ln(p_ij))，其中 k = 1/ln(n)
     * w_j = (1 - E_j) / Σ(1 - E_j)
     * </p>
     * <p>
     * 当n=1时（只有1个目标），信息熵无法计算，返回均等权重。
     * </p>
     *
     * @param ifnMatrix IFN决策矩阵
     * @param n         目标数量
     * @return 信息熵权重数组
     */
    private double[] calculateEntropyWeights(double[][][] ifnMatrix, int n) {
        double[] weights = new double[M];

        if (n <= 1) {
            // 只有1个目标时，信息熵无意义，返回均等权重
            for (int j = 0; j < M; j++) {
                weights[j] = 1.0 / M;
            }
            return weights;
        }

        double k = 1.0 / Math.log(n);

        for (int j = 0; j < M; j++) {
            // 将IFN转换为评分值以计算熵
            double[] scores = new double[n];
            double sumScores = 0.0;
            for (int i = 0; i < n; i++) {
                double mu = ifnMatrix[i][j][0];
                double nu = ifnMatrix[i][j][1];
                // 评分函数: S = μ - ν * π = μ - ν * (1 - μ - ν)
                scores[i] = mu - nu * (1.0 - mu - nu);
                if (scores[i] <= 0) {
                    scores[i] = 0.001; // 避免零/负值导致log计算异常
                }
                sumScores += scores[i];
            }

            // 归一化并计算熵
            double entropy = 0.0;
            for (int i = 0; i < n; i++) {
                double p = scores[i] / sumScores;
                if (p > 0) {
                    entropy -= p * Math.log(p);
                }
            }
            entropy *= k;
            // 熵越小 -> 信息量越大 -> 权重越大
            weights[j] = 1.0 - entropy;
        }

        // 归一化
        double sum = 0.0;
        for (double w : weights) {
            sum += w;
        }
        if (sum > 0) {
            for (int i = 0; i < M; i++) {
                weights[i] /= sum;
            }
        } else {
            // 极端情况：所有熵权重为零，使用均等权重
            for (int i = 0; i < M; i++) {
                weights[i] = 1.0 / M;
            }
        }

        return weights;
    }

    /**
     * 计算时间熵权重
     * <p>
     * 当前实现返回均等权重（所有时间点的数据同等重要）。
     * 后续可扩展为基于指数衰减的时间权重：
     * w_time[j] = exp(-λ * Δt_j) / Σ exp(-λ * Δt_k)，
     * 其中λ为衰减系数，Δt为数据时间戳与当前时间的差异。
     * </p>
     *
     * @return 时间熵权重数组
     */
    private double[] calculateTimeEntropyWeights() {
        double[] weights = new double[M];
        for (int i = 0; i < M; i++) {
            weights[i] = 1.0 / M;
        }
        return weights;
    }

    // ======================== 加权与理想解 ========================

    /**
     * 构建加权IFN决策矩阵
     * <p>
     * 使用IFN加权公式对原始决策矩阵进行加权处理：
     * </p>
     * <pre>
     * μ'_ij = 1 - (1 - μ_ij)^w_j
     * ν'_ij = (ν_ij)^w_j
     * </pre>
     * <p>
     * 此公式保证加权后的IFN仍满足 μ' + ν' ≤ 1（直觉模糊集约束）。
     * </p>
     *
     * @param ifnMatrix 原始IFN决策矩阵
     * @param weights   组合权重矩阵
     * @param n         目标数量
     * @return 加权IFN决策矩阵
     */
    private double[][][] calculateWeightedMatrix(double[][][] ifnMatrix, double[][] weights, int n) {
        double[][][] weighted = new double[n][M][2];
        for (int i = 0; i < n; i++) {
            for (int j = 0; j < M; j++) {
                double w = weights[i][j];
                // 加权IFN公式
                weighted[i][j][0] = 1.0 - Math.pow(1.0 - ifnMatrix[i][j][0], w);
                weighted[i][j][1] = Math.pow(ifnMatrix[i][j][1], w);
            }
        }
        return weighted;
    }

    /**
     * 确定正理想解(PIS)和负理想解(NIS)
     * <p>
     * PIS（Positive Ideal Solution）：对每个指标j，取所有目标中μ最大、ν最小的值<br>
     * NIS（Negative Ideal Solution）：对每个指标j，取所有目标中μ最小、ν最大的值<br>
     * </p>
     * <p>
     * 即：PIS = (max_i μ_ij, min_i ν_ij)<br>
     *    NIS = (min_i μ_ij, max_i ν_ij)
     * </p>
     *
     * @param weightedMatrix 加权IFN决策矩阵
     * @param n              目标数量
     * @param pis            输出参数：正理想解数组
     * @param nis            输出参数：负理想解数组
     */
    private void determineIdealSolutions(double[][][] weightedMatrix, int n,
                                         double[][] pis, double[][] nis) {
        for (int j = 0; j < M; j++) {
            // 初始化PIS和NIS
            pis[j][0] = 0.0;
            pis[j][1] = 1.0; // PIS: 初始μ最小, ν最大（实际取反后为正确值）
            nis[j][0] = 1.0;
            nis[j][1] = 0.0; // NIS: 初始μ最大, ν最小

            for (int i = 0; i < n; i++) {
                // PIS: 最大μ, 最小ν
                if (weightedMatrix[i][j][0] > pis[j][0]) {
                    pis[j][0] = weightedMatrix[i][j][0];
                }
                if (weightedMatrix[i][j][1] < pis[j][1]) {
                    pis[j][1] = weightedMatrix[i][j][1];
                }

                // NIS: 最小μ, 最大ν
                if (weightedMatrix[i][j][0] < nis[j][0]) {
                    nis[j][0] = weightedMatrix[i][j][0];
                }
                if (weightedMatrix[i][j][1] > nis[j][1]) {
                    nis[j][1] = weightedMatrix[i][j][1];
                }
            }
        }
    }

    /**
     * 计算每个目标到PIS和NIS的欧氏距离
     * <p>
     * 使用IFN距离公式（包含犹豫度π分量）：
     * </p>
     * <pre>
     * d = sqrt( Σ[(μ_ij - μ*_j)² + (ν_ij - ν*_j)² + (π_ij - π*_j)²] )
     * </pre>
     * <p>
     * 其中 π = 1 - μ - ν 为犹豫度，表示信息的不确定程度。
     * 加入π分量使距离度量更全面，涵盖了模糊集的不确定性信息。
     * </p>
     *
     * @param weightedMatrix 加权IFN决策矩阵
     * @param pis            正理想解
     * @param nis            负理想解
     * @param n              目标数量
     * @param dPlus          输出参数：到PIS的距离数组
     * @param dMinus         输出参数：到NIS的距离数组
     */
    private void calculateDistances(double[][][] weightedMatrix, double[][] pis,
                                    double[][] nis, int n,
                                    double[] dPlus, double[] dMinus) {
        for (int i = 0; i < n; i++) {
            double dp = 0.0;
            double dm = 0.0;
            for (int j = 0; j < M; j++) {
                double mu = weightedMatrix[i][j][0];
                double nu = weightedMatrix[i][j][1];
                double pi = 1.0 - mu - nu;

                double muP = pis[j][0];
                double nuP = pis[j][1];
                double piP = 1.0 - muP - nuP;

                double muN = nis[j][0];
                double nuN = nis[j][1];
                double piN = 1.0 - muN - nuN;

                // 欧氏距离平方和（包含μ、ν、π三维分量）
                dp += (mu - muP) * (mu - muP)
                        + (nu - nuP) * (nu - nuP)
                        + (pi - piP) * (pi - piP);
                dm += (mu - muN) * (mu - muN)
                        + (nu - nuN) * (nu - nuN)
                        + (pi - piN) * (pi - piN);
            }
            dPlus[i] = Math.sqrt(dp);
            dMinus[i] = Math.sqrt(dm);
        }
    }

    // ======================== 辅助方法 ========================

    /**
     * 查找评估结果中的最高威胁等级描述
     *
     * @param results 评估结果Map
     * @return 最高威胁等级的中文标签，若无结果返回"无"
     */
    private String findMaxThreatLevel(Map<String, ThreatScores> results) {
        if (results.isEmpty()) {
            return "无";
        }
        ThreatScores maxScore = null;
        for (ThreatScores s : results.values()) {
            if (maxScore == null || s.getThreatScore() > maxScore.getThreatScore()) {
                maxScore = s;
            }
        }
        return maxScore != null && maxScore.getThreatLevel() != null
                ? maxScore.getThreatLevel().getLabel() : "未知";
    }

    // ======================== 内部类 ========================

    /**
     * IFN-TOPSIS威胁评分结果
     * <p>
     * 封装单个目标的完整威胁评估结果，包括贴近度系数、威胁等级、
     * 威胁评分以及各指标的分项得分。
     * </p>
     */
    @Data
    public static class ThreatScores {

        /** 目标唯一标识 */
        private String targetId;

        /** 相对贴近度系数 (0.0-1.0)，越大表示威胁越高 */
        private double closenessCoefficient;

        /** 威胁等级枚举 */
        private ThreatLevel threatLevel;

        /** 威胁评分 (0-100)，由贴近度系数×100得到 */
        private double threatScore;

        /** 各评估指标的分项得分 Map，key为指标名称，value为IFN评分 */
        private Map<String, Double> indicatorScores;
    }
}
