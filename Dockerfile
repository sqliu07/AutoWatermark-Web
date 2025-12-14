# 基础镜像
FROM python:3.10-slim

# 设置时区
ENV TZ=Asia/Shanghai

# 复制 ffmpeg 二进制文件
COPY --from=mwader/static-ffmpeg:6.0 /ffmpeg /usr/local/bin/
COPY --from=mwader/static-ffmpeg:6.0 /ffprobe /usr/local/bin/

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl tzdata perl-base \
        nodejs \
        npm && \
    rm -rf /var/lib/apt/lists/*

# 2. 全局安装 JS 混淆工具
RUN npm install -g javascript-obfuscator

WORKDIR /app

# 拷贝项目文件
COPY . /app

# 3. 在构建时执行混淆
RUN javascript-obfuscator ./static/js/script.js \
    --output ./static/js/script.js \
    --compact true \
    --self-defending true \
    --rename-globals true \
    --string-array true \
    --string-array-encoding 'base64'

# 4. 混淆完成后卸载 Node.js 以减小镜像体积
RUN npm uninstall -g javascript-obfuscator && \
    apt-get remove -y nodejs npm && \
    apt-get autoremove -y && \
    apt-get clean

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt

# 清理 ExifTool 的垃圾文件
RUN sed -i 's/\r$//' /app/3rdparty/exiftool/exiftool && \
    rm -rf /app/3rdparty/exiftool/{Changes,MANIFEST,META.json,META.yml,Makefile.PL,README,build_geolocation,build_tag_lookup,html,t,validate,windows_exiftool,windows_exiftool.txt}

ENV FLASK_ENV=production
EXPOSE 5000

CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "app:app"]