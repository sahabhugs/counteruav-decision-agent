# ============================================================
# LLM Agent Dockerfile - FastAPI + llama.cpp
# ============================================================

FROM python:3.10-slim

LABEL maintainer="CounterUAV Team"
LABEL description="反无人机LLM辅助决策Agent (Qwen3-8B + ReAct)"

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    curl \
    git \
    tzdata \
    && cp /usr/share/zoneinfo/Asia/Shanghai /etc/localtime \
    && echo "Asia/Shanghai" > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 安装Python依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir \
       sentencepiece \
       transformers \
       torch --index-url https://download.pytorch.org/whl/cpu

# 复制源码
COPY src/ ./src/
COPY models/ ./models/

# 创建非root用户
RUN groupadd -r cuav && useradd -r -g cuav cuav && \
    mkdir -p /app/logs /app/knowledge-base /app/models && \
    chown -R cuav:cuav /app

USER cuav

# 环境变量
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src
ENV MODEL_PATH=/app/models/qwen3-8b-q4_k_m.gguf
ENV EMBEDDING_MODEL=/app/models/bge-small-zh

# 健康检查
HEALTHCHECK --interval=60s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8001/api/llm/health || exit 1

EXPOSE 8001

# 启动
CMD ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "1"]
