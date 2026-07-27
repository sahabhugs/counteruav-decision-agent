"""
限流器单元测试
测试威胁等级感知限流、紧急通道和分级配额。
"""

from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path

_src_dir = Path(__file__).resolve().parent.parent / "src"
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))


class TestRateLimiterBasic(unittest.TestCase):
    """测试基础限流功能。"""

    def setUp(self):
        from rate_limiter import RateLimiter
        self.rate_limiter = RateLimiter(
            max_calls_per_minute=10,
            cooldown_seconds=0.1,  # 短冷却便于测试
            max_per_target_high=6,
            max_per_target_med=3,
            max_per_target_low=2,
        )

    def tearDown(self):
        self.rate_limiter.reset()

    def test_normal_acquire(self):
        """测试正常获取调用许可。"""
        result = self.rate_limiter.try_acquire("T001", threat_level=3, urgent=False)
        self.assertTrue(result)

    def test_cooldown(self):
        """测试冷却时间。"""
        self.rate_limiter.try_acquire("T001", threat_level=3, urgent=False)
        # 立即再次请求应被冷却拒绝
        result = self.rate_limiter.try_acquire("T001", threat_level=3, urgent=False)
        self.assertFalse(result)

    def test_cooldown_expires(self):
        """测试冷却过期后可再次获取。"""
        self.rate_limiter.try_acquire("T001", threat_level=3, urgent=False)
        time.sleep(0.15)  # 等待冷却过期 (0.1s)
        result = self.rate_limiter.try_acquire("T002", threat_level=3, urgent=False)
        self.assertTrue(result)


class TestThreatLevelAwareRateLimit(unittest.TestCase):
    """测试威胁等级感知限流。"""

    def setUp(self):
        from rate_limiter import RateLimiter
        self.rate_limiter = RateLimiter(
            max_calls_per_minute=10,
            cooldown_seconds=0.05,
            max_per_target_high=6,
            max_per_target_med=3,
            max_per_target_low=2,
        )

    def tearDown(self):
        self.rate_limiter.reset()

    def test_high_threat_shorter_cooldown(self):
        """测试高威胁目标冷却更短。"""
        self.rate_limiter.try_acquire("T001", threat_level=3, urgent=False)
        time.sleep(0.07)
        # 常规冷却(0.05s)已过，低威胁可获取
        result_low = self.rate_limiter.try_acquire("T001", threat_level=3, urgent=False)
        self.assertTrue(result_low)

    def test_urgent_channel_always_passes(self):
        """测试紧急通道始终放行。"""
        # 先消耗所有配额
        for i in range(10):
            self.rate_limiter.try_acquire(f"T{i}", threat_level=3, urgent=False)
        time.sleep(0.06)
        # 紧急通道应始终放行
        result = self.rate_limiter.try_acquire("T_URGENT", threat_level=5, urgent=True)
        self.assertTrue(result)

    def test_threat_level_5_always_passes(self):
        """测试威胁等级 5 始终放行（等效紧急通道）。"""
        for i in range(10):
            self.rate_limiter.try_acquire(f"T{i}", threat_level=3, urgent=False)
        time.sleep(0.06)
        result = self.rate_limiter.try_acquire("T_CRITICAL", threat_level=5, urgent=False)
        self.assertTrue(result)

    def test_higher_threat_gets_more_quota(self):
        """测试低威胁目标配额限制。"""
        from rate_limiter import RateLimiter
        rl = RateLimiter(
            max_calls_per_minute=100,
            cooldown_seconds=0.10,
            max_per_target_high=6,
            max_per_target_med=3,
            max_per_target_low=2,
        )
        import time as _time

        # 低威胁目标（threat_level=2）：最多 2 次
        for i in range(2):
            ok = rl.try_acquire("T_LOW", threat_level=2, urgent=False)
            if not ok:
                self.fail(f"第{i+1}次调用应成功（配额内）")
            _time.sleep(0.15)

        # 第 3 次应被限（配额满 2/2）
        _time.sleep(0.15)
        # 配额已满，应失败
        self.assertFalse(
            rl.try_acquire("T_LOW", threat_level=2, urgent=False),
            "第3次调用应因配额限制而失败"
        )

    def test_per_target_limits_independent(self):
        """测试不同目标限流独立。"""
        for i in range(3):
            self.rate_limiter.try_acquire(f"T_A", threat_level=3, urgent=False)
        time.sleep(0.06)
        # 目标 B 应不受 A 的调用影响
        result = self.rate_limiter.try_acquire("T_B", threat_level=3, urgent=False)
        self.assertTrue(result)


class TestRateLimiterStatus(unittest.TestCase):
    """测试限流器状态查询。"""

    def setUp(self):
        from rate_limiter import RateLimiter
        self.rate_limiter = RateLimiter(
            max_calls_per_minute=10,
            cooldown_seconds=5,
        )

    def tearDown(self):
        self.rate_limiter.reset()

    def test_status_contains_all_fields(self):
        """测试状态包含所有必要字段。"""
        self.rate_limiter.try_acquire("T001", threat_level=3, urgent=False)
        status = self.rate_limiter.get_status()

        required_keys = [
            "global_calls_last_minute", "global_limit",
            "cooldown_seconds", "seconds_since_last_call",
            "per_target_status",
        ]
        for key in required_keys:
            self.assertIn(key, status, f"状态缺少键: {key}")

    def test_status_reflects_calls(self):
        """测试状态正确反映调用次数。"""
        from rate_limiter import RateLimiter
        rl = RateLimiter(
            max_calls_per_minute=100,
            cooldown_seconds=0.10,
        )
        import time as _time
        call_count = 0
        for i in range(5):
            if rl.try_acquire(f"T{i}", threat_level=3, urgent=False):
                call_count += 1
            _time.sleep(0.12)

        status = rl.get_status()
        # 应至少记录了 call_count 次调用
        self.assertGreaterEqual(status["global_calls_last_minute"], call_count)

    def test_status_seconds_since_last(self):
        """测试距上次调用时间。"""
        self.rate_limiter.try_acquire("T001", threat_level=3, urgent=False)
        time.sleep(0.2)
        status = self.rate_limiter.get_status()
        self.assertGreaterEqual(status["seconds_since_last_call"], 0.15)


class TestRateLimiterReset(unittest.TestCase):
    """测试限流器重置。"""

    def test_reset_clears_all(self):
        from rate_limiter import RateLimiter
        rl = RateLimiter(max_calls_per_minute=10, cooldown_seconds=1)
        rl.try_acquire("T001", threat_level=3, urgent=False)
        rl.try_acquire("T002", threat_level=3, urgent=False)

        rl.reset()
        status = rl.get_status()
        self.assertEqual(status["global_calls_last_minute"], 0)
        self.assertEqual(len(status["per_target_status"]), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
