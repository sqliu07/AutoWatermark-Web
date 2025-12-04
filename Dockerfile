# 基础镜像
FROM python:3.10-slim

# 设置时区
ENV TZ=Asia/Shanghai

COPY --from=mwader/static-ffmpeg:6.0 /ffmpeg /usr/local/bin/
COPY --from=mwader/static-ffmpeg:6.0 /ffprobe /usr/local/bin/

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl tzdata perl-base && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 拷贝项目文件
COPY . /app

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt

# 清理 ExifTool 的垃圾文件
RUN sed -i 's/\r$//' /app/3rdparty/exiftool/exiftool && \
    rm -rf /app/3rdparty/exiftool/{Changes,MANIFEST,META.json,META.yml,Makefile.PL,README,build_geolocation,build_tag_lookup,html,t,validate,windows_exiftool,windows_exiftool.txt}

ENV FLASK_ENV=production
EXPOSE 5000

CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "app:app"]