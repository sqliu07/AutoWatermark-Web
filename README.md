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

Docker 镜像会构建 Vue 前端，并把静态产物打包到 Flask 应用中。

```bash
docker build -t autowatermark-web .

docker run -d \
  --name autowatermark-web \
  -p 5000:5000 \
  -e DOWNLOAD_TOKEN_SECRET=replace-with-a-strong-secret \
  -e GUNICORN_WORKERS=1 \
  -e GUNICORN_BIND=0.0.0.0:5000 \
  -e UPLOAD_FOLDER=/app/upload \
  -v autowatermark-upload:/app/upload \
  -v autowatermark-logs:/app/logs \
  autowatermark-web
```

访问 `http://localhost:5000`。

生产部署建议保持 `GUNICORN_WORKERS=1`。当前任务状态和限速都在单进程内管理，多 worker 会导致状态不一致。

### 本地运行

前置依赖：

- Python 3.10+
- Node.js 18+
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

export DOWNLOAD_TOKEN_SECRET=replace-with-a-strong-secret
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
| `DOWNLOAD_TOKEN_SECRET` | 无 | 必填。用于签名预览、下载、ZIP 和 Motion Video 链接。 |
| `UPLOAD_FOLDER` | `./upload` | 上传文件、处理结果和默认状态数据库目录。 |
| `GUNICORN_WORKERS` | `1` | 生产模式 worker 数。建议保持 1。 |
| `GUNICORN_BIND` | `0.0.0.0:5000` | Gunicorn 监听地址。 |
| `FLASK_RUN_HOST` | `127.0.0.1` | `scripts/start.sh` 本地启动地址。 |
| `FLASK_RUN_PORT` | `5000` | `scripts/start.sh` 本地启动端口。 |
| `SKIP_PIP_INSTALL` | `0` | 设为 `1` 可跳过启动脚本中的依赖安装。 |

应用启动时会检查上传目录和状态数据库是否可写；不可写时会回退到系统临时目录并记录 warning。

## 处理流程

1. 用户上传图片，后端校验扩展名、大小和像素上限。
2. 后端提取 EXIF、识别品牌和媒体能力。
3. 如果是 Xiaomi 照片，会要求用户选择 Xiaomi 或 Leica Logo。
4. 如果检测到 Motion Photo 或 Ultra HDR，会要求用户选择是否保留对应能力。
5. 后台任务执行水印渲染，前端轮询任务状态并展示进度。
6. 成功后生成签名预览链接、下载链接和可选 Motion Video 链接。
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

前端构建：

```bash
cd frontend
npm ci
npm run build
```

依赖安全检查：

```bash
cd frontend
npm audit --registry=https://registry.npmjs.org/
```

测试素材位于 `tests/fixtures/`：

- `sample_with_exif.jpg`: 常规 EXIF 主流程图片
- `motion_photo.jpg`: Motion Photo 示例
- `ultrahdr.jpg`: Ultra HDR 示例
- `no_exif.jpg`: 缺失 EXIF 的错误分支
- `unsupported_brand.jpg`: 未支持品牌分支

## 安全说明

- 所有下载、预览、ZIP 和 Motion Video 链接都通过 `DOWNLOAD_TOKEN_SECRET` 签名。
- 上传和任务重试使用 `services/path_safety.py` 限制文件路径必须位于 `UPLOAD_FOLDER` 下。
- 文件名会通过 `werkzeug.utils.secure_filename` 清洗。
- 阅后即焚文件会在访问后进入删除队列。
- 默认响应头包含 `X-Content-Type-Options`、`X-Frame-Options`、`Referrer-Policy` 和 CSP。
- 上传接口和 ZIP 接口有限速配置。

## 已知约束

- 默认只允许 `png`、`jpg`、`jpeg` 上传。
- 单文件最大请求体为 200 MB。
- 图片像素上限为 200,000,000。
- ZIP 一次最多打包 50 个文件。
- 状态持久化使用 SQLite，推荐单实例部署。
- Motion Photo 和 Ultra HDR 处理依赖真实设备写入的元数据，不同厂商格式可能需要补充兼容。

## 许可证与三方组件

项目许可证见 `LICENSE`。

本项目使用 Phil Harvey 开发的 ExifTool。ExifTool 采用 Artistic License 2.0 与 GPL 双许可发布，本项目按 Artistic License 2.0 使用。

ExifTool 官网：https://exiftool.org/

欢迎通过 Issue 或 PR 补充设备兼容、Logo 映射、水印样式和部署文档。
