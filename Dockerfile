# 基础镜像
FROM python:3.10-slim

# 设置时区（可通过环境变量覆盖）
ENV TZ=Asia/Shanghai

# 安装系统依赖和 Python 依赖
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libglib2.0-0 libsm6 libxext6 libxrender-dev curl tzdata && \
    rm -rf /var/lib/apt/lists/*

# 设置工作目录
WORKDIR /app

# 拷贝项目文件
COPY . /app

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt

# 默认 Flask 环境为 production
ENV FLASK_ENV=production

# 暴露端口
EXPOSE 5000

# 启动 Gunicorn 作为 WSGI 服务器
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "app:app"]
