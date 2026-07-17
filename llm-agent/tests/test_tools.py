"""
工具模块单元测试
测试五个工具函数的正常流程和错误处理流程。
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, Mock

# 添加 src 目录到 sys.path
_src_dir = Path(__file__).resolve().parent.parent / "src"
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))


class TestSearchRules(unittest.TestCase):
    """测试 search_rules 工具。"""

    def setUp(self):
        from tools.search_rules import search_rules
        self.search_rules = search_rules

    def test_empty_query(self):
        """测试空查询参数。"""
        result = self.search_rules({"query": ""})
        self.assertFalse(result["success"])
        self.assertIn("不能为空", result.get("error", ""))

    def test_valid_query_with_mock_http(self):
        """测试正常查询（Mock HTTP）。"""
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"id": 1, "name": "高速接近处置规则", "content": "当目标高速接近..."},
            {"id": 2, "name": "蜂群处置规则", "content": "当检测到蜂群..."},
        ]
        mock_response.raise_for_status = MagicMock()

        with patch("tools.search_rules.httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.return_value = mock_response
            result = self.search_rules({"query": "高速接近"})

        self.assertTrue(result["success"])
        self.assertGreaterEqual(len(result["data"]), 1)

    def test_http_connect_error_fallback_local(self):
        """测试 HTTP 连接失败回退到本地搜索。"""
        with patch("tools.search_rules.httpx.Client") as mock_client:
            from httpx import ConnectError
            mock_client.return_value.__enter__.return_value.get.side_effect = ConnectError("连接失败")

            # 由于本地文件不存在，应返回空结果
            with patch("tools.search_rules._LOCAL_RULES_PATH") as mock_path:
                mock_path.exists.return_value = False
                result = self.search_rules({"query": "测试"})

        # 回退到本地搜索（文件不存在时返回空数据）
        self.assertIsNotNone(result)
        # 不应抛出异常

    def test_search_with_layers_filter(self):
        """测试带层级过滤的搜索。"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "rules": [
                {"name": "规则1", "layer": 1, "content": "L1规则"},
                {"name": "规则2", "layer": 2, "content": "L2规则"},
                {"name": "规则3", "layer": 3, "content": "L3规则"},
            ]
        }
        mock_response.raise_for_status = MagicMock()

        with patch("tools.search_rules.httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.return_value = mock_response
            result = self.search_rules({"query": "规则", "layers": [1, 2]})

        self.assertTrue(result["success"])


class TestQueryKB(unittest.TestCase):
    """测试 query_kb 工具。"""

    def setUp(self):
        from tools.query_kb import query_kb
        self.query_kb = query_kb

    def test_invalid_entity_type(self):
        """测试无效的实体类型。"""
        result = self.query_kb({"entity_type": "invalid_type", "query": "测试"})
        self.assertFalse(result["success"])
        self.assertIn("不支持的实体类型", result.get("error", ""))

    def test_empty_query(self):
        """测试空查询。"""
        result = self.query_kb({"entity_type": "drone", "query": ""})
        self.assertFalse(result["success"])
        self.assertIn("不能为空", result.get("error", ""))

    def test_query_with_mock_faiss(self):
        """测试 FAISS 查询（Mock）。"""
        mock_index = MagicMock()
        mock_index.ntotal = 100
        mock_index.search.return_value = (
            [[0.1, 0.3, 0.5]],  # distances
            [[0, 1, 2]],        # indices
        )

        mock_data = [
            {"model": "DJI Mavic 3", "category": "消费级", "max_speed_ms": 20},
            {"model": "Autel EVO II", "category": "消费级", "max_speed_ms": 22},
            {"model": "DJI Phantom 4", "category": "消费级", "max_speed_ms": 20},
        ]

        mock_model = MagicMock()
        mock_encode = MagicMock()
        mock_encode.encode.return_value = [[0.1, 0.2, 0.3]]

        with patch("tools.query_kb._load_faiss_index", return_value=mock_index), \
             patch("tools.query_kb._load_json_data", return_value=mock_data), \
             patch("tools.query_kb._get_embedding_model", return_value=mock_encode):
            result = self.query_kb({"entity_type": "drone", "query": "DJI 消费级", "top_k": 3})

        self.assertTrue(result["success"])
        self.assertGreater(len(result["data"]), 0)

    def test_fallback_json_search(self):
        """测试 JSON 回退搜索。"""
        mock_data = [
            {"model": "DJI Mini", "category": "微型", "manufacturer": "DJI"},
            {"model": "DJI Air", "category": "轻型", "manufacturer": "DJI"},
        ]

        with patch("tools.query_kb._load_faiss_index", return_value=None), \
             patch("tools.query_kb._load_json_data", return_value=mock_data):
            result = self.query_kb({"entity_type": "drone", "query": "DJI", "top_k": 2})

        self.assertTrue(result["success"])
        self.assertGreater(len(result["data"]), 0)

    def test_scenario_query_format(self):
        """测试场景模板查询的格式化。"""
        mock_data = [
            {
                "name": "蜂群攻击",
                "description": "5+无人机协同攻击",
                "typical_threats": ["饱和攻击"],
                "recommended_strategies": ["全频段压制"],
                "roi_constraints": {},
                "similar_cases": [],
            }
        ]

        with patch("tools.query_kb._load_faiss_index", return_value=None), \
             patch("tools.query_kb._load_json_data", return_value=mock_data):
            result = self.query_kb({"entity_type": "scenario", "query": "蜂群", "top_k": 1})

        self.assertTrue(result["success"])
        if result["data"]:
            self.assertEqual(result["data"][0]["type"], "scenario")


class TestRunTopsis(unittest.TestCase):
    """测试 run_topsis 工具。"""

    def setUp(self):
        from tools.run_topsis import run_topsis
        self.run_topsis = run_topsis

    def test_empty_target_id(self):
        """测试空目标 ID。"""
        result = self.run_topsis({"target_id": ""})
        self.assertFalse(result["success"])
        self.assertIn("不能为空", result.get("error", ""))

    def test_valid_http_response(self):
        """测试正常 HTTP 响应。"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "result": {
                "threat_score": 0.85,
                "threat_level": 5,
                "indicator_scores": {"speed": 0.9, "distance": 0.8},
                "positive_ideal_distance": 0.1,
                "negative_ideal_distance": 0.9,
            }
        }
        mock_response.raise_for_status = MagicMock()

        with patch("tools.run_topsis.httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.post.return_value = mock_response
            result = self.run_topsis({"target_id": "T001"})

        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["threat_score"], 0.85)
        self.assertEqual(result["data"]["threat_level"], 5)

    def test_local_fallback(self):
        """测试本地 TOPSIS 回退计算。"""
        with patch("tools.run_topsis.httpx.Client") as mock_client:
            from httpx import ConnectError
            mock_client.return_value.__enter__.return_value.post.side_effect = ConnectError("连接失败")
            result = self.run_topsis({
                "target_id": "T002",
                "speed_ms": 80,
                "distance_m": 2000,
                "altitude_m": 150,
                "signal_strength": 15,
                "target_type": "unknown",
            })

        self.assertTrue(result["success"])
        self.assertIn("threat_score", result["data"])
        self.assertIn("threat_level", result["data"])
        self.assertGreaterEqual(result["data"]["threat_level"], 1)
        self.assertLessEqual(result["data"]["threat_level"], 5)
        self.assertIn("_source", result["data"])
        self.assertEqual(result["data"]["_source"], "本地简化TOPSIS")

    def test_local_fallback_with_indicators(self):
        """测试带指标数据的本地回退。"""
        with patch("tools.run_topsis.httpx.Client") as mock_client:
            from httpx import ConnectError
            mock_client.return_value.__enter__.return_value.post.side_effect = ConnectError("连接失败")
            result = self.run_topsis({
                "target_id": "T003",
                "indicators": {
                    "speed_factor": 0.9,
                    "distance_factor": 0.8,
                    "altitude_factor": 0.3,
                    "signal_strength": 0.7,
                    "target_type_score": 0.6,
                },
            })

        self.assertTrue(result["success"])
        self.assertGreaterEqual(result["data"]["threat_score"], 0.0)
        self.assertLessEqual(result["data"]["threat_score"], 1.0)


class TestCheckDevices(unittest.TestCase):
    """测试 check_devices 工具。"""

    def setUp(self):
        from tools.check_devices import check_devices
        self.check_devices = check_devices

    def test_valid_http_response(self):
        """测试正常 HTTP 设备查询。"""
        mock_devices = [
            {
                "device_id": "jammer_01",
                "type": "干扰器",
                "status": "在线",
                "lat": 39.9, "lon": 116.4, "alt": 50,
                "effective_range_m": 5000,
                "current_target_id": "",
                "battery": 85, "temperature": 28,
                "uptime_hours": 72, "error_count": 0,
            },
            {
                "device_id": "laser_01",
                "type": "激光",
                "status": "维护中",
                "lat": 39.91, "lon": 116.41, "alt": 60,
                "effective_range_m": 3000,
                "current_target_id": "T005",
                "battery": 60, "temperature": 35,
                "uptime_hours": 48, "error_count": 2,
            },
        ]
        mock_response = MagicMock()
        mock_response.json.return_value = mock_devices
        mock_response.raise_for_status = MagicMock()

        with patch("tools.check_devices.httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.return_value = mock_response
            result = self.check_devices({})

        self.assertTrue(result["success"])
        self.assertEqual(len(result["data"]), 2)
        self.assertEqual(result["data"][0]["type"], "干扰器")

    def test_fallback_situation_data(self):
        """测试回退到态势数据。"""
        situation_devices = [
            {"id": "dev1", "device_type": "雷达", "status": "在线", "range_m": 10000},
        ]

        with patch("tools.check_devices.httpx.Client") as mock_client:
            from httpx import ConnectError
            mock_client.return_value.__enter__.return_value.get.side_effect = ConnectError("连接失败")
            result = self.check_devices({
                "_situation": {"devices": situation_devices},
            })

        self.assertTrue(result["success"])
        self.assertGreaterEqual(len(result["data"]), 1)

    def test_filter_by_device_type(self):
        """测试按设备类型筛选。"""
        mock_devices = [
            {"device_id": "jammer_01", "type": "干扰器", "status": "在线"},
            {"device_id": "laser_01", "type": "激光", "status": "在线"},
        ]
        mock_response = MagicMock()
        mock_response.json.return_value = mock_devices
        mock_response.raise_for_status = MagicMock()

        with patch("tools.check_devices.httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.return_value = mock_response
            result = self.check_devices({"device_type": "激光"})

        self.assertTrue(result["success"])
        self.assertEqual(len(result["data"]), 2)  # HTTP 筛选在服务端

    def test_normalize_device_info(self):
        """测试设备信息标准化。"""
        from tools.check_devices import _normalize_device_info

        raw = {"id": "D001", "device_type": "干扰器", "state": "待命", "range_m": 4000}
        normalized = _normalize_device_info(raw)

        self.assertEqual(normalized["device_id"], "D001")
        self.assertEqual(normalized["type"], "干扰器")
        self.assertEqual(normalized["status"], "待命")
        self.assertIn("position", normalized)
        self.assertIn("health_metrics", normalized)


class TestProposeRule(unittest.TestCase):
    """测试 propose_rule 工具。"""

    def setUp(self):
        from tools.propose_rule import propose_rule
        self.propose_rule = propose_rule

    def test_empty_rule_text(self):
        """测试空规则文本。"""
        result = self.propose_rule({
            "rule_text": "",
            "reason": "测试",
            "source_decision_id": "D001",
        })
        self.assertFalse(result["success"])
        self.assertIn("rule_text", result.get("error", ""))

    def test_empty_reason(self):
        """测试空原因。"""
        result = self.propose_rule({
            "rule_text": "新规则",
            "reason": "",
            "source_decision_id": "D001",
        })
        self.assertFalse(result["success"])
        self.assertIn("reason", result.get("error", ""))

    def test_empty_source_id(self):
        """测试空来源决策 ID。"""
        result = self.propose_rule({
            "rule_text": "新规则",
            "reason": "测试",
            "source_decision_id": "",
        })
        self.assertFalse(result["success"])
        self.assertIn("source_decision_id", result.get("error", ""))

    def test_valid_http_proposal(self):
        """测试正常 HTTP 提案提交。"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "proposal_id": "prop-12345",
            "status": "submitted",
        }
        mock_response.raise_for_status = MagicMock()

        with patch("tools.propose_rule.httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.post.return_value = mock_response
            result = self.propose_rule({
                "rule_text": "当目标距离小于1km且速度大于30m/s时，建议启动全频段压制",
                "reason": "LLM 推理发现的新模式",
                "source_decision_id": "D-2024-001",
            })

        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["status"], "submitted")

    def test_local_fallback_save(self):
        """测试本地回退保存。"""
        with patch("tools.propose_rule.httpx.Client") as mock_client:
            from httpx import ConnectError
            mock_client.return_value.__enter__.return_value.post.side_effect = ConnectError("连接失败")

            with patch("tools.propose_rule._BACKUP_PATH") as mock_path:
                mock_path.exists.return_value = False
                mock_path.parent.mkdir = MagicMock()

                # Mock 文件写入
                m = MagicMock()
                with patch("builtins.open", m):
                    result = self.propose_rule({
                        "rule_text": "回退保存规则",
                        "reason": "测试回退",
                        "source_decision_id": "D-2024-002",
                    })

        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["status"], "pending_local")


