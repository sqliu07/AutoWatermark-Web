# 基础镜像
FROM python:3.10-slim

# 设置时区
ENV TZ=Asia/Shanghai

# --- 优化点 1: 使用多阶段构建拷贝 ffmpeg (静态编译版仅 ~40-70MB) ---
# mwader/static-ffmpeg 是一个非常流行的精简版 ffmpeg 镜像
COPY --from=mwader/static-ffmpeg:6.0 /ffmpeg /usr/local/bin/
COPY --from=mwader/static-ffmpeg:6.0 /ffprobe /usr/local/bin/

# --- 优化点 2: 移除 ffmpeg 和 curl 的 apt 安装 ---
# curl 在你的 process.py 中被用于 ntfy 通知，建议改用 python requests 库 (见下文建议)，
# 这样就可以把 curl 也去掉。如果暂时不想改代码，可以保留 curl。
# 必须保留 perl-base 用于 ExifTool
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl tzdata perl-base && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 拷贝项目文件 (配合 .dockerignore 过滤垃圾文件)
COPY . /app

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt

# 清理 ExifTool 的垃圾文件 (保留你原有的逻辑)
RUN sed -i 's/\r$//' /app/3rdparty/exiftool/exiftool && \
    rm -rf /app/3rdparty/exiftool/{Changes,MANIFEST,META.json,META.yml,Makefile.PL,README,build_geolocation,build_tag_lookup,html,t,validate,windows_exiftool,windows_exiftool.txt}

ENV FLASK_ENV=production
EXPOSE 5000

CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "app:app"]