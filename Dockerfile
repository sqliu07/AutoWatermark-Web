# ============ 第一阶段：构建 Vue 前端 ============
FROM node:18-alpine AS frontend-build

WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --production=false

COPY frontend/ ./
RUN npm run build

# ============ 第二阶段：Python 应用 ============
FROM python:3.10-slim

ENV TZ=Asia/Shanghai \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# 复制 ffmpeg 二进制文件
COPY --from=mwader/static-ffmpeg:6.0 /ffmpeg /usr/local/bin/
COPY --from=mwader/static-ffmpeg:6.0 /ffprobe /usr/local/bin/

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        tzdata perl-base && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 安装 Python 依赖
COPY requirements-deploy.txt /app/requirements-deploy.txt
RUN pip install --no-cache-dir -r /app/requirements-deploy.txt

# 拷贝项目文件（排除 frontend/ 源码）
COPY . /app

# 从前端构建阶段复制产物
COPY --from=frontend-build /static/dist /app/static/dist

# 清理 ExifTool 的垃圾文件
RUN sed -i 's/\r$//' /app/3rdparty/exiftool/exiftool && \
    rm -rf /app/3rdparty/exiftool/{Changes,MANIFEST,META.json,META.yml,Makefile.PL,README,build_geolocation,build_tag_lookup,html,t,validate,windows_exiftool,windows_exiftool.txt}

RUN useradd -r -s /usr/sbin/nologin appuser && \
    mkdir -p /app/upload /app/logs && \
    chown -R appuser:appuser /app

USER appuser

ENV FLASK_ENV=production
EXPOSE 5000

CMD ["gunicorn", "-w", "1", "-b", "0.0.0.0:5000", "app:app"]
