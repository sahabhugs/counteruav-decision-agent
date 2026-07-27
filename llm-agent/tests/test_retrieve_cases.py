"""
retrieve_cases 工具单元测试
测试相似案例检索（动态 Few-shot）。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_src_dir = Path(__file__).resolve().parent.parent / "src"
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))


class TestRetrieveCases(unittest.TestCase):
    """测试 retrieve_cases 工具。"""

    def setUp(self):
        from tools.retrieve_cases import retrieve_cases
        self.retrieve_cases = retrieve_cases

    # ========== 参数校验 ==========

    def test_empty_query(self):
        """测试空查询。"""
        result = self.retrieve_cases({"situation_desc": ""})
        self.assertFalse(result["success"])
        self.assertIn("不能为空", result.get("error", ""))

    # ========== 静态回退（冷启动） ==========

    def test_fallback_static_examples(self):
        """测试冷启动阶段回退到静态 Few-shot 示例。"""
        with patch("tools.retrieve_cases._load_faiss_index", return_value=None):
            result = self.retrieve_cases({
                "situation_desc": "未知型号无人机高速接近指挥中心，距离500m",
                "top_k": 3,
            })

        self.assertTrue(result["success"])
        data = result["data"]
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0)
        # 应包含案例字段
        for case in data:
            self.assertIn("case_id", case)
            self.assertIn("similarity", case)

    def test_fallback_returns_requested_count(self):
        """测试回退时返回正确数量的案例（不超过可用匹配数）。"""
        with patch("tools.retrieve_cases._load_faiss_index", return_value=None):
            result = self.retrieve_cases({
                "situation_desc": "蜂群无人机袭击防空阵地 多频段跳频 高速",
                "top_k": 2,
            })

        self.assertTrue(result["success"])
        # 返回数应 <= top_k
        self.assertLessEqual(len(result["data"]), 2)
        self.assertGreater(len(result["data"]), 0)

    # ========== 案例结构 ==========

    def test_case_structure(self):
        """测试案例结构完整性。"""
        with patch("tools.retrieve_cases._load_faiss_index", return_value=None):
            result = self.retrieve_cases({
                "situation_desc": "FPV竞速无人机接近弹药库",
                "top_k": 1,
            })

        self.assertTrue(result["success"])
        case = result["data"][0]
        required_fields = [
            "case_id", "similarity", "scenario", "decision_summary",
            "commander_verdict", "outcome", "key_lessons",
        ]
        for field in required_fields:
            self.assertIn(field, case, f"案例缺少字段: {field}")

    # ========== 关键词匹配 ==========

    def test_keyword_matching(self):
        """测试关键词匹配（应返回与无人机相关的案例）。"""
        with patch("tools.retrieve_cases._load_faiss_index", return_value=None):
            result = self.retrieve_cases({
                "situation_desc": "平民区上空有无人机悬挂不明载荷，人群密集 改装工业无人机",
                "top_k": 3,
            })

        self.assertTrue(result["success"])
        titles = [c.get("title", c.get("scenario", "")) for c in result["data"]]
        titles_str = " ".join(titles)
        # 至少应包含与"无人机"相关的案例（所有静态示例都包含）
        self.assertTrue(
            "无人机" in titles_str or "FPV" in titles_str or "蜂群" in titles_str,
            f"关键词匹配应返回相关案例，实际: {titles}"
        )

    # ========== 自定义 top_k ==========

    def test_default_top_k(self):
        """测试默认返回数量（不超过可用匹配）。"""
        with patch("tools.retrieve_cases._load_faiss_index", return_value=None):
            result = self.retrieve_cases({
                "situation_desc": "FPV 高速 接近 弹药库 未知信号",
            })

        self.assertTrue(result["success"])
        # 返回数应 <= 默认 top_k=3
        self.assertLessEqual(len(result["data"]), 3)
        self.assertGreater(len(result["data"]), 0)

    def test_top_k_limit(self):
        """测试 top_k 上限。"""
        with patch("tools.retrieve_cases._load_faiss_index", return_value=None):
            result = self.retrieve_cases({
                "situation_desc": "测试",
                "top_k": 20,
            })

        self.assertTrue(result["success"])
        # 不应超过可用案例数量，且最多返回 top_k 个
        self.assertLessEqual(len(result["data"]), 20)


if __name__ == "__main__":
    unittest.main(verbosity=2)