class TestToolRegistry(unittest.TestCase):
    """测试工具注册中心。"""

    def setUp(self):
        from tools.registry import ToolRegistry
        self.registry = ToolRegistry()

    def test_register_and_execute(self):
        """测试注册和执行工具。"""
        def echo(args):
            return {"success": True, "data": args, "error": ""}

        self.registry.register("echo", echo, "回显工具")
        self.assertTrue(self.registry.has_tool("echo"))

        result = self.registry.execute("echo", {"msg": "hello"})
        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["msg"], "hello")

    def test_execute_unregistered_tool(self):
        """测试执行未注册工具。"""
        result = self.registry.execute("nonexistent", {})
        self.assertFalse(result["success"])
        self.assertIn("未注册", result.get("error", ""))

    def test_tool_execution_exception(self):
        """测试工具执行异常。"""
        def failing_tool(args):
            raise ValueError("测试异常")

        self.registry.register("failing", failing_tool, "会失败的工具")
        result = self.registry.execute("failing", {})
        self.assertFalse(result["success"])
        self.assertIn("测试异常", result.get("error", ""))

    def test_get_descriptions(self):
        """测试获取工具描述。"""
        self.registry.register("tool1", lambda x: {}, "工具1描述")
        self.registry.register("tool2", lambda x: {}, "工具2描述")

        desc = self.registry.get_descriptions()
        self.assertIn("tool1", desc)
        self.assertIn("tool2", desc)
        self.assertIn("工具1描述", desc)

    def test_list_tools(self):
        """测试列出工具。"""
        self.registry.register("a", lambda x: {}, "A")
        self.registry.register("b", lambda x: {}, "B")

        tools = self.registry.list_tools()
        self.assertEqual(len(tools), 2)
        self.assertIn("a", tools)
        self.assertIn("b", tools)

    def test_unregister(self):
        """测试注销工具。"""
        self.registry.register("temp", lambda x: {}, "临时工具")
        self.assertTrue(self.registry.unregister("temp"))
        self.assertFalse(self.registry.has_tool("temp"))
        self.assertFalse(self.registry.unregister("nonexistent"))

    def test_get_tool_count(self):
        """测试工具计数。"""
        self.assertEqual(self.registry.get_tool_count(), 0)
        self.registry.register("t1", lambda x: {}, "T1")
        self.assertEqual(self.registry.get_tool_count(), 1)
        self.registry.register("t2", lambda x: {}, "T2")
        self.assertEqual(self.registry.get_tool_count(), 2)


