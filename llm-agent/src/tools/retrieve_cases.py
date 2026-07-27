"""
相似案例检索工具 (Tool 7)
从历史成功案例库中检索与当前态势最相似的案例（动态 Few-shot）。

双轨制：
- 冷启动阶段 (<50 个 APPROVED 案例): 回退到静态 Few-shot 示例
- 热启动后: FAISS 向量检索动态 Top-3
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# FAISS 索引路径
_CASES_INDEX_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "kb_index"

# 静态 Few-shot 回退文件
_STATIC_EXAMPLES_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "prompt_templates" / "few_shot_examples.json"
)

# 历史案例数据路径
_CASES_DATA_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "kb_json" / "cases.json"


def _load_faiss_index() -> Optional[Any]:
    """加载案例 FAISS 索引。"""
    try:
        import faiss
        index_path = _CASES_INDEX_DIR / "cases.index"
        if not index_path.exists():
            logger.info(f"案例 FAISS 索引不存在: {index_path}，回退到静态示例")
            return None
        index = faiss.read_index(str(index_path))
        logger.info(f"案例 FAISS 索引加载成功: ntotal={index.ntotal}")
        return index
    except ImportError:
        logger.warning("faiss-cpu 未安装，回退到静态示例")
        return None
    except Exception as e:
        logger.warning(f"案例 FAISS 索引加载失败: {e}")
        return None


def _load_cases_data() -> Optional[list[dict]]:
    """加载历史案例 JSON 数据。"""
    if not _CASES_DATA_PATH.exists():
        logger.info(f"历史案例数据不存在: {_CASES_DATA_PATH}")
        return None
    try:
        with open(_CASES_DATA_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            data = data.get("items", data.get("data", []))
        logger.info(f"历史案例数据加载成功: {len(data)} 条")
        return data
    except Exception as e:
        logger.warning(f"历史案例数据加载失败: {e}")
        return None


def _load_static_examples() -> list[dict]:
    """加载静态 Few-shot 示例（冷启动回退）。"""
    if not _STATIC_EXAMPLES_PATH.exists():
        logger.warning(f"静态 Few-shot 示例文件不存在: {_STATIC_EXAMPLES_PATH}")
        return _get_builtin_examples()

    try:
        with open(_STATIC_EXAMPLES_PATH, "r", encoding="utf-8") as f:
            examples = json.load(f)
        if not isinstance(examples, list):
            return _get_builtin_examples()
        logger.info(f"加载静态 Few-shot 示例: {len(examples)} 条")
        return examples
    except Exception as e:
        logger.warning(f"静态 Few-shot 示例加载失败: {e}")
        return _get_builtin_examples()


def _keyword_score(text: str, query: str) -> int:
    """简单关键词匹配打分（双向子串匹配）。"""
    score = 0
    query_lower = query.lower()
    text_lower = text.lower()

    # 检查 query 是否是 text 的子串（或反过来）
    if query_lower in text_lower or text_lower in query_lower:
        score += 3

    # 分词匹配：从 query 中提取词，检查是否在 text 中
    for word in query_lower.split():
        if len(word) >= 2 and word in text_lower:
            score += 2

    # 从 text 中提取词，检查是否在 query 中
    for word in text_lower.split():
        if len(word) >= 2 and word in query_lower:
            score += 1

    return score


def _convert_static_to_case(example: dict, similarity: float) -> dict:
    """将静态 Few-shot 示例转换为案例格式。"""
    title = example.get("title", example.get("scenario", ""))
    sit_summary = example.get("situation_summary", "")
    expected = example.get("expected_output", {})
    ta = expected.get("threat_assessment", {})
    ra = expected.get("recommended_action", {})
    remarks = expected.get("remarks", "")

    return {
        "case_id": f"static-{example.get('id', '?')}",
        "title": title,
        "similarity": round(similarity, 4),
        "scenario": sit_summary,
        "decision_summary": (
            f"威胁等级 {ta.get('threat_level', '?')}，"
            f"置信度 {ta.get('confidence', '?')}，"
            f"动作: {ra.get('action_type', '?')}"
        ),
        "commander_verdict": "APPROVED",
        "outcome": ra.get("expected_effect", remarks[:80] if remarks else ""),
        "key_lessons": remarks[:120] if remarks else title,
        "_source": "static_few_shot",
    }


def _faiss_search(query: str, top_k: int) -> Optional[list[dict]]:
    """使用 FAISS 进行语义检索。"""
    index = _load_faiss_index()
    data = _load_cases_data()

    if index is None or data is None:
        return None

    try:
        from sentence_transformers import SentenceTransformer
        # 使用已有的 embedding 模型
        model = SentenceTransformer("BAAI/bge-small-zh")
        query_embedding = model.encode([query], normalize_embeddings=True)
        import numpy as np
        query_vector = np.array(query_embedding, dtype=np.float32)

        distances, indices = index.search(query_vector, min(top_k, len(data)))

        results = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx < 0 or idx >= len(data):
                continue
            similarity = 1.0 - float(dist) / 2.0
            similarity = max(0.0, min(1.0, similarity))
            item = data[idx]
            results.append({
                "case_id": item.get("case_id", item.get("id", f"case-{idx}")),
                "similarity": round(similarity, 4),
                "scenario": item.get("scenario", item.get("situation_summary", "")),
                "decision_summary": item.get("decision_summary", ""),
                "commander_verdict": item.get("commander_verdict", item.get("verdict", "APPROVED")),
                "outcome": item.get("outcome", ""),
                "key_lessons": item.get("key_lessons", item.get("remarks", "")),
                "_source": "faiss_retrieval",
            })

        if results:
            logger.info(f"FAISS 案例检索成功: 返回 {len(results)} 条")
            return results
    except Exception as e:
        logger.warning(f"FAISS 案例检索异常: {e}")

    return None


def _keyword_search(query: str, top_k: int) -> list[dict]:
    """使用关键词从静态示例中检索（回退方案）。"""
    static_examples = _load_static_examples()

    scored = []
    for ex in static_examples:
        title = ex.get("title", "")
        sit = ex.get("situation_summary", "")
        task = ex.get("task", "")
        text = f"{title} {sit} {task}"

        score = _keyword_score(text, query)
        if score > 0:
            scored.append((score, ex))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:top_k]

    max_score = top[0][0] if top else 1
    results = []
    for rank, (score, ex) in enumerate(top):
        similarity = score / max_score if max_score > 0 else 0.3
        results.append(_convert_static_to_case(ex, similarity))

    logger.info(f"关键词案例检索: 返回 {len(results)} 条 (top_k={top_k})")
    return results


def retrieve_cases(args: dict) -> dict:
    """检索与当前态势最相似的历史案例（动态 Few-shot）。

    Args:
        args: 参数字典，包含:
            - situation_desc (str): 当前态势描述（必需）
            - top_k (int, 可选): 返回案例数，默认 3

    Returns:
        {
            "success": bool,
            "data": [
                {
                    "case_id": str, "similarity": float,
                    "scenario": str, "decision_summary": str,
                    "commander_verdict": str, "outcome": str,
                    "key_lessons": str,
                }, ...
            ],
            "error": str,
        }
    """
    situation_desc = args.get("situation_desc", args.get("query", ""))
    top_k = int(args.get("top_k", 3))
    top_k = max(1, min(10, top_k))

    if not situation_desc:
        return {"success": False, "data": None, "error": "参数 'situation_desc' 不能为空"}

    # 优先使用 FAISS 检索
    faiss_results = _faiss_search(situation_desc, top_k)
    if faiss_results:
        return {"success": True, "data": faiss_results, "error": ""}

    # 回退到关键词检索（静态 Few-shot 示例）
    keyword_results = _keyword_search(situation_desc, top_k)
    return {"success": True, "data": keyword_results, "error": ""}


def _get_builtin_examples() -> list[dict]:
    """内置的冷启动示例（所有文件加载失败时的最终回退）。"""
    return [
        {
            "id": 1,
            "title": "未知无人机高速接近 → 威胁5 + 全频段压制",
            "situation_summary": "未知型号无人机以35m/s高速接近核心区域，CPA预计120s",
            "task": "评估目标威胁并生成处置建议",
            "expected_output": {
                "threat_assessment": {"threat_level": 5, "confidence": 0.85},
                "recommended_action": {"action_type": "全频段压制", "priority": 1},
            },
        },
        {
            "id": 2,
            "title": "消费级DJI + 中等距离 → 威胁3 + 选择性干扰",
            "situation_summary": "DJI Mavic 3消费级无人机，距离3.2km，工业区悬停",
            "task": "评估目标威胁",
            "expected_output": {
                "threat_assessment": {"threat_level": 3, "confidence": 0.90},
                "recommended_action": {"action_type": "选择性干扰", "priority": 2},
            },
        },
        {
            "id": 3,
            "title": "蜂群攻击 → 威胁5 + 全频段+微波",
            "situation_summary": "7架无人机扇形编队推进，多频段跳频",
            "task": "评估蜂群威胁",
            "expected_output": {
                "threat_assessment": {"threat_level": 5, "confidence": 0.92},
                "recommended_action": {"action_type": "全频段压制", "priority": 1},
            },
        },
        {
            "id": 4,
            "title": "平民区上空目标 → 软杀伤优先",
            "situation_summary": "改装工业无人机在市区广场上方悬停，下方人流密集",
            "task": "评估威胁并考虑平民安全",
            "expected_output": {
                "threat_assessment": {"threat_level": 4, "confidence": 0.72},
                "recommended_action": {"action_type": "导航诱骗", "priority": 1},
            },
            "remarks": "严禁在此场景使用硬杀伤手段",
        },
        {
            "id": 5,
            "title": "FPV竞速 + 关键区域 → 威胁4 + 5.8GHz干扰",
            "situation_summary": "高速小型目标RCS极小，FPV竞速特征，接近弹药库",
            "task": "评估FPV对关键设施威胁",
            "expected_output": {
                "threat_assessment": {"threat_level": 4, "confidence": 0.87},
                "recommended_action": {"action_type": "选择性干扰", "priority": 1},
            },
        },
        {
            "id": 6,
            "title": "传感器低信噪比 → 保守估计",
            "situation_summary": "雷达回波SNR仅3dB，目标信息碎片化，无法确认型号",
            "task": "在传感器质量差时评估威胁",
            "expected_output": {
                "threat_assessment": {"threat_level": 4, "confidence": 0.35},
                "recommended_action": {"action_type": "全频段压制", "priority": 2},
            },
        },
    ]
