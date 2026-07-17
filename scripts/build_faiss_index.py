#!/usr/bin/env python3
"""
FAISS 索引构建命令行工具

支持按实体类型单独重建或全部重建 FAISS 索引。
可重用 init_knowledge_base.py 中的嵌入逻辑。
通过 --force 强制覆盖已有索引，否则默认跳过。
使用 tqdm 显示进度（可选依赖）。

依赖：sentence-transformers, faiss-cpu, numpy, tqdm（可选）
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

# ---------------------------------------------------------------------------
# 日志配置
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("build_faiss_index")

# ---------------------------------------------------------------------------
# 可选依赖：tqdm 进度条
# ---------------------------------------------------------------------------
try:
    from tqdm import tqdm as _tqdm

    _TQDM_AVAILABLE = True
except ImportError:
    _TQDM_AVAILABLE = False


def _get_progress_bar(iterable=None, **kwargs):
    """获取进度条，若未安装 tqdm 则返回原可迭代对象。"""
    if _TQDM_AVAILABLE and iterable is not None:
        return _tqdm(iterable, **kwargs)
    return iterable


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _get_script_dir() -> Path:
    """获取当前脚本所在目录的绝对路径。"""
    return Path(__file__).resolve().parent


def _resolve_path(base: Path, path_str: str) -> Path:
    """将相对路径解析为绝对路径（相对于 base 或脚本目录）。"""
    p = Path(path_str)
    if p.is_absolute():
        return p
    candidate = base / p
    if candidate.exists():
        return candidate
    candidate2 = _get_script_dir() / p
    if candidate2.exists():
        return candidate2
    return candidate


def _check_cuda_available() -> bool:
    """检查 CUDA 是否可用。"""
    try:
        import torch
        return torch.cuda.is_available()
    except ImportError:
        return False


def _resolve_device(device_arg: str) -> str:
    """解析设备参数。"""
    if device_arg == "auto":
        return "cuda" if _check_cuda_available() else "cpu"
    if device_arg == "cuda":
        if _check_cuda_available():
            return "cuda"
        logger.warning("CUDA 不可用，回退到 CPU 模式")
        return "cpu"
    return "cpu"


# ---------------------------------------------------------------------------
# 嵌入与索引构建逻辑（与 init_knowledge_base.py 保持一致）
# ---------------------------------------------------------------------------

# 文本构建函数

def _build_drone_text(drone: Dict) -> str:
    """将无人机各字段拼接为用于嵌入的文本。"""
    parts: List[str] = []
    name = drone.get("name", "")
    if name:
        parts.append(f"名称: {name}")
    name_cn = drone.get("name_cn", drone.get("nameCn", ""))
    if name_cn:
        parts.append(f"中文名: {name_cn}")
    category = drone.get("category", "")
    if category:
        parts.append(f"类别: {category}")
    rf = drone.get("rf_signature", drone.get("rfSignature", {}))
    if isinstance(rf, dict):
        rf_parts = []
        freq = rf.get("frequency_mhz", rf.get("frequencyMhz"))
        if freq is not None:
            rf_parts.append(f"频率: {freq}MHz")
        bw = rf.get("bandwidth_mhz", rf.get("bandwidthMhz"))
        if bw is not None:
            rf_parts.append(f"带宽: {bw}MHz")
        mod = rf.get("modulation_type", rf.get("modulationType", ""))
        if mod:
            rf_parts.append(f"调制: {mod}")
        proto = rf.get("protocol", "")
        if proto:
            rf_parts.append(f"协议: {proto}")
        if rf_parts:
            parts.append("RF特征: " + "，".join(rf_parts))
    mission = drone.get("typical_mission", drone.get("typicalMission", ""))
    if mission:
        parts.append(f"典型任务: {mission}")
    notes = drone.get("notes", "")
    if notes:
        parts.append(f"备注: {notes}")
    manufacturer = drone.get("manufacturer", "")
    if manufacturer:
        parts.append(f"制造商: {manufacturer}")
    return "；".join(parts)


def _build_scenario_text(scenario: Dict) -> str:
    """将场景模板各字段拼接为用于嵌入的文本。"""
    parts: List[str] = []
    sid = scenario.get("scenario_id", scenario.get("id", ""))
    if sid:
        parts.append(f"场景ID: {sid}")
    name = scenario.get("name", "")
    if name:
        parts.append(f"名称: {name}")
    desc = scenario.get("description", "")
    if desc:
        parts.append(f"描述: {desc}")
    inp = scenario.get("input", {})
    if isinstance(inp, dict):
        mode = inp.get("mode", "")
        if mode:
            parts.append(f"模式: {mode}")
        env = inp.get("environment", {})
        if isinstance(env, dict):
            terrain = env.get("terrain_type", env.get("terrainType", ""))
            if terrain:
                parts.append(f"地形: {terrain}")
            weather = env.get("weather", "")
            if weather:
                parts.append(f"天气: {weather}")
    expected = scenario.get("expected_output", scenario.get("expected", {}))
    if isinstance(expected, dict):
        trigger = expected.get("trigger_reason_contains", "")
        if trigger:
            parts.append(f"触发原因: {trigger}")
    return "；".join(parts)


def _build_frequency_band_text(band: Dict) -> str:
    """将频段各字段拼接为用于嵌入的文本。"""
    parts: List[str] = []
    bid = band.get("band_id", band.get("id", ""))
    if bid:
        parts.append(f"频段ID: {bid}")
    name = band.get("name", "")
    if name:
        parts.append(f"名称: {name}")
    freq_range = band.get("frequency_range", band.get("frequencyRange", ""))
    if freq_range:
        parts.append(f"频率范围: {freq_range}")
    usage = band.get("usage", band.get("common_usage", band.get("commonUsage", "")))
    if usage:
        parts.append(f"用途: {usage}")
    modulation = band.get("modulation", band.get("typical_modulation", band.get("typicalModulation", "")))
    if modulation:
        parts.append(f"典型调制: {modulation}")
    notes = band.get("notes", "")
    if notes:
        parts.append(f"备注: {notes}")
    return "；".join(parts)


# 实体类型配置
_ENTITY_CONFIG = {
    "drone": {
        "json_file": "drone_types.json",
        "list_key": "drones",
        "id_field": "drone_id",
        "text_builder": _build_drone_text,
        "index_file": "drone_types.index",
        "meta_file": "drone_metadata.json",
        "label": "无人机类型",
    },
    "scenario": {
        "json_file": "scenario_templates.json",
        "list_key": "templates",
        "id_field": "scenario_id",
        "text_builder": _build_scenario_text,
        "index_file": "scenario_templates.index",
        "meta_file": "scenario_metadata.json",
        "label": "场景模板",
    },
    "frequency_band": {
        "json_file": "frequency_bands.json",
        "list_key": "bands",
        "id_field": "band_id",
        "text_builder": _build_frequency_band_text,
        "index_file": "frequency_bands.index",
        "meta_file": "frequency_bands_metadata.json",
        "label": "频段数据",
    },
}


# ---------------------------------------------------------------------------
# 索引构建器
# ---------------------------------------------------------------------------

class FAISSIndexBuilder:
    """单个实体类型的 FAISS 索引构建器。"""

    def __init__(self, model, batch_size: int = 32):
        self.model = model
        self.batch_size = batch_size

    def load_json_data(self, filepath: Path, list_key: str) -> Optional[List[Dict]]:
        """加载 JSON 数据文件。"""
        if not filepath.exists():
            logger.error("文件不存在: %s", filepath)
            return None
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            logger.error("JSON 解析失败 (%s): %s", filepath, e)
            return None
        except Exception as e:
            logger.error("读取文件失败 (%s): %s", filepath, e)
            return None

        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            # 尝试多种常见的列表键名
            for key in [list_key, "items", "data", "records"]:
                val = data.get(key)
                if isinstance(val, list):
                    return val
            # 最后尝试 values 中的第一个列表
            for val in data.values():
                if isinstance(val, list):
                    return val
        logger.error("%s 格式不正确，期望 list 或含列表的 dict", filepath)
        return None

    def build(
        self,
        items: List[Dict],
        text_builder,
        id_field: str,
        label: str,
    ) -> Tuple[Any, np.ndarray, List[str], int]:
        """生成文本嵌入并构建 FAISS 索引。

        Returns:
            (faiss_index, embeddings, metadata_ids, dimension)
        """
        if not items:
            logger.warning("%s 数据为空，跳过索引构建", label)
            return None, np.array([]), [], 0

        # 构建文本
        texts = []
        ids = []
        for item in items:
            text = text_builder(item)
            if not text.strip():
                continue
            texts.append(text)
            item_id = item.get(id_field, f"unknown_{len(ids)}")
            ids.append(str(item_id))

        if not texts:
            logger.error("%s: 无有效文本数据，无法构建索引", label)
            return None, np.array([]), [], 0

        logger.info("%s: 共 %d 条数据待编码", label, len(texts))

        # 编码（使用 tqdm 进度条如果可用）
        t0 = time.perf_counter()
        show_progress = _TQDM_AVAILABLE
        embeddings = self.model.encode(
            texts,
            batch_size=self.batch_size,
            show_progress_bar=show_progress,
            normalize_embeddings=True,
        )
        encode_time = time.perf_counter() - t0
        logger.info("%s: 编码完成，耗时 %.2f 秒，嵌入维度 %d", label, encode_time, embeddings.shape[1])

        embeddings = np.asarray(embeddings, dtype=np.float32)

        # 构建 FAISS 索引
        import faiss
        dim = embeddings.shape[1]
        index = faiss.IndexFlatIP(dim)
        index.add(embeddings)

        logger.info("%s: FAISS 索引构建完成，共 %d 条向量", label, index.ntotal)
        return index, embeddings, ids, dim

    @staticmethod
    def save_index(index, filepath: Path) -> bool:
        """保存 FAISS 索引。"""
        import faiss
        filepath.parent.mkdir(parents=True, exist_ok=True)
        try:
            faiss.write_index(index, str(filepath))
            file_size_kb = filepath.stat().st_size / 1024
            logger.info("FAISS 索引已保存: %s (%.1f KB)", filepath, file_size_kb)
            return True
        except Exception as e:
            logger.error("保存索引失败 (%s): %s", filepath, e)
            return False

    @staticmethod
    def save_metadata(ids: List[str], filepath: Path) -> bool:
        """保存元数据映射。"""
        filepath.parent.mkdir(parents=True, exist_ok=True)
        metadata = {str(i): item_id for i, item_id in enumerate(ids)}
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)
            file_size_kb = filepath.stat().st_size / 1024
            logger.info("元数据已保存: %s (%.1f KB)", filepath, file_size_kb)
            return True
        except Exception as e:
            logger.error("保存元数据失败 (%s): %s", filepath, e)
            return False


# ---------------------------------------------------------------------------
# 统计报告
# ---------------------------------------------------------------------------

def _print_index_report(
    label: str,
    index,
    embeddings: np.ndarray,
    ids: List[str],
    index_path: Path,
    elapsed: float,
):
    """打印单个索引的统计报告。"""
    total = index.ntotal if index else 0
    dim = embeddings.shape[1] if embeddings.size else 0
    file_size = index_path.stat().st_size / 1024 if index_path.exists() else 0

    print(f"\n  [{label}]")
    print(f"    向量数量:    {total}")
    print(f"    向量维度:    {dim}")
    print(f"    元数据条目:  {len(ids)}")
    print(f"    索引文件:    {index_path}")
    print(f"    文件大小:    {file_size:.1f} KB")
    print(f"    构建耗时:    {elapsed:.2f} 秒")


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def _load_model(model_name: str, device: str):
    """加载 sentence-transformers 模型。"""
    logger.info("正在加载嵌入模型: %s（设备: %s）", model_name, device)
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(model_name, device=device)
    dim = model.get_sentence_embedding_dimension()
    logger.info("模型加载完成，嵌入维度: %d", dim)
    return model


def _build_one_entity(
    builder: FAISSIndexBuilder,
    entity_key: str,
    config: dict,
    data_dir: Path,
    output_dir: Path,
    force: bool,
) -> bool:
    """构建单个实体类型的索引。"""
    label = config["label"]
    json_path = data_dir / config["json_file"]
    index_path = output_dir / config["index_file"]
    meta_path = output_dir / config["meta_file"]

    # 检查是否已存在，非强制模式则跳过
    if index_path.exists() and meta_path.exists() and not force:
        logger.info("[%s] 索引已存在，跳过构建（使用 --force 可强制覆盖）", label)
        # 仍输出已有索引的报告
        try:
            import faiss
            existing = faiss.read_index(str(index_path))
            print(f"\n  [{label}] (已有索引)")
            print(f"    向量数量:    {existing.ntotal}")
            print(f"    向量维度:    {existing.d}")
            file_size = index_path.stat().st_size / 1024
            print(f"    文件大小:    {file_size:.1f} KB")
            return True
        except Exception as e:
            logger.warning("读取已有索引失败: %s", e)
            # 继续构建

    # 验证 JSON 文件存在
    if not json_path.exists():
        logger.error("[%s] JSON 文件不存在: %s", label, json_path)
        return False

    # 加载数据
    t0 = time.perf_counter()
    items = builder.load_json_data(json_path, config["list_key"])
    if items is None:
        return False
    logger.info("[%s] 共加载 %d 条数据", label, len(items))

    # 构建索引
    index, embeddings, ids, dim = builder.build(
        items,
        config["text_builder"],
        config["id_field"],
        label,
    )
    if index is None:
        return False

    # 保存
    ok1 = builder.save_index(index, index_path)
    ok2 = builder.save_metadata(ids, meta_path)
    if not ok1 or not ok2:
        return False

    elapsed = time.perf_counter() - t0
    _print_index_report(label, index, embeddings, ids, index_path, elapsed)
    return True


def main() -> None:
    """主函数：根据命令行参数构建指定的 FAISS 索引。"""
    parser = argparse.ArgumentParser(
        description="FAISS 索引构建工具：为知识库数据生成向量索引",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python build_faiss_index.py
  python build_faiss_index.py --entity-type drone --force
  python build_faiss_index.py --entity-type all --model-name BAAI/bge-large-zh --device cpu
        """,
    )

    default_parent = _get_script_dir().parent
    default_data_dir = default_parent / "knowledge-base"
    default_output_dir = default_data_dir / "faiss_index"

    parser.add_argument(
        "--entity-type",
        type=str,
        default="all",
        choices=["drone", "scenario", "frequency_band", "all"],
        help="要构建索引的实体类型 (默认: all)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="强制覆盖已有索引（默认：存在则跳过）",
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default=str(default_data_dir),
        help="知识库 JSON 文件所在目录 (默认: %(default)s)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(default_output_dir),
        help="FAISS 索引输出目录 (默认: data-dir/faiss_index)",
    )
    parser.add_argument(
        "--model-name",
        type=str,
        default="BAAI/bge-small-zh",
        help="sentence-transformers 模型名称 (默认: %(default)s)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=32,
        help="编码时的批处理大小 (默认: %(default)s)",
    )
    parser.add_argument(
        "--device",
        type=str,
        default="auto",
        choices=["auto", "cpu", "cuda"],
        help="计算设备 (默认: auto)",
    )

    args = parser.parse_args()

    # 解析路径
    data_dir = Path(args.data_dir)
    if not data_dir.is_absolute():
        data_dir = _get_script_dir().parent / data_dir

    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = data_dir / output_dir

    output_dir.mkdir(parents=True, exist_ok=True)

    device = _resolve_device(args.device)

    logger.info("实体类型: %s", args.entity_type)
    logger.info("强制覆盖: %s", args.force)
    logger.info("数据目录: %s", data_dir)
    logger.info("输出目录: %s", output_dir)
    logger.info("模型名称: %s", args.model_name)
    logger.info("计算设备: %s", device)

    # 确定要构建的实体类型
    if args.entity_type == "all":
        entity_keys = list(_ENTITY_CONFIG.keys())
    else:
        entity_keys = [args.entity_type]

    # 加载模型（一次性加载，所有实体共享）
    model = _load_model(args.model_name, device)
    builder = FAISSIndexBuilder(model, batch_size=args.batch_size)

    all_ok = True
    for key in entity_keys:
        config = _ENTITY_CONFIG[key]
        print(f"\n{'=' * 60}")
        print(f"  构建: {config['label']} ({key})")
        print(f"{'=' * 60}")
        ok = _build_one_entity(builder, key, config, data_dir, output_dir, args.force)
        if not ok:
            all_ok = False

    print(f"\n{'=' * 60}")
    print(f"  构建完成: {'全部成功' if all_ok else '存在失败项（请查看日志）'}")
    print(f"{'=' * 60}")

    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
