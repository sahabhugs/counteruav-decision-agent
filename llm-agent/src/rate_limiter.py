"""
限流器模块（威胁等级感知 + 紧急通道）
提供全局和单目标粒度的调用频率控制，线程安全。

改进：
- 紧急通道：threat_level=5 或 urgent=True 直接放行
- 分级配额：高威胁目标配额更多
- 动态冷却：高威胁冷却更短
"""

from __future__ import annotations

import threading
import time
from typing import Dict


class RateLimiter:
    """威胁等级感知限流器。

    约束：
    - 全局每分钟最多 max_calls_per_minute 次调用（含高威胁额外配额）
    - 单目标配额按威胁等级分级
    - 紧急通道（threat_level=5 或 urgent=True）始终放行
    - 高威胁冷却时间更短
    """

    def __init__(
        self,
        max_calls_per_minute: int = 10,
        cooldown_seconds: int = 5,
        max_per_target_high: int = 6,
        max_per_target_med: int = 3,
        max_per_target_low: int = 2,
        cooldown_high_threat_ms: float = 1.0,
    ):
        self._max_calls_per_minute = max_calls_per_minute
        self._cooldown_seconds = cooldown_seconds
        self._max_per_target_high = max_per_target_high
        self._max_per_target_med = max_per_target_med
        self._max_per_target_low = max_per_target_low
        self._cooldown_high_threat_ms = cooldown_high_threat_ms

        self._lock = threading.Lock()

        # 全局调用时间戳列表（滑动窗口）
        self._global_timestamps: list[float] = []
        # 单目标调用时间戳
        self._target_timestamps: Dict[str, list[float]] = {}
        # 上次调用时间
        self._last_call_time: float = 0.0

    def _clean_old_timestamps(self, timestamps: list[float], window: float = 60.0) -> list[float]:
        now = time.monotonic()
        return [ts for ts in timestamps if now - ts < window]

    def _get_max_per_target(self, threat_level: int) -> int:
        """根据威胁等级返回单目标配额。"""
        if threat_level >= 5:
            return 999999  # 极危：不限制
        elif threat_level >= 4:
            return self._max_per_target_high
        elif threat_level >= 3:
            return self._max_per_target_med
        else:
            return self._max_per_target_low

    def try_acquire(self, target_id: str, threat_level: int = 3, urgent: bool = False) -> bool:
        """尝试获取调用许可。

        Args:
            target_id: 目标 ID。
            threat_level: 目标当前威胁等级 (1-5)。
            urgent: 是否为紧急调用（指挥员手动触发）。

        Returns:
            True 表示允许调用，False 表示被限流。
        """
        with self._lock:
            now = time.monotonic()

            # 紧急通道：threat_level=5 或 urgent=True → 直接放行
            if urgent or threat_level >= 5:
                self._global_timestamps.append(now)
                if target_id not in self._target_timestamps:
                    self._target_timestamps[target_id] = []
                self._target_timestamps[target_id].append(now)
                self._last_call_time = now
                return True

            is_high_threat = threat_level >= 4
            effective_cooldown = (
                self._cooldown_high_threat_ms / 1000.0
                if is_high_threat
                else self._cooldown_seconds
            )

            # 1. 冷却时间检查
            if self._last_call_time > 0 and now - self._last_call_time < effective_cooldown:
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
            max_per_target = self._get_max_per_target(threat_level)
            if len(self._target_timestamps[target_id]) >= max_per_target:
                return False

            # 4. 通过所有检查
            self._global_timestamps.append(now)
            self._target_timestamps[target_id].append(now)
            self._last_call_time = now
            return True

    def get_status(self) -> dict:
        """返回限流器当前状态。"""
        with self._lock:
            now = time.monotonic()
            self._global_timestamps = self._clean_old_timestamps(self._global_timestamps)

            target_status = {}
            for tid, tss in list(self._target_timestamps.items()):
                cleaned = self._clean_old_timestamps(tss)
                if cleaned:
                    target_status[tid] = {
                        "count_last_minute": len(cleaned),
                        "limit": "unlimited",
                    }
                else:
                    del self._target_timestamps[tid]

            seconds_since_last = (
                round(now - self._last_call_time, 2) if self._last_call_time > 0 else 999.0
            )

            return {
                "global_calls_last_minute": len(self._global_timestamps),
                "global_limit": self._max_calls_per_minute,
                "cooldown_seconds": self._cooldown_seconds,
                "seconds_since_last_call": seconds_since_last,
                "per_target_status": target_status,
            }

    def reset(self) -> None:
        """重置限流器状态（用于测试）。"""
        with self._lock:
            self._global_timestamps.clear()
            self._target_timestamps.clear()
            self._last_call_time = 0.0
