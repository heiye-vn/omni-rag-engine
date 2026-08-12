# ==============================================================================
# omni-rag-engine 官方 Dockerfile
# 基于 Python 3.11-slim 构建高性能全模态 RAG 微服务
# ==============================================================================

FROM python:3.11-slim

# 1. 设置环境变量
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100

# 2. 安装基础系统依赖 (ffmpeg 用于音视频处理, libgl1/libglib2.0 用于 OpenCV/PaddleOCR 图像处理)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    ffmpeg \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# 3. 安装高性能包管理器 uv
RUN pip install --no-cache-dir uv

# 4. 工作目录配置
WORKDIR /app

# 5. 复制依赖描述文件并预先构建环境
COPY pyproject.toml uv.lock ./
COPY wheels ./wheels

# 使用 uv 安装项目依赖 (无缓存快速构建)
RUN uv sync --frozen --no-dev || uv pip install -e . --system

# 6. 复制项目代码
COPY app ./app
COPY .env.example ./.env.example

# 7. 暴露端口
EXPOSE 8000

# 8. 健康检查
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:8000/ || exit 1

# 9. 启动命令 (FastAPI 微服务)
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
