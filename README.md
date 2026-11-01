# AutoWatermark Web

AutoWatermark Web 是一个面向摄影照片的水印相框生成工具。它读取照片 EXIF 信息，识别相机/手机品牌和拍摄参数，并输出带品牌 Logo、参数信息和可配置版式的成片。

项目包含 Flask 后端、Vue 3 前端、后台任务队列、Motion Photo/Ultra HDR 处理、临时文件清理和下载链接签名机制，适合自托管为个人或小团队的照片处理服务。

## 功能概览

- EXIF 自动识别：读取厂商、机型、焦距、光圈、快门、ISO 等信息。
- 品牌 Logo 匹配：内置 Sony、Nikon、Canon、Fujifilm、Leica、Hasselblad、Olympus、Panasonic、Pentax、Xiaomi、OPPO、Apple、Huawei/XMAGE 等 Logo。
- 多种水印样式：拍立得、经典双行、居中极简、毛玻璃、胶片留白，样式由 `config/watermark_styles.toml` 驱动。
- 批量处理：多图上传、任务进度、失败任务重试、ZIP 打包下载。
- Motion Photo：支持提取动态照片中的视频段，并在预览中展示。
- Ultra HDR：支持检测并按用户选择保留或剥离 HDR/动态照片能力。
- 隐私保护：下载链接签名、阅后即焚、定时清理过期上传文件和临时 ZIP。
- 安全边界：上传路径约束、文件名清洗、下载 token、基础安全响应头。
- 中英双语：前端支持简体中文和英文切换。

## 快速启动

### Docker

Docker 镜像会构建 Vue 前端，并把静态产物打包到 Flask 应用中。构建前必须初始化 ExifTool 子模块（本地运行也需要）：

```bash
git submodule update --init --recursive
```

镜像构建不会带入 `.env*`、日志、上传文件或本地工作状态；下载签名密钥只在运行时注入。

```bash
docker build -t autowatermark-web .

export DOWNLOAD_TOKEN_SECRET="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"

docker run -d \
  --name autowatermark-web \
  -p 127.0.0.1:5000:5000 \
  --memory=2g --cpus=2 --pids-limit=128 \
  --cap-drop=ALL --security-opt=no-new-privileges:true \
  -e DOWNLOAD_TOKEN_SECRET \
  -e GUNICORN_WORKERS=1 \
  -e GUNICORN_BIND=0.0.0.0:5000 \
  -e UPLOAD_FOLDER=/app/upload \
  -v autowatermark-upload:/app/upload \
  -v autowatermark-logs:/app/logs \
  autowatermark-web
```

访问 `http://localhost:5000`。公网访问应由 HTTPS 反向代理转发，容器端口只绑定本机。内存、CPU 配额可按服务器容量和实际照片大小调整；原生解码器仍需要操作系统层的资源隔离。

生产部署必须保持 `GUNICORN_WORKERS=1`，使用项目的 `gunicorn.conf.py`，且不能启用 `--preload`。后台执行器和限速由单个进程管理；多 worker 或共享上传目录的多实例部署不受支持。Gunicorn 配置会拒绝多 worker 和 preload；由服务器负责停止接收请求，退出时再释放应用资源。

### 本地运行

前置依赖：

- Python 3.11+（Docker 使用 3.12，Pillow 13 不再支持 Python 3.10）
- Node.js 22+（前端构建需要）
- FFmpeg/ffprobe，用于 Motion Photo 视频处理
- Perl，用于运行内置 ExifTool

一键启动后端：

```bash
./scripts/start.sh
```

脚本会创建 `.venv`、安装 Python 依赖，并在 `.env.local` 中生成 `DOWNLOAD_TOKEN_SECRET`。

手动启动：

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt

