"""
反无人机 LLM Agent 服务入口 - FastAPI 应用
提供基于 ReAct 模式的深度推理决策服务。
"""

from __future__ import annotations

import logging
import os
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# 确保 src 目录在 sys.path 中
_src_dir = Path(__file__).resolve().parent
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

from config import config as app_config
from rate_limiter import RateLimiter
from react_engine import ReActEngine
from tools.registry import ToolRegistry
from tools.search_rules import search_rules
from tools.query_kb import query_kb
from tools.run_topsis import run_topsis
from tools.check_devices import check_devices
from tools.predict_trajectory import predict_trajectory
from tools.simulate_action import simulate_action
from tools.retrieve_cases import retrieve_cases
from output_validator import OutputValidator


# ==================== 日志配置 ====================

def setup_logging() -> None:
    """配置日志系统（中文消息）。"""
    log_format = "%(asctime)s [%(levelname)s] %(name)s - %(message)s"
    logging.basicConfig(
        level=getattr(logging, app_config.LOG_LEVEL, logging.INFO),
        format=log_format,
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # 降低第三方库日志级别
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("faiss").setLevel(logging.WARNING)
    logging.getLogger("sentence_transformers").setLevel(logging.WARNING)


setup_logging()
logger = logging.getLogger("llm-agent")


# ==================== 全局实例 ====================

llm_instance: Any = None
react_engine: Optional[ReActEngine] = None
tools_registry: Optional[ToolRegistry] = None
rate_limiter: Optional[RateLimiter] = None
_startup_time: float = 0.0


# ==================== Pydantic 请求/响应模型 ====================

class SituationData(BaseModel):
    """态势数据模型。"""
    task_id: str = Field(..., description="任务ID")
    target_id: Optional[str] = Field(default=None, description="目标ID")
    type: Optional[str] = Field(default=None, description="目标类型")
    model: Optional[str] = Field(default=None, description="无人机型号")
    lat: Optional[float] = Field(default=None, description="纬度")
    lon: Optional[float] = Field(default=None, description="经度")
    alt: Optional[float] = Field(default=None, description="高度(米)")
    speed_ms: Optional[float] = Field(default=None, description="速度(m/s)")
    heading: Optional[float] = Field(default=None, description="航向(度)")
    distance_m: Optional[float] = Field(default=None, description="距离(米)")
    cpa_m: Optional[float] = Field(default=None, description="最近接近点距离(米)")
    signal_features: Optional[str] = Field(default=None, description="信号特征")
    snr_db: Optional[float] = Field(default=None, description="信噪比(dB)")
    behavior: Optional[str] = Field(default=None, description="行为描述")
    threat_hint: Optional[str] = Field(default=None, description="初步威胁判断")
    # 扩展字段
    environment: Optional[dict] = Field(default=None, description="环境信息")
    constraints: Optional[dict] = Field(default=None, description="约束条件")
    targets: Optional[List[dict]] = Field(default=None, description="多目标信息")
    devices: Optional[List[dict]] = Field(default=None, description="设备状态")

    class Config:
        extra = "allow"


class DecideRequest(BaseModel):
    """决策请求模型。"""
    task_id: str = Field(..., description="任务ID（唯一标识）")
    trigger_reason: str = Field(..., description="触发原因")
    trigger_detail: Optional[str] = Field(default="", description="触发详情")
    situation: SituationData = Field(..., description="态势信息（含 precomputed 可选字段）")
    task_description: str = Field(..., description="任务描述")
    threat_level: int = Field(default=3, ge=1, le=5, description="初始威胁等级 (1-5)，用于限流分级")
    urgent: bool = Field(default=False, description="是否紧急调用（指挥员手动触发）")


class DecideResponse(BaseModel):
    """决策响应模型。"""
    task_id: str = Field(..., description="任务ID")
    status: str = Field(..., description="状态：success/warning/error")
    decision: Optional[dict] = Field(default=None, description="决策结果")
    metadata: Optional[dict] = Field(default=None, description="元数据（推理轮次、耗时等）")
    errors: Optional[List[str]] = Field(default=None, description="错误信息列表")


class HealthResponse(BaseModel):
    """健康检查响应模型。"""
    status: str = Field(..., description="服务状态：healthy/degraded/unhealthy")
    model_loaded: bool = Field(..., description="LLM 模型是否已加载")
    tools_count: int = Field(..., description="已注册工具数量")
    memory_usage_mb: Optional[float] = Field(default=None, description="内存占用(MB)")
    uptime_seconds: float = Field(..., description="服务运行时间(秒)")


class RateLimiterStatusResponse(BaseModel):
    """限流器状态响应模型。"""
    global_calls_last_minute: int = Field(..., description="过去1分钟全局调用次数")
    global_limit: int = Field(..., description="全局限制")
    cooldown_seconds: int = Field(..., description="冷却时间(秒)")
    seconds_since_last_call: float = Field(..., description="距离上次调用秒数")
    per_target_status: dict = Field(default_factory=dict, description="单目标状态")


class ErrorResponse(BaseModel):
    """错误响应模型。"""
    detail: str = Field(..., description="错误详情")
    error_code: str = Field(default="UNKNOWN", description="错误码")


# ==================== 生命周期管理 ====================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理：启动时加载模型和工具，关闭时清理资源。"""
    global llm_instance, react_engine, tools_registry, rate_limiter, _startup_time

    logger.info("=" * 60)
    logger.info("反无人机 LLM Agent 辅助决策服务启动中...")
    logger.info("=" * 60)

    # 1. 初始化限流器（威胁等级感知）
    rate_limiter = RateLimiter(
        max_calls_per_minute=app_config.MAX_CALLS_PER_MINUTE,
        cooldown_seconds=app_config.COOLDOWN_SECONDS,
        max_per_target_high=6,
        max_per_target_med=3,
        max_per_target_low=2,
        cooldown_high_threat_ms=1.0,
    )
    logger.info("限流器初始化完成（威胁等级感知 + 紧急通道）")

    # 2. 注册工具（6 个实时 Tool + retrieve_cases）
    tools_registry = ToolRegistry()
    tools_registry.register(
        "search_rules",
        search_rules,
        "搜索反无人机处置规则数据库。参数: query(必需,搜索关键词), layers(可选,规则层级列表如[1,2])"
    )
    tools_registry.register(
        "query_kb",
        query_kb,
        "查询知识库。参数: entity_type(必需,实体类型:drone/scenario/terrain/em_environment), "
        "query(必需,查询文本), top_k(可选,返回数量默认5)"
    )
    tools_registry.register(
        "run_topsis",
        run_topsis,
        "执行TOPSIS多属性威胁评估计算（可选假设分析模式，默认结果已预注入precomputed字段）。"
        "参数: target_id(必需), exclude_indicators(可选,排除的指标列表), custom_weights(可选,自定义权重)"
    )
    tools_registry.register(
        "check_devices",
        check_devices,
        "查询反无人机设备当前状态和部署信息。参数: device_type(可选,如'干扰器'/'激光'), status(可选,如'在线')"
    )
    tools_registry.register(
        "predict_trajectory",
        predict_trajectory,
        "预测目标轨迹。基于当前运动状态做线性外推，计算CPA和禁飞区入侵时间。"
        "参数: target_id(必需), horizon_s(可选,预测时间范围默认30s)"
    )
    tools_registry.register(
        "simulate_action",
        simulate_action,
        "预测反制行动对目标的效果和风险。参数: target_id(必需), action_type(必需), "
        "device_id(可选,不指定则自动匹配)"
    )
    tools_registry.register(
        "retrieve_cases",
        retrieve_cases,
        "检索与当前态势最相似的历史成功案例（动态Few-shot）。参数: situation_desc(必需), top_k(可选,默认3)"
    )
    # 注: propose_rule 已从实时 Tool 列表移除，改为战后异步批处理
    logger.info(f"已注册 {tools_registry.get_tool_count()} 个工具")

    # 3. 加载 LLM 模型
    try:
        # ============================================================
        # 清理所有 CUDA/GPU 相关环境变量（防止 llama-cpp-python 加载 DLL 失败）
        #
        # 背景：系统环境变量 CUDA_PATH 被错误设置为 PyCharm 路径，
        # 导致 llama-cpp-python 的 _ctypes_extensions.py 在导入时尝试
        # os.add_dll_directory() 一个不存在的路径而崩溃。
        #
        # 此外，如果 llama-cpp-python 是 CUDA 编译版本，在纯 CPU 机器上
        # llama_backend_init() 会因找不到 CUDA 运行时 DLL 而触发
        # "access violation reading 0x0000000000000000" 空指针崩溃。
        #
        # 解决方案：
        #   1. 清理所有 CUDA 相关环境变量
        #   2. 清理 PATH 中的 CUDA 路径
        #   3. 使用 CPU-only 版本的 llama-cpp-python（通过 conda 安装：
        #      conda install -c conda-forge llama-cpp-python）
        # ============================================================
        _cleaned_cuda_vars = []
        # 清理所有 CUDA/NVIDIA 相关环境变量（包括版本化变体如 CUDA_PATH_V11_0）
        for _var in list(os.environ.keys()):
            _upper = _var.upper()
            if any(kw in _upper for kw in (
                "CUDA_PATH", "CUDA_HOME", "CUDA_TOOLKIT", "CUDA_MODULE",
                "CUDA_CACHE", "CUDA_VISIBLE", "CUDA_VERSION",
                "NVCC", "NVIDIA_DRIVER", "NVTOOLSEXT",
                "NVCUDASAMPLES", "GPU_", "GGML_CUDA",
            )):
                _cleaned_cuda_vars.append(f"{_var}={os.environ.pop(_var)}")

        # 清理 PATH 中可能的 CUDA/NVIDIA 路径
        if "PATH" in os.environ:
            _old_path = os.environ["PATH"]
            _new_entries = []
            for _entry in _old_path.split(os.pathsep):
                _lower = _entry.lower()
                if any(kw in _lower for kw in (
                    "cuda", "nvcc", "cublas", "cudnn",
                    "nvidia corp", "nvidia gpu", "libnvvp", "nsight",
                )):
                    _cleaned_cuda_vars.append(f"PATH entry: {_entry}")
                else:
                    _new_entries.append(_entry)
            if len(_new_entries) != len(_old_path.split(os.pathsep)):
                os.environ["PATH"] = os.pathsep.join(_new_entries)

        if _cleaned_cuda_vars:
            logger.info(
                f"已清理 {len(_cleaned_cuda_vars)} 个 CUDA 相关环境变量/路径条目，"
                f"使用 CPU 推理模式"
            )
            logger.debug(f"清理详情: {_cleaned_cuda_vars}")

        from llama_cpp import Llama

        model_path = app_config.MODEL_PATH
        if not os.path.isabs(model_path):
            base_dir = Path(__file__).resolve().parent.parent
            model_path = str(base_dir / model_path)

        if not os.path.exists(model_path):
            logger.warning(
                f"LLM 模型文件不存在: {model_path}。"
                f"服务将以降级模式运行（仅健康检查和限流状态可用）。"
            )
            llm_instance = None
        else:
            logger.info(f"正在加载 LLM 模型: {model_path}")
            llm_instance = Llama(
                model_path=model_path,
                n_ctx=app_config.N_CTX,
                n_threads=app_config.N_THREADS,
                verbose=False,
            )
            logger.info(f"LLM 模型加载成功 (n_ctx={app_config.N_CTX}, n_threads={app_config.N_THREADS})")

    except ImportError:
        logger.warning("llama-cpp-python 未安装，服务将以降级模式运行")
        llm_instance = None
    except OSError as e:
        # 捕获 "access violation reading 0x0000000000000000" 等 C 层崩溃
        if "access violation" in str(e).lower() or "0x0000000000000000" in str(e):
            logger.error(
                f"LLM 模型加载失败（C 层空指针崩溃）: {e}\n"
                f"根本原因: llama-cpp-python 可能是 CUDA 编译版本，但本机没有 NVIDIA GPU。\n"
                f"解决方案: 请使用 conda 安装 CPU 版本:\n"
                f"  conda install -c conda-forge llama-cpp-python\n"
                f"或修复 CUDA_PATH 环境变量后重新安装 CPU-only 版本。"
            )
        else:
            logger.error(f"LLM 模型加载失败（OS 错误）: {e}", exc_info=True)
        llm_instance = None
    except Exception as e:
        logger.error(f"LLM 模型加载失败: {e}", exc_info=True)
        llm_instance = None

    # 4. 初始化 ReAct 引擎
    if llm_instance is not None and tools_registry is not None:
        react_engine = ReActEngine(
            cfg=app_config,
            tools_registry=tools_registry,
            llm_instance=llm_instance,
        )
        logger.info("ReAct 引擎初始化完成")
    else:
        react_engine = None
        logger.warning("ReAct 引擎未初始化（LLM 模型不可用或工具注册未完成）")

    _startup_time = time.monotonic()
    logger.info("=" * 60)
    logger.info(f"LLM Agent 服务启动完成，监听 {app_config.SERVER_HOST}:{app_config.SERVER_PORT}")
    logger.info("=" * 60)

    yield  # 应用运行中...

    # ---- 关闭阶段 ----
    logger.info("LLM Agent 服务正在关闭...")
    if llm_instance is not None:
        try:
            del llm_instance
            logger.info("LLM 模型资源已释放")
        except Exception as e:
            logger.warning(f"LLM 模型资源释放异常: {e}")
    logger.info("LLM Agent 服务已关闭")


# ==================== FastAPI 应用实例 ====================

app = FastAPI(
    title="反无人机 LLM Agent 辅助决策服务",
    description="基于 ReAct 推理模式的智能辅助决策系统，集成 Qwen3-8B 本地大模型进行深度态势分析",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==================== API 端点 ====================

@app.get(
    "/api/llm/health",
    response_model=HealthResponse,
    summary="健康检查",
    description="检查 LLM Agent 服务状态，包括模型加载情况和内存使用。",
)
async def health_check():
    """健康检查端点。"""
    try:
        import psutil
        process = psutil.Process()
        memory_mb = process.memory_info().rss / (1024 * 1024)
    except ImportError:
        memory_mb = -1.0

    uptime = time.monotonic() - _startup_time if _startup_time > 0 else 0.0

    return HealthResponse(
        status="healthy" if llm_instance is not None else "degraded",
        model_loaded=llm_instance is not None,
        tools_count=tools_registry.get_tool_count() if tools_registry else 0,
        memory_usage_mb=round(memory_mb, 2) if memory_mb >= 0 else None,
        uptime_seconds=round(uptime, 2),
    )


@app.get(
    "/api/llm/status",
    response_model=RateLimiterStatusResponse,
    summary="限流器状态",
    description="查询当前限流器状态，包括全局和单目标的调用频率统计。",
)
async def rate_limiter_status():
    """限流器状态查询端点。"""
    if rate_limiter is None:
        raise HTTPException(status_code=500, detail="限流器未初始化")

    status = rate_limiter.get_status()
    return RateLimiterStatusResponse(**status)


@app.post(
    "/api/llm/decide",
    response_model=DecideResponse,
    summary="LLM 辅助决策",
    description="基于 ReAct 推理引擎对低置信度场景进行深度分析和辅助决策。",
)
async def llm_decide(request: DecideRequest):
    """主决策端点：接收态势信息，执行 ReAct 推理，返回结构化决策。

    Args:
        request: 决策请求，包含 task_id、trigger_reason、situation、task_description。

    Returns:
        结构化决策响应。

    Raises:
        HTTPException: 503 模型不可用 / 429 限流 / 500 内部异常。
    """
    task_id = request.task_id
    logger.info(f"收到决策请求: task_id={task_id}, reason={request.trigger_reason}")

    # 1. 检查引擎是否就绪
    if react_engine is None or llm_instance is None:
        logger.error("LLM 模型未加载，无法处理决策请求")
        raise HTTPException(
            status_code=503,
            detail="LLM 模型未加载或不可用，服务当前处于降级模式。请检查模型文件是否存在。",
        )

    # 2. 检查限流器
    if rate_limiter is None:
        logger.error("限流器未初始化")
        raise HTTPException(
            status_code=500,
            detail="限流器未初始化，服务配置异常",
        )

    target_id = request.situation.target_id or task_id
    if not rate_limiter.try_acquire(target_id, request.threat_level, request.urgent):
        logger.warning(f"限流拒绝: task_id={task_id}, target_id={target_id}, threat_level={request.threat_level}")
        raise HTTPException(
            status_code=429,
            detail=f"请求频率超限，请稍后重试。全局限制: {app_config.MAX_CALLS_PER_MINUTE}次/分钟，"
                   f"冷却时间: {app_config.COOLDOWN_SECONDS}秒。紧急请求请设置 urgent=true",
        )

    # 3. 构建态势字典
    situation_dict = request.situation.model_dump(exclude_none=False)

    # 3a. 注入规则引擎的威胁等级和触发原因（Agent 需要感知上报上下文）
    if request.trigger_reason:
        situation_dict["_escalation_trigger_reason"] = request.trigger_reason
    if request.trigger_detail:
        situation_dict["_escalation_trigger_detail"] = request.trigger_detail
    if request.threat_level:
        # 将规则引擎的初步威胁等级注入态势（如果态势中未设置）
        if "threat_level" not in situation_dict:
            situation_dict["rule_engine_threat_level"] = request.threat_level

    # 3b. 构建增强任务描述（含上报上下文，让Agent知道被调用的原因）
    enhanced_task = request.task_description
    if request.trigger_reason or request.trigger_detail:
        escalation_context = []
        if request.trigger_reason:
            escalation_context.append(f"上报原因: {request.trigger_reason}")
        if request.trigger_detail:
            escalation_context.append(f"详情: {request.trigger_detail}")
        if request.threat_level:
            escalation_context.append(
                f"规则引擎初步威胁等级: {request.threat_level}/5"
            )
        enhanced_task = (
            f"{request.task_description}\n\n"
            f"【规则引擎上报上下文】\n"
            + "\n".join(escalation_context)
            + "\n请进行深度分析，尝试提供更高置信度的威胁评估和决策建议。"
        )
        logger.info(
            f"任务描述已增强，包含上报上下文: task_id={task_id}"
        )

    # 4. 执行 ReAct 推理
    start_time = time.monotonic()
    try:
        decision = react_engine.run(
            task=enhanced_task,
            situation=situation_dict,
        )
        elapsed = time.monotonic() - start_time

        # 校验输出
        validator = OutputValidator()
        valid, errors = validator.validate(decision)

        metadata = {
            "elapsed_seconds": round(elapsed, 3),
            "validation_passed": valid,
            "model": app_config.MODEL_PATH,
            "inference_rounds": len(decision.get("reasoning_chain", [])),
            "trigger_reason": request.trigger_reason,
            "rule_engine_threat_level": request.threat_level,
            "agent_confidence": (
                decision.get("threat_assessment", {}).get("confidence", 0.0)
            ),
            "confidence_threshold": app_config.CONFIDENCE_THRESHOLD,
            "confidence_improved": (
                decision.get("threat_assessment", {}).get("confidence", 0.0)
                >= app_config.CONFIDENCE_THRESHOLD
            ),
        }

        logger.info(
            f"决策完成: task_id={task_id}, "
            f"threat_level={decision.get('threat_assessment', {}).get('threat_level', '?')}, "
            f"valid={valid}, elapsed={elapsed:.2f}s"
        )

        return DecideResponse(
            task_id=task_id,
            status="success" if valid else "warning",
            decision=decision,
            metadata=metadata,
            errors=errors if errors else None,
        )

    except Exception as e:
        elapsed = time.monotonic() - start_time
        logger.error(f"决策推理异常: task_id={task_id}, error={e}", exc_info=True)

        return DecideResponse(
            task_id=task_id,
            status="error",
            decision=None,
            metadata={
                "elapsed_seconds": round(elapsed, 3),
                "error_type": type(e).__name__,
                "trigger_reason": request.trigger_reason,
                "rule_engine_threat_level": request.threat_level,
            },
            errors=[f"推理过程异常: {str(e)}"],
        )


# ==================== 异常处理器 ====================

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc: HTTPException):
    """HTTP 异常处理器（中文错误信息）。"""
    logger.warning(f"HTTP 异常: {exc.status_code} - {exc.detail}")
    return {"detail": str(exc.detail), "error_code": f"HTTP_{exc.status_code}"}


@app.exception_handler(Exception)
async def general_exception_handler(request, exc: Exception):
    """通用异常处理器。"""
    logger.error(f"未捕获异常: {type(exc).__name__}: {exc}", exc_info=True)
    return {
        "detail": f"服务内部异常: {type(exc).__name__}: {str(exc)}",
        "error_code": "INTERNAL_ERROR",
    }


# ==================== 入口 ====================

if __name__ == "__main__":
    import uvicorn

    logger.info(f"启动 LLM Agent 服务: {app_config.SERVER_HOST}:{app_config.SERVER_PORT}")
    uvicorn.run(
        "main:app",
        host=app_config.SERVER_HOST,
        port=app_config.SERVER_PORT,
        reload=False,
        log_level=app_config.LOG_LEVEL.lower(),
    )
