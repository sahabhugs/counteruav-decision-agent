@echo off
REM 反无人机 LLM Agent 辅助决策服务 - 启动脚本

REM ============================================================
REM 清除所有 CUDA/NVIDIA/GPU 相关环境变量
REM （防止 llama-cpp-python 尝试加载不存在的 CUDA DLL 而崩溃）
REM ============================================================
set CUDA_PATH=
set CUDA_PATH_V11_0=
set CUDA_PATH_V12_4=
set CUDA_HOME=
set CUDA_TOOLKIT_ROOT_DIR=
set CUDA_MODULE_LOADING=
set CUDA_CACHE_PATH=
set CUDA_VISIBLE_DEVICES=
set NVCC=
set NVIDIA_DRIVER=
set NVCUDASAMPLES_ROOT=
set NVCUDASAMPLES11_0_ROOT=
set NVTOOLSEXT_PATH=
set GGML_CUDA_NO_PIN_MEM=

cd /d %~dp0

echo.
echo ============================================
echo   LLM Agent 服务启动中...
echo   推理模式: CPU
echo   监听端口: 8001
echo ============================================
echo.

REM 使用 Anaconda Python（避免 cmd 中默认 Python 3.10 的 CUDA 版 llama-cpp-python）
F:\Anaconda3\python.exe src/main.py

pause