export DOWNLOAD_TOKEN_SECRET="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
python3 app.py
```

前端开发：

```bash
cd frontend
npm ci
npm run dev
```

构建前端静态产物：

```bash
cd frontend
npm ci
npm run build
```

构建结果写入 `static/dist/`，Flask 会直接服务这些文件。

## 常用配置

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `DOWNLOAD_TOKEN_SECRET` | 无 | 必填，至少 32 字节，使用随机生成值。用于签名预览、下载、ZIP 和 Motion Video 链接。重启时应复用同一密钥。 |
| `UPLOAD_FOLDER` | `./upload` | 上传文件、处理结果和默认状态数据库目录。 |
| `GUNICORN_WORKERS` | `1` | 必须为 1，不支持多 worker。 |
| `GUNICORN_BIND` | `0.0.0.0:5000` | Gunicorn 监听地址。 |
| `TRUSTED_HOSTS` | 不限制 | 公网部署时设置为域名白名单，多个域名用逗号分隔，例如 `photos.example.com`；不带协议和路径。 |
| `TRUSTED_PROXY_CIDRS` | 空 | 仅信任指定代理 IP/CIDR 传入的一跳 `X-Forwarded-For`、`X-Forwarded-Proto`。不信任转发的 Host。 |
| `FLASK_RUN_HOST` | `127.0.0.1` | `scripts/start.sh` 本地启动地址。 |
| `FLASK_RUN_PORT` | `5000` | `scripts/start.sh` 本地启动端口。 |
| `SKIP_PIP_INSTALL` | `0` | 设为 `1` 可跳过启动脚本中的依赖安装。 |

应用启动时会检查上传目录和状态数据库是否可写；不可写时会回退到系统临时目录并记录 warning。

`scripts/start.sh` 按 requirements 文件内容校验依赖安装标记；依赖清单变化后会重新安装。Python 3.10 的旧虚拟环境应先迁移至 Python 3.11+。手动部署或 Docker 部署需要重新安装依赖或重建镜像，更新源码不会自动更新运行中的服务。

### 公网反向代理

Nginx 与 Gunicorn 直接运行于同一台主机时，可将 Gunicorn 绑定到 `127.0.0.1:5000`，并设置：

```bash
export TRUSTED_HOSTS=photos.example.com
export TRUSTED_PROXY_CIDRS=127.0.0.1/32
```

Nginx 的 HTTPS 站点中使用如下转发配置；TLS 证书和 HTTP 到 HTTPS 的重定向由站点配置提供：

```nginx
location / {
    client_max_body_size 200m;
    client_body_timeout 30s;
    proxy_connect_timeout 5s;
    proxy_read_timeout 60s;
    proxy_pass http://127.0.0.1:5000;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Host "";
    proxy_cache off;
}
```

代理必须覆盖客户端传入的转发头。Docker 场景下应用看到的代理地址可能是网桥网关，应按实际地址设置精确的 `/32` 或 `/128`，而不是直接信任整个公网。未设置可信代理时，应用会忽略转发头，代理后的访客将共享限流额度。还应在入口按连接数、请求速率限制流量；应用内限流无法替代边缘 DDoS 防护。

不要在访问日志中记录签名 URL 的查询参数：Nginx 可使用包含 `$uri`、不包含 `$request`/`$request_uri`/`$args` 的日志格式；Gunicorn 保持默认不记录访问日志，启用时使用 `%(U)s`，避免包含 `%(q)s`。任务 UUID 和签名 URL 都是持有者凭据，应像密码一样保管。

## 处理流程

1. 用户上传图片，后端校验扩展名、JPEG/PNG 真实格式、大小、像素和待处理容量。
2. 后端提取 EXIF、识别品牌和媒体能力。
3. 如果是 Xiaomi 照片，会要求用户选择 Xiaomi 或 Leica Logo。
4. 如果检测到 Motion Photo 或 Ultra HDR，会要求用户选择是否保留对应能力。
5. 按本批次固定的设置串行上传，客户端根据容量等待；确认媒体选项后可继续选择下一张，或应用到剩余照片。
6. 后台生成完整成片、1280 像素预览和 160 像素缩略图，分别提供签名链接。全屏和下载使用完整成片。
7. 失败任务保留原始任务信息，用户可以在前端重试。
8. 清理线程定期删除过期任务、阅后即焚文件、临时 ZIP 和陈旧上传文件。

## 水印样式

样式配置位于 `config/watermark_styles.toml`。当前内置：

| ID | 名称 | 布局 | 说明 |
| --- | --- | --- | --- |
| 1 | 拍立得 | `split_lr` | 大留白相框，底部左右分区。 |
| 2 | 经典双行 | `split_lr` | 低留白，适合横图和快速分享。 |
| 3 | 居中极简 | `center_stack` | Logo 和参数居中堆叠。 |
| 4 | 毛玻璃特效 | `center_stack` | 底部毛玻璃背景，自动适配文字颜色。 |
| 5 | 胶片留白 | `film_frame` | 类胶片边框，强制方形构图。 |

新增样式通常只需要：

1. 复制一个 `[styles.<id>]` 配置块。
2. 修改 `display_code`、`label_zh`、`label_en`、布局和比例参数。
3. 把预览图放到 `static/images/` 并配置 `preview_image`。
4. 重启服务。

常用枚举：

- `layout`: `split_lr`, `center_stack`, `film_frame`
- `background`: `white`, `frosted`
- `padding_x_mode`: `border_left`, `footer_ratio`
- `text_color_mode`: `black`, `auto_contrast`
- `position_mode`: `footer_center`, `bottom_offset`

## API 摘要

主要接口都挂在 `/api` 下：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/api/upload` | 上传图片并创建任务。 |
| `POST` | `/api/upload/confirm_logo` | 提交 Xiaomi/Leica Logo 选择。 |
| `POST` | `/api/upload/confirm_options` | 提交 Motion/HDR 保留选项。 |
| `POST` | `/api/tasks/<task_id>/retry` | 重试失败任务。 |
| `POST` | `/api/tasks/<task_id>/cancel` | 取消仍在等待 Logo/媒体选项的任务并释放上传副本；不打断渲染。 |
| `GET` | `/api/status/<task_id>` | 查询任务状态。 |
| `GET` | `/api/upload/<filename>` | 签名预览文件。 |
| `GET` | `/api/upload/<filename>/video` | 签名获取 Motion Photo 视频段。 |
| `POST` | `/api/download_zip` | 创建批量下载 ZIP。 |
| `GET` | `/api/download/<filename>` | 签名下载文件。 |

