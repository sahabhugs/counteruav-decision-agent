"""
限流器模块
提供全局和单目标粒度的调用频率控制，线程安全。
"""

from __future__ import annotations

import threading
import time
from typing import Dict


class RateLimiter:
    """简单的令牌桶风格限流器，控制 LLM 调用频率。

    约束：
    - 全局每分钟最多 MAX_CALLS_PER_MINUTE 次调用
    - 单目标每分钟最多 3 次调用
    - 两次调用之间至少间隔 COOLDOWN_SECONDS 秒
    """

    def __init__(self, max_calls_per_minute: int = 10, cooldown_seconds: int = 5):
        self._max_calls_per_minute = max_calls_per_minute
        self._cooldown_seconds = cooldown_seconds
        self._per_target_max = 3  # 单目标每分钟最多 3 次

        self._lock = threading.Lock()

        # 全局调用时间戳列表（滑动窗口）
        self._global_timestamps: list[float] = []

        # 单目标调用时间戳 dict: target_id -> list[float]
        self._target_timestamps: Dict[str, list[float]] = {}

        # 上次调用时间
        self._last_call_time: float = 0.0

    def _clean_old_timestamps(self, timestamps: list[float], window: float = 60.0) -> list[float]:
        """清理超过时间窗口的旧时间戳。"""
        now = time.monotonic()
        return [ts for ts in timestamps if now - ts < window]

    def try_acquire(self, target_id: str) -> bool:
        """尝试获取调用许可。

        Args:
            target_id: 目标 ID（用于单目标限流）。

        Returns:
            True 表示允许调用，False 表示被限流。
        """
        with self._lock:
            now = time.monotonic()

            # 1. 检查冷却时间
            if now - self._last_call_time < self._cooldown_seconds:
                return False

            # 2. 清理并检查全局窗口
            self._global_timestamps = self._clean_old_timestamps(self._global_timestamps)
            if len(self._global_timestamps) >= self._max_calls_per_minute:
                return False

            # 3. 清理并检查单目标窗口
            if target_id not in self._target_timestamps:
                self._target_timestamps[target_id] = []
            self._target_timestamps[target_id] = self._clean_old_timestamps(
                self._target_timestamps[target_id]
            )
            if len(self._target_timestamps[target_id]) >= self._per_target_max:
                return False

            # 4. 通过所有检查，记录时间戳
            self._global_timestamps.append(now)
            self._target_timestamps[target_id].append(now)
            self._last_call_time = now
            return True

    def get_status(self) -> dict:
        """返回限流器当前状态。

        Returns:
            包含全局和单目标状态信息的字典。
        """
        with self._lock:
            now = time.monotonic()

            # 清理
            self._global_timestamps = self._clean_old_timestamps(self._global_timestamps)

            target_status = {}
            for tid, tss in list(self._target_timestamps.items()):
                cleaned = self._clean_old_timestamps(tss)
                if cleaned:
                    target_status[tid] = {
                        "count_last_minute": len(cleaned),
                        "limit": self._per_target_max,
                    }
                else:
                    del self._target_timestamps[tid]

            seconds_since_last = now - self._last_call_time if self._last_call_time > 0 else 999.0

            return {
                "global_calls_last_minute": len(self._global_timestamps),
                "global_limit": self._max_calls_per_minute,
                "cooldown_seconds": self._cooldown_seconds,
                "seconds_since_last_call": round(seconds_since_last, 2),
                "per_target_status": target_status,
            }

    def reset(self) -> None:
        """重置限流器状态（用于测试）。"""
        with self._lock:
            self._global_timestamps.clear()
            self._target_timestamps.clear()
            self._last_call_time = 0.0
