# syntax=docker/dockerfile:1
# SmartSketch 后端镜像（K08）：API 与 worker 共用本镜像，按命令区分。
# 构建上下文必须是仓库根目录：docker build -f src/backend/Dockerfile .
#
# 目录布局照搬仓库，因为运行时按相对仓库根的路径加载三类签入文件：
#   /app/src/backend/migrations                     SQLite / Neo4j 迁移（repositories/sqlite.py、graph_migrations.py）
#   /app/src/contracts/v1/generated/python/models.py 生成的契约 DTO（app/schemas/contracts.py，C04 风险项）
#   /app/prompts                                     提示词（services/ai/prompts.py）
# 因此不 pip install 后端包本身（装进 site-packages 会让上述相对路径失效），只装它声明的依赖。
#
# 镜像里没有任何密钥：LLM/Embedding/Neo4j/JWT 等全部在运行时经环境变量注入。

ARG PYTHON_IMAGE=python:3.12-slim-bookworm

FROM ${PYTHON_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app/src/backend \
    API_HOST=0.0.0.0 \
    API_PORT=8000 \
    SQLITE_URL=sqlite:////data/smartsketch.sqlite3 \
    STORAGE_DIR=/data/storage \
    WORKER_HEARTBEAT_FILE=/tmp/smartsketch-worker.heartbeat

WORKDIR /app/src/backend

# 依赖以 pyproject.toml 为唯一来源（只取运行依赖，不装 test extra）。
COPY src/backend/pyproject.toml ./pyproject.toml
RUN python -c "import tomllib; print('\n'.join(tomllib.load(open('pyproject.toml', 'rb'))['project']['dependencies']))" > /tmp/requirements.txt \
    && pip install -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt

COPY src/backend/app ./app
COPY src/backend/migrations ./migrations
COPY src/contracts/v1/generated/python /app/src/contracts/v1/generated/python
COPY prompts /app/prompts

# 非 root 运行；/data 放 SQLite 与上传文件，由 compose 挂卷（API 与 worker 必须同机同卷，§8.1）。
RUN useradd --system --uid 10001 --home-dir /nonexistent --shell /usr/sbin/nologin smartsketch \
    && mkdir -p /data/storage \
    && chown -R smartsketch /data
USER smartsketch
VOLUME ["/data"]

EXPOSE 8000

# API 健康检查：匿名 GET /health（B05）。worker 容器在 compose 里改用 `python -m app.workers --health`。
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=4 \
    CMD ["python", "-c", "import os, sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:%s/health' % os.environ.get('API_PORT', '8000'), timeout=4).status == 200 else 1)"]

CMD ["python", "-m", "app"]