## 项目结构

```text
.
├── app.py / app_factory.py       # Flask 入口与应用工厂
├── routes/                       # HTTP 路由
├── services/                     # 任务、状态、上传流程、清理、安全路径等服务
├── imaging/                      # 水印渲染器和图像绘制工具
├── media/                        # Motion Photo、Ultra HDR、视频和 XMP 处理
├── exif/                         # EXIF 读取和品牌归一化
├── frontend/                     # Vue 3 + Vite + Ant Design Vue 前端
├── static/dist/                  # 前端构建产物
├── config/                       # 水印样式和错误消息配置
├── tests/                        # 后端测试和真实图片 fixture
└── 3rdparty/exiftool/            # 内置 ExifTool
```

## 测试与质量检查

后端测试：

```bash
. .venv/bin/activate
python -m pytest -q -o log_cli=false --tb=short
```

语法编译检查：

```bash
python -m compileall -q .
```

前端轮询回归测试与构建：

```bash
node --test frontend/tests/*.test.js
cd frontend
npm ci
npm run build
```

依赖安全检查：

```bash
cd frontend
npm audit --registry=https://registry.npmjs.org/
```

Python 依赖可使用隔离的审计工具检查（不写入项目运行依赖）：

```bash
uv tool run pip-audit -r requirements.txt
uv tool run pip-audit -r requirements-deploy.txt
```

测试素材位于 `tests/fixtures/`：

- `sample_with_exif.jpg`: 常规 EXIF 主流程图片
- `motion_photo.jpg`: Motion Photo 示例
- `ultrahdr.jpg`: Ultra HDR 示例
- `no_exif.jpg`: 缺失 EXIF 的错误分支
- `unsupported_brand.jpg`: 未支持品牌分支

## 安全说明

