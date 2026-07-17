"""
知识库查询工具
使用 sentence-transformers 嵌入和 FAISS 索引进行语义搜索，
支持按实体类型（无人机/场景/地形/电磁环境）分类查询。
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

import numpy as np

try:
    from ..config import config
except (ImportError, ValueError):
    from config import config  # type: ignore[no-redef]

logger = logging.getLogger(__name__)

# 懒加载嵌入模型
_embedding_model = None

_KB_INDEX_DIR = Path(config.KB_INDEX_DIR)
_KB_JSON_DIR = Path(config.KB_JSON_DIR)


def _get_embedding_model():
    """懒加载嵌入模型（单例）。"""
    global _embedding_model
    if _embedding_model is None:
        try:
            from sentence_transformers import SentenceTransformer
            model_path = config.EMBEDDING_MODEL
            if os.path.exists(model_path):
                _embedding_model = SentenceTransformer(model_path)
            else:
                # 尝试从 HuggingFace 或本地默认路径加载
                logger.info(f"模型路径 {model_path} 不存在，尝试使用默认 bge-small-zh 模型")
                _embedding_model = SentenceTransformer("BAAI/bge-small-zh")
            logger.info("嵌入模型加载成功")
        except Exception as e:
            logger.error(f"嵌入模型加载失败: {e}")
            raise
    return _embedding_model


def _load_faiss_index(entity_type: str) -> Optional[Any]:
    """加载指定实体类型的 FAISS 索引。

    Args:
        entity_type: 实体类型（drone/scenario/terrain/em_environment）

    Returns:
        FAISS 索引对象或 None。
    """
    try:
        import faiss

        index_path = _KB_INDEX_DIR / f"{entity_type}.index"
        if not index_path.exists():
            logger.warning(f"FAISS 索引文件不存在: {index_path}")
            return None

        index = faiss.read_index(str(index_path))
        logger.info(f"FAISS 索引加载成功: {entity_type} (向量数: {index.ntotal})")
        return index

    except ImportError:
        logger.warning("faiss-cpu 未安装，无法使用 FAISS 索引")
        return None
    except Exception as e:
        logger.error(f"FAISS 索引加载失败 ({entity_type}): {e}")
        return None


def _load_json_data(entity_type: str) -> Optional[list[dict]]:
    """加载指定实体类型的 JSON 数据文件。

    Args:
        entity_type: 实体类型。

    Returns:
        数据列表或 None。
    """
    json_path = _KB_JSON_DIR / f"{entity_type}.json"
    if not json_path.exists():
        logger.warning(f"JSON 数据文件不存在: {json_path}")
        return None

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            data = data.get("items", data.get("data", []))
        logger.info(f"JSON 数据加载成功: {entity_type} ({len(data)} 条)")
        return data
    except Exception as e:
        logger.error(f"JSON 数据加载失败 ({entity_type}): {e}")
        return None


def _format_drone_result(item: dict, similarity: float) -> dict:
    """格式化无人机查询结果。"""
    return {
        "type": "drone",
        "model": item.get("model", item.get("name", "未知")),
        "manufacturer": item.get("manufacturer", ""),
        "category": item.get("category", item.get("type", "")),
        "specifications": {
            "max_speed_ms": item.get("max_speed_ms", ""),
            "max_altitude_m": item.get("max_altitude_m", ""),
            "endurance_min": item.get("endurance_min", ""),
            "weight_kg": item.get("weight_kg", ""),
            "frequency_bands": item.get("frequency_bands", item.get("freq_bands", [])),
            "gnss_support": item.get("gnss_support", []),
            "payload_capability": item.get("payload_capability", ""),
            "detection_difficulty": item.get("detection_difficulty", ""),
        },
        "threat_profile": item.get("threat_profile", item.get("threat_level", "")),
        "known_countermeasures": item.get("known_countermeasures", item.get("countermeasures", [])),
        "similarity": round(similarity, 4),
    }


def _format_scenario_result(item: dict, similarity: float) -> dict:
    """格式化场景模板查询结果。"""
    return {
        "type": "scenario",
        "name": item.get("name", item.get("title", "")),
        "description": item.get("description", ""),
        "typical_threats": item.get("typical_threats", []),
        "recommended_strategies": item.get("recommended_strategies", item.get("strategies", [])),
        "roi_constraints": item.get("roi_constraints", {}),
        "similar_cases": item.get("similar_cases", []),
        "similarity": round(similarity, 4),
    }


def _format_terrain_result(item: dict, similarity: float) -> dict:
    """格式化地形查询结果。"""
    return {
        "type": "terrain",
        "name": item.get("name", ""),
        "terrain_class": item.get("terrain_class", item.get("class", "")),
        "rf_propagation": item.get("rf_propagation", {}),
        "visibility_map": item.get("visibility_map", {}),
        "deployment_constraints": item.get("deployment_constraints", []),
        "similarity": round(similarity, 4),
    }


def _format_em_result(item: dict, similarity: float) -> dict:
    """格式化电磁环境查询结果。"""
    return {
        "type": "em_environment",
        "name": item.get("name", ""),
        "ambient_noise_level": item.get("ambient_noise_level", ""),
        "interference_sources": item.get("interference_sources", []),
        "available_bands": item.get("available_bands", []),
        "regulated_bands": item.get("regulated_bands", []),
        "similarity": round(similarity, 4),
    }


_FORMATTERS = {
    "drone": _format_drone_result,
    "scenario": _format_scenario_result,
    "terrain": _format_terrain_result,
    "em_environment": _format_em_result,
}


def query_kb(args: dict) -> dict:
    """查询知识库。

    Args:
        args: 参数字典，包含:
            - entity_type (str): 实体类型，可选: drone/scenario/terrain/em_environment
            - query (str): 查询文本
            - top_k (int, 可选): 返回结果数，默认 5

    Returns:
        查询结果字典。
    """
    entity_type = args.get("entity_type", "drone")
    query_text = args.get("query", "")
    top_k = args.get("top_k", 5)

    if entity_type not in _FORMATTERS:
        return {
            "success": False,
            "data": None,
            "error": f"不支持的实体类型: {entity_type}，可选: {list(_FORMATTERS.keys())}",
        }

    if not query_text:
        return {"success": False, "data": None, "error": "查询文本 'query' 不能为空"}

    # 优先使用 FAISS 索引
    faiss_index = _load_faiss_index(entity_type)
    json_data = _load_json_data(entity_type)

    if faiss_index is not None and json_data is not None:
        try:
            results = _search_faiss(entity_type, query_text, top_k, faiss_index, json_data)
            return results
        except Exception as e:
            logger.warning(f"FAISS 搜索失败，切至 JSON 搜索: {e}")

    # 回退到 JSON 文件搜索
    if json_data is not None:
        try:
            results = _search_json(entity_type, query_text, top_k, json_data)
            return results
        except Exception as e:
            logger.error(f"JSON 搜索失败: {e}")

    return {
        "success": False,
        "data": None,
        "error": f"知识库查询失败: 实体类型 {entity_type} 的索引和数据均不可用",
    }


def _search_faiss(
    entity_type: str,
    query: str,
    top_k: int,
    index: Any,
    data: list[dict],
) -> dict:
    """使用 FAISS 索引进行语义搜索。

    Args:
        entity_type: 实体类型。
        query: 查询文本。
        top_k: 返回结果数。
        index: FAISS 索引对象。
        data: 原始 JSON 数据。

    Returns:
        搜索结果字典。
    """
    model = _get_embedding_model()
    query_embedding = model.encode([query], normalize_embeddings=True)
    query_vector = np.array(query_embedding, dtype=np.float32)

    distances, indices = index.search(query_vector, min(top_k, len(data)))

    results: list[dict] = []
    formatter = _FORMATTERS.get(entity_type)

    for dist, idx in zip(distances[0], indices[0]):
        if idx < 0 or idx >= len(data):
            continue
        similarity = 1.0 - float(dist) / 2.0  # L2 距离转相似度
        similarity = max(0.0, min(1.0, similarity))

        item = data[idx]
        if formatter:
            formatted = formatter(item, similarity)
        else:
            formatted = {**item, "similarity": round(similarity, 4)}
        results.append(formatted)

    logger.info(f"FAISS 知识库查询成功: {entity_type}, 返回 {len(results)} 条")
    return {"success": True, "data": results, "error": ""}


def _search_json(
    entity_type: str,
    query: str,
    top_k: int,
    data: list[dict],
) -> dict:
    """使用简单的关键词匹配进行 JSON 数据搜索（回退方案）。

    Args:
        entity_type: 实体类型。
        query: 查询文本。
        top_k: 返回结果数。
        data: 原始 JSON 数据。

    Returns:
        搜索结果字典。
    """
    query_lower = query.lower()
    scored: list[tuple[int, dict]] = []

    for item in data:
        # 将所有文本字段拼接进行匹配
        text = json.dumps(item, ensure_ascii=False).lower()
        score = 0
        if query_lower in text:
            score += 2
        # 分词匹配
        for word in query_lower.split():
            if word in text:
                score += 1

        if score > 0:
            scored.append((score, item))

    scored.sort(key=lambda x: x[0], reverse=True)
    top_items = scored[:top_k]

    formatter = _FORMATTERS.get(entity_type)
    results: list[dict] = []
    for rank, (score, item) in enumerate(top_items):
        # 归一化相似度
        max_score = top_items[0][0] if top_items else 1
        similarity = score / max_score if max_score > 0 else 0.0

        if formatter:
            formatted = formatter(item, similarity)
        else:
            formatted = {**item, "similarity": round(similarity, 4)}
        results.append(formatted)

    logger.info(f"JSON 知识库查询成功: {entity_type}, 返回 {len(results)} 条")
    return {"success": True, "data": results, "error": ""}
