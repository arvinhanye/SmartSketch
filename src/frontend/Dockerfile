# syntax=docker/dockerfile:1
# SmartSketch 前端镜像（K08）：Vite 构建产物由非 root 的 nginx 提供，/api 反向代理到后端。
# 构建上下文必须是仓库根目录：docker build -f src/frontend/Dockerfile .
#
# 前端构建不接受任何密钥：本文件没有 ARG/ENV 形式的构建参数，.dockerignore 排除所有 .env*，
# 只 COPY src/frontend。浏览器以同源相对路径 /api/v1 访问后端（src/frontend/src/api/http.ts）。

ARG NODE_IMAGE=node:24-bookworm-slim
ARG NGINX_IMAGE=nginxinc/nginx-unprivileged:1.27-alpine

FROM ${NODE_IMAGE} AS build
WORKDIR /web
COPY src/frontend/package.json src/frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY src/frontend/ ./
RUN npm run build

FROM ${NGINX_IMAGE}
COPY src/frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /web/dist /usr/share/nginx/html
EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=4 \
    CMD ["wget", "-q", "-O", "/dev/null", "http://127.0.0.1:8080/"]