- 所有下载、预览、ZIP 和 Motion Video 链接都通过 `DOWNLOAD_TOKEN_SECRET` 签名。
- 弱密钥会阻止应用启动；文件下载仅允许图片或本服务生成的 ZIP，禁止读取状态数据库等内部文件。
- 上传前校验 JPEG/PNG 内容；用户图片及 HDR gain map 只进入对应的 Pillow 解码器。
- 视频处理强制 MOV/MP4 解复用器、仅允许本地文件协议，并禁用外部轨道，阻止伪装播放列表触发 SSRF 或读取其他本地资源。
- 上传和任务重试使用 `services/path_safety.py` 限制文件路径必须位于 `UPLOAD_FOLDER` 下。
- 文件名会通过 `werkzeug.utils.secure_filename` 清洗。
- 内部存储使用随机文件名；下载与 ZIP 内使用原文件名加 `_watermark`，支持中文与重名去重，保留实际输出格式。
- 阅后即焚下载由响应结束触发文件清理，并使用持久化删除队列兜底。
- API、签名预览和下载均设置 `Cache-Control: no-store, private`，避免照片、任务结果和签名被共享缓存保留。
- 默认响应头包含 `X-Content-Type-Options`、`X-Frame-Options`、`Referrer-Policy: no-referrer` 和 CSP；HTTPS 响应包含 HSTS。
- 写操作拒绝跨站浏览器请求；JSON 请求体限制为 16 KiB，上传表单最多 16 项、每个普通字段最多 128 KiB。
- 上传接口和 ZIP 接口有限速配置。

本次安全审查的现有修改分析、Dependabot 处理和验证范围见 [SECURITY.md](SECURITY.md)。

性能和体验优化的改动、样本测量及验证记录见 [PERFORMANCE.md](PERFORMANCE.md)。

## 已知约束

- 默认只允许 `png`、`jpg`、`jpeg` 上传。
- 单文件最大请求体为 200 MB。
- 输入图、输出图及受保护的中间画布上限为 40,000,000 像素；输入长边不超过 16,384，长宽比不超过 32。加边框后超过输出限制的图片也会被拒绝。
- ZIP 一次最多接收 50 项，按文件去重；单次总输入不超过 256 MiB，临时 ZIP 总量不超过 1 GiB。
- 状态持久化使用 SQLite，仅支持单进程、单实例部署。
- 后台同时执行 2 个任务；执行及等待总数最多 8 个，累计输入最多 512 MiB。超出容量时拒绝新任务，不无限排队。
- 上传元数据解析串行准入；等待 Logo/HDR 选择的任务也计入新上传的 8 个待处理名额。
- Motion Photo 视频最多 30 秒，输出最多 128 MiB；限制解码、编码线程、帧数和派生画布尺寸，失败时删除不完整视频。
- 前端单任务每 2 秒、批量每任务每 3 秒轮询，遵守 429 的 `Retry-After`；单次状态请求最长 15 秒，轮询总时限为 5 分钟。前端超时不代表后台任务已取消。
- 状态查询断线后可继续查询；只有后台确认失败才重新执行。上传超时为 180 秒；429/503 最多尝试 6 次，忙碌等待窗口为 120 秒，超出后由用户继续。
- 普通预览和缩略图为轻量 SDR JPEG；查看完整画质及 HDR 效果请使用全屏或下载。预览失败或容量不足时回退到完整成片，成片本身不受影响。
- 重新选择照片会停止旧批次的前端请求，并尝试取消已知的等待选择任务，避免继续占用名额；已排队或正在渲染的任务仍正常完成。网络不可用时无法保证取消请求送达，未送达的任务沿用过期回收策略。
- 应用日志同时输出标准输出及日志文件；单个文件最多 10 MiB，保留 3 个轮转备份。
- Motion Photo 和 Ultra HDR 处理依赖真实设备写入的元数据，不同厂商格式可能需要补充兼容。

## 许可证与三方组件

项目许可证见 `LICENSE`。

本项目使用 Phil Harvey 开发的 ExifTool。ExifTool 采用 Artistic License 2.0 与 GPL 双许可发布，本项目按 Artistic License 2.0 使用。

ExifTool 官网：https://exiftool.org/

欢迎通过 Issue 或 PR 补充设备兼容、Logo 映射、水印样式和部署文档。
