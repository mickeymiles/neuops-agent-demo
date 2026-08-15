# ═══════════════════════════════════════════
# NeuOps Agent 运维监控平台 容器化
# network_mode: host 以访问 127.0.0.1:9006 等本机服务
# ═══════════════════════════════════════════
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=9007

WORKDIR /srv/neuops

# 系统依赖（fastembed/chromadb 需要编译工具与底层库）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ build-essential \
    libffi-dev libssl-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 运行时数据卷（SQLite / chroma / uploads）
RUN mkdir -p /srv/neuops/data /srv/neuops/chroma_data /srv/neuops/uploads
VOLUME ["/srv/neuops/data", "/srv/neuops/chroma_data", "/srv/neuops/uploads"]

EXPOSE 9007

# 启动：统一探针 + 自愈引擎在应用 lifespan 中自动启动
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9007"]
