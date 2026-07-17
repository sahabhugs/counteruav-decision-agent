#!/usr/bin/env python3
"""
知识库初始化脚本

功能：
1. 加载 drone_types.json、scenario_templates.json、frequency_bands.json
2. 使用 sentence-transformers 生成文本嵌入向量
3. 构建 FAISS 索引（IndexFlatIP，归一化后等价于余弦相似度）
4. 保存索引文件和元数据映射到 knowledge-base/faiss_index/
5. 输出汇总统计信息

依赖：sentence-transformers, faiss-cpu (或 faiss-gpu), numpy
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
logger = logging.getLogger("init_knowledge_base")


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _get_script_dir() -> Path:
    """获取当前脚本所在目录的绝对路径。"""
    return Path(__file__).resolve().parent


def _resolve_path(base: Path, path_str: str) -> Path:
    """将相对路径解析为绝对路径（相对于 base 或当前工作目录）。"""
    p = Path(path_str)
    if p.is_absolute():
        return p
    # 先尝试相对于 base 解析
    candidate = base / p
    if candidate.exists():
        return candidate
    # 回退到相对于脚本目录
    candidate2 = _get_script_dir() / p
    if candidate2.exists():
        return candidate2
    # 都不存在则返回相对于 base 的路径（后续代码会处理不存在的情况）
    return candidate


def _check_cuda_available() -> bool:
    """检查 CUDA 是否可用。"""
    try:
        import torch
        return torch.cuda.is_available()
    except ImportError:
        return False


def _resolve_device(device_arg: str) -> str:
    """解析设备参数：auto -> 自动检测，cpu -> 强制 CPU，cuda -> 强制 GPU（不可用时回退 CPU）。"""
    if device_arg == "auto":
        return "cuda" if _check_cuda_available() else "cpu"
    if device_arg == "cuda":
        if _check_cuda_available():
            return "cuda"
        logger.warning("CUDA 不可用，回退到 CPU 模式")
        return "cpu"
    return "cpu"


# ---------------------------------------------------------------------------
# 核心类
# ---------------------------------------------------------------------------

class KnowledgeBaseInitializer:
    """知识库初始化器，负责生成和保存 FAISS 索引。"""

    def __init__(
        self,
        data_dir: Path,
        model_name: str = "BAAI/bge-small-zh",
        batch_size: int = 32,
        device: str = "cpu",
    ):
        """
        Args:
            data_dir: knowledge-base/ 目录路径
            model_name: sentence-transformers 模型名称
            batch_size: 编码时的批处理大小
            device: 计算设备（cpu 或 cuda）
        """
        self.data_dir = Path(data_dir)
        self.model_name = model_name
        self.batch_size = batch_size
        self.device = device
        self._model = None

    # ---- 模型延迟加载 ----

    @property
    def model(self):
        """延迟加载 sentence-transformers 模型。"""
        if self._model is None:
            logger.info("正在加载嵌入模型: %s（设备: %s）", self.model_name, self.device)
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name, device=self.device)
            logger.info("模型加载完成，嵌入维度: %d", self._model.get_sentence_embedding_dimension())
        return self._model

    # ---- 数据加载 ----

    def _load_json(self, filename: str) -> Optional[Any]:
        """加载 JSON 文件，不存在时返回 None。"""
        filepath = self.data_dir / filename
        if not filepath.exists():
            logger.error("文件不存在: %s", filepath)
            return None
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            logger.info("成功加载 %s", filepath)
            return data
        except json.JSONDecodeError as e:
            logger.error("JSON 解析失败 (%s): %s", filepath, e)
            return None
        except Exception as e:
            logger.error("读取文件失败 (%s): %s", filepath, e)
            return None

    def _load_drone_types(self) -> Optional[List[Dict]]:
        """加载 drone_types.json，返回无人机列表。"""
        data = self._load_json("drone_types.json")
        if data is None:
            return None
        # 支持两种格式：直接列表 或 {"drones": [...]}
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("drones", [])
        logger.error("drone_types.json 格式不正确，期望 list 或含 'drones' 键的 dict")
        return None

    def _load_scenario_templates(self) -> Optional[List[Dict]]:
        """加载 scenario_templates.json，返回场景模板列表。"""
        data = self._load_json("scenario_templates.json")
        if data is None:
            return None
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("templates", data.get("scenarios", []))
        logger.error("scenario_templates.json 格式不正确，期望 list 或含 'templates'/'scenarios' 键的 dict")
        return None

    def _load_frequency_bands(self) -> Optional[List[Dict]]:
        """加载 frequency_bands.json，返回频段列表。"""
        data = self._load_json("frequency_bands.json")
        if data is None:
            return None
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("bands", data.get("frequency_bands", []))
        logger.error("frequency_bands.json 格式不正确，期望 list 或含 'bands'/'frequency_bands' 键的 dict")
        return None

    # ---- 文本构建 ----

    @staticmethod
    def _build_drone_text(drone: Dict) -> str:
        """将无人机各字段拼接为用于嵌入的文本。"""
        parts: List[str] = []

        # 名称
        name = drone.get("name", "")
        if name:
            parts.append(f"名称: {name}")

        name_cn = drone.get("name_cn", drone.get("nameCn", ""))
        if name_cn:
            parts.append(f"中文名: {name_cn}")

        # 分类
        category = drone.get("category", "")
        if category:
            parts.append(f"类别: {category}")

        # RF 特征
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

        # 典型任务
        mission = drone.get("typical_mission", drone.get("typicalMission", ""))
        if mission:
            parts.append(f"典型任务: {mission}")

        # 备注说明
        notes = drone.get("notes", "")
        if notes:
            parts.append(f"备注: {notes}")

        # 其他特征
        manufacturer = drone.get("manufacturer", "")
        if manufacturer:
            parts.append(f"制造商: {manufacturer}")

        return "；".join(parts)

    @staticmethod
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

        # 输入条件
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

        # 期望输出
        expected = scenario.get("expected_output", scenario.get("expected", {}))
        if isinstance(expected, dict):
            trigger = expected.get("trigger_reason_contains", "")
            if trigger:
                parts.append(f"触发原因: {trigger}")

        return "；".join(parts)

    @staticmethod
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

    # ---- 嵌入生成与索引构建 ----

    def _build_index(
        self,
        items: List[Dict],
        text_builder,
        id_field: str,
        entity_type: str,
    ) -> Tuple[Any, np.ndarray, List[str], int]:
        """通用方法：生成文本嵌入并构建 FAISS 索引。

        Args:
            items: 要索引的数据项列表
            text_builder: 将数据项转换为文本的函数
            id_field: 用作唯一标识的字段名
            entity_type: 实体类型名称（用于日志）

        Returns:
            (faiss_index, embeddings_array, metadata_ids, dimension)
        """
        if not items:
            logger.warning("%s 数据为空，跳过索引构建", entity_type)
            return None, np.array([]), [], 0

        # 构建文本列表
        texts = []
        ids = []
        skipped = 0
        for item in items:
            text = text_builder(item)
            if not text.strip():
                skipped += 1
                continue
            texts.append(text)
            item_id = item.get(id_field, f"unknown_{len(ids)}")
            ids.append(str(item_id))

        if skipped:
            logger.warning("%s: %d 条数据因文本为空被跳过", entity_type, skipped)

        logger.info("%s: 共 %d 条数据待编码", entity_type, len(texts))
        if not texts:
            logger.error("%s: 无有效文本数据，无法构建索引", entity_type)
            return None, np.array([]), [], 0

        # 编码
        t0 = time.perf_counter()
        embeddings = self.model.encode(
            texts,
            batch_size=self.batch_size,
            show_progress_bar=True,
            normalize_embeddings=True,  # L2 归一化，使内积等价于余弦相似度
        )
        encode_time = time.perf_counter() - t0
        logger.info("%s: 编码完成，耗时 %.2f 秒，嵌入维度 %d", entity_type, encode_time, embeddings.shape[1])

        # 确保是 float32
        embeddings = np.asarray(embeddings, dtype=np.float32)

        # 构建 FAISS 索引
        import faiss
        dim = embeddings.shape[1]
        index = faiss.IndexFlatIP(dim)  # 内积索引，配合归一化向量 = 余弦相似度
        index.add(embeddings)

        logger.info("%s: FAISS 索引构建完成，共 %d 条向量", entity_type, index.ntotal)
        return index, embeddings, ids, dim

    # ---- 保存 ----

    def _save_index(self, index, filename: str) -> bool:
        """保存 FAISS 索引到文件。"""
        import faiss
        output_dir = self.data_dir / "faiss_index"
        output_dir.mkdir(parents=True, exist_ok=True)
        filepath = output_dir / filename
        try:
            faiss.write_index(index, str(filepath))
            file_size_kb = filepath.stat().st_size / 1024
            logger.info("FAISS 索引已保存: %s (%.1f KB)", filepath, file_size_kb)
            return True
        except Exception as e:
            logger.error("保存 FAISS 索引失败 (%s): %s", filepath, e)
            return False

    def _save_metadata(self, ids: List[str], filename: str) -> bool:
        """保存索引位置到 ID 的元数据映射。"""
        output_dir = self.data_dir / "faiss_index"
        output_dir.mkdir(parents=True, exist_ok=True)
        filepath = output_dir / filename
        # 格式: {"0": "drone_id_1", "1": "drone_id_2", ...}
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

    # ---- 统计输出 ----

    @staticmethod
    def _print_stats(
        entity_type: str,
        index,
        embeddings: np.ndarray,
        ids: List[str],
        elapsed: float,
    ):
        """打印索引构建的统计信息。"""
        total = index.ntotal if index else 0
        dim = embeddings.shape[1] if embeddings.size else 0
        logger.info("=" * 60)
        logger.info("  [%s] 索引构建统计", entity_type)
        logger.info("  - 嵌入向量数量: %d", total)
        logger.info("  - 嵌入维度:     %d", dim)
        logger.info("  - 元数据条目:   %d", len(ids))
        logger.info("  - 耗时:         %.2f 秒", elapsed)
        logger.info("=" * 60)

    # ---- 主流程 ----

    def run(self) -> bool:
        """执行完整初始化流程。成功返回 True，失败返回 False。"""
        overall_start = time.perf_counter()
        all_success = True

        # ---- 1. 无人机类型 ----
        logger.info(">>> 阶段 1/3: 索引无人机类型 (drone_types.json)")
        t0 = time.perf_counter()
        drones = self._load_drone_types()
        if drones is not None:
            index, embeddings, ids, dim = self._build_index(
                drones,
                self._build_drone_text,
                id_field="drone_id",
                entity_type="无人机类型",
            )
            if index is not None:
                saved_idx = self._save_index(index, "drone_types.index")
                saved_meta = self._save_metadata(ids, "drone_metadata.json")
                if not saved_idx or not saved_meta:
                    all_success = False
            else:
                all_success = False
            self._print_stats("无人机类型", index, embeddings, ids, time.perf_counter() - t0)
        else:
            logger.warning("跳过无人机类型索引（文件不存在或格式错误）")
            all_success = False

        # ---- 2. 场景模板 ----
        logger.info(">>> 阶段 2/3: 索引场景模板 (scenario_templates.json)")
        t0 = time.perf_counter()
        scenarios = self._load_scenario_templates()
        if scenarios is not None:
            index, embeddings, ids, dim = self._build_index(
                scenarios,
                self._build_scenario_text,
                id_field="scenario_id",
                entity_type="场景模板",
            )
            if index is not None:
                saved_idx = self._save_index(index, "scenario_templates.index")
                saved_meta = self._save_metadata(ids, "scenario_metadata.json")
                if not saved_idx or not saved_meta:
                    all_success = False
            else:
                all_success = False
            self._print_stats("场景模板", index, embeddings, ids, time.perf_counter() - t0)
        else:
            logger.warning("跳过场景模板索引（文件不存在或格式错误）")
            all_success = False

        # ---- 3. 频段 ----
        logger.info(">>> 阶段 3/3: 索引频段数据 (frequency_bands.json)")
        t0 = time.perf_counter()
        bands = self._load_frequency_bands()
        if bands is not None:
            index, embeddings, ids, dim = self._build_index(
                bands,
                self._build_frequency_band_text,
                id_field="band_id",
                entity_type="频段数据",
            )
            if index is not None:
                saved_idx = self._save_index(index, "frequency_bands.index")
                saved_meta = self._save_metadata(ids, "frequency_bands_metadata.json")
                if not saved_idx or not saved_meta:
                    all_success = False
            else:
                all_success = False
            self._print_stats("频段数据", index, embeddings, ids, time.perf_counter() - t0)
        else:
            logger.warning("跳过频段数据索引（文件不存在或格式错误）")
            all_success = False

        overall_elapsed = time.perf_counter() - overall_start
        logger.info("=" * 60)
        logger.info("  知识库初始化完成")
        logger.info("  总耗时: %.2f 秒", overall_elapsed)
        logger.info("  最终状态: %s", "成功" if all_success else "部分失败（请检查日志）")
        logger.info("=" * 60)

        return all_success


# ---------------------------------------------------------------------------
# 命令行入口
# ---------------------------------------------------------------------------

def main() -> None:
    """主函数：解析命令行参数并执行初始化。"""
    parser = argparse.ArgumentParser(
        description="初始化知识库：生成 drone_types / scenario_templates / frequency_bands 的 FAISS 索引",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python init_knowledge_base.py
  python init_knowledge_base.py --data-dir ../knowledge-base --model-name BAAI/bge-large-zh
  python init_knowledge_base.py --device cpu --batch-size 64
        """,
    )

    default_data_dir = _get_script_dir().parent / "knowledge-base"

    parser.add_argument(
        "--data-dir",
        type=str,
        default=str(default_data_dir),
        help="知识库数据目录路径 (默认: %(default)s)",
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
        help="计算设备: auto=自动检测, cpu=强制CPU, cuda=强制GPU (默认: auto)",
    )

    args = parser.parse_args()

    # 解析路径
    script_dir = _get_script_dir()
    data_dir = _resolve_path(script_dir.parent, args.data_dir)

    if not data_dir.exists():
        logger.warning("数据目录不存在，将创建: %s", data_dir)
        data_dir.mkdir(parents=True, exist_ok=True)

    logger.info("数据目录: %s", data_dir)
    logger.info("模型名称: %s", args.model_name)
    logger.info("批处理大小: %d", args.batch_size)
    logger.info("设备选择: %s", args.device)

    device = _resolve_device(args.device)
    logger.info("实际使用设备: %s", device)

    initializer = KnowledgeBaseInitializer(
        data_dir=data_dir,
        model_name=args.model_name,
        batch_size=args.batch_size,
        device=device,
    )

    success = initializer.run()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