class TestToolErrorHandling(unittest.TestCase):
    """测试工具错误处理（连接拒绝等）。"""

    def test_search_rules_connection_refused(self):
        """测试规则搜索连接被拒绝。"""
        from tools.search_rules import search_rules

        with patch("tools.search_rules.httpx.Client") as mock_client:
            from httpx import ConnectError
            mock_client.return_value.__enter__.return_value.get.side_effect = ConnectError("连接被拒绝")

            # 模拟本地文件存在以避免进一步回退
            with patch("tools.search_rules._LOCAL_RULES_PATH") as mock_path:
                mock_path.exists.return_value = False
                result = search_rules({"query": "测试连接拒绝"})

        # 不应抛出异常
        self.assertIsNotNone(result)

    def test_query_kb_no_index_no_data(self):
        """测试知识库查询无索引也无数据。"""
        from tools.query_kb import query_kb

        with patch("tools.query_kb._load_faiss_index", return_value=None), \
             patch("tools.query_kb._load_json_data", return_value=None):
            result = query_kb({"entity_type": "drone", "query": "测试"})

        self.assertFalse(result["success"])

    def test_run_topsis_timeout(self):
        """测试 TOPSIS 请求超时。"""
        from tools.run_topsis import run_topsis

        with patch("tools.run_topsis.httpx.Client") as mock_client:
            from httpx import TimeoutException
            mock_client.return_value.__enter__.return_value.post.side_effect = TimeoutException("请求超时")
            result = run_topsis({"target_id": "T099"})

        # 应回退到本地计算
        self.assertTrue(result["success"])
        self.assertIn("_source", result["data"])

    def test_check_devices_empty_situation(self):
        """测试设备查询空态势数据。"""
        from tools.check_devices import check_devices

        with patch("tools.check_devices.httpx.Client") as mock_client:
            from httpx import ConnectError
            mock_client.return_value.__enter__.return_value.get.side_effect = ConnectError("连接失败")
            result = check_devices({"_situation": {}})

        self.assertTrue(result["success"])
        self.assertEqual(result["data"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
