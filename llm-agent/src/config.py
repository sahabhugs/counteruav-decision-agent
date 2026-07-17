"""
LLM Agent 配置模块
从环境变量和 .env 文件中加载配置，提供默认值。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# 加载 .env 文件（如果存在）
_env_path = Path(__file__).resolve().parent.parent / ".env"
if _env_path.exists():
    load_dotenv(dotenv_path=_env_path)
else:
    load_dotenv()


def _env_str(key: str, default: str) -> str:
    """读取字符串环境变量，不存在则返回默认值。"""
    return os.environ.get(key, default)


def _env_int(key: str, default: int) -> int:
    """读取整数环境变量，不存在或格式错误则返回默认值。"""
    try:
        return int(os.environ.get(key, default))
    except (TypeError, ValueError):
        return default


def _env_float(key: str, default: float) -> float:
    """读取浮点数环境变量，不存在或格式错误则返回默认值。"""
    try:
        return float(os.environ.get(key, default))
    except (TypeError, ValueError):
        return default


class LLMAgentConfig:
    """LLM Agent 全局配置类，所有配置项支持环境变量覆盖。"""

    # ==================== 模型配置 ====================
    MODEL_PATH: str = _env_str("LLM_MODEL_PATH", "models/qwen3-8b-q4_k_m.gguf")
    EMBEDDING_MODEL: str = _env_str("LLM_EMBEDDING_MODEL", "models/bge-small-zh")

    # ==================== 推理参数 ====================
    N_CTX: int = _env_int("LLM_N_CTX", 8192)
    N_THREADS: int = _env_int("LLM_N_THREADS", 8)
    TEMPERATURE: float = _env_float("LLM_TEMPERATURE", 0.1)
    MAX_TOKENS: int = _env_int("LLM_MAX_TOKENS", 1024)

    # ==================== ReAct 循环控制 ====================
    MAX_ROUNDS: int = _env_int("LLM_MAX_ROUNDS", 5)
    TIMEOUT_SECONDS: float = _env_float("LLM_TIMEOUT_SECONDS", 10.0)

    # ==================== 外部服务 ====================
    RULE_ENGINE_URL: str = _env_str("LLM_RULE_ENGINE_URL", "http://localhost:8080")

    # ==================== 决策阈值 ====================
    CONFIDENCE_THRESHOLD: float = _env_float("LLM_CONFIDENCE_THRESHOLD", 0.80)

    # ==================== 限流配置 ====================
    MAX_CALLS_PER_MINUTE: int = _env_int("LLM_MAX_CALLS_PER_MINUTE", 10)
    COOLDOWN_SECONDS: int = _env_int("LLM_COOLDOWN_SECONDS", 5)

    # ==================== 服务配置 ====================
    SERVER_HOST: str = _env_str("LLM_SERVER_HOST", "0.0.0.0")
    SERVER_PORT: int = _env_int("LLM_SERVER_PORT", 8001)

    # ==================== 知识库路径 ====================
    KB_INDEX_DIR: str = _env_str("LLM_KB_INDEX_DIR", "data/kb_index")
    KB_JSON_DIR: str = _env_str("LLM_KB_JSON_DIR", "data/kb_json")

    # ==================== 日志配置 ====================
    LOG_LEVEL: str = _env_str("LLM_LOG_LEVEL", "INFO")

    @classmethod
    def as_dict(cls) -> dict:
        """返回所有配置项的字典表示（不含敏感信息）。"""
        return {
            "model_path": cls.MODEL_PATH,
            "embedding_model": cls.EMBEDDING_MODEL,
            "n_ctx": cls.N_CTX,
            "n_threads": cls.N_THREADS,
            "temperature": cls.TEMPERATURE,
            "max_tokens": cls.MAX_TOKENS,
            "max_rounds": cls.MAX_ROUNDS,
            "timeout_seconds": cls.TIMEOUT_SECONDS,
            "rule_engine_url": cls.RULE_ENGINE_URL,
            "confidence_threshold": cls.CONFIDENCE_THRESHOLD,
            "max_calls_per_minute": cls.MAX_CALLS_PER_MINUTE,
            "cooldown_seconds": cls.COOLDOWN_SECONDS,
            "server_host": cls.SERVER_HOST,
            "server_port": cls.SERVER_PORT,
            "kb_index_dir": cls.KB_INDEX_DIR,
            "kb_json_dir": cls.KB_JSON_DIR,
            "log_level": cls.LOG_LEVEL,
        }


# 全局配置单例
config = LLMAgentConfig()
