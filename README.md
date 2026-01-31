# AutoWatermark Web 📸

> 一个基于 Python Flask 的高性能图片水印自动生成工具，支持智能 EXIF 识别、多风格相框合成及隐私保护功能。

AutoWatermark Web 旨在为摄影师和摄影爱好者提供一个自动化、高质量的照片水印解决方案。它不仅仅是简单的文字叠加，而是通过读取照片的原始 EXIF 元数据（厂商、型号、焦距、光圈、ISO、快门时间），自动匹配品牌 Logo，并生成类似徕卡、哈苏等经典风格的“摄影相框”。适用于作品发布、社交分享与影像归档等场景。

## ✨ 核心特性

### 1. 智能 EXIF 解析
* **自动识别**：无需手动输入参数，自动从照片中提取 `Make` (厂商), `Model` (机型), `FNumber` (光圈), `ExposureTime` (快门), `ISOSpeedRatings` (ISO) 等信息。
* **信息完整**：输出中保留关键拍摄参数，提升作品展示的专业性与可信度。

### 2. 多样化水印风格
项目内置 4 种精选布局风格，适配横构图与竖构图：
* **Style 1 (拍立得风格)**：宽底边留白，复古相框感更明显。
* **Style 2 (经典左右布局)**：左侧显示相机型号，右侧显示厂商 Logo 及拍摄参数，中间以竖线分割。
* **Style 3 (居中极简风格)**：Logo 与拍摄参数在底部居中堆叠，视觉重心更集中。
* **Style 4 (毛玻璃特效)**：底部加入玻璃质感，文字颜色自动适配画面明暗。

### 3. 隐私与安全
* **阅后即焚 (Burn After Read)**：支持开启隐私模式，文件在预览或下载后短时间内自动删除。
* **自动清理机制**：后台定期清理过期临时文件与 ZIP 包，避免存储堆积。
* **路径安全**：文件名清洗机制防止路径遍历攻击。

### 4. 高级功能
* **动态照片支持 (Motion Photo)**：支持上传 Google/Samsung 等设备的动态照片，自动提取高画质的静态帧进行处理。
* **批量处理**：支持多图并发上传处理，并提供 ZIP 一键打包下载。
* **多语言界面**：原生支持简体中文与英文切换。
* **Ultra HDR 兼容**：对部分 Ultra HDR 照片可保留 HDR 效果，提升成片质量。

---

## 🛠️ 技术架构

* **Web 服务**：提供上传、预览、下载的完整使用闭环。
* **图像处理**：自动解析 EXIF 并生成品牌化水印相框。
* **并发处理**：支持多图并发与进度反馈，提升处理效率。
* **前端交互**：原生 Web 界面，操作简单直观。

---

## 🚀 安装与部署

### 方式一：Docker 部署 (推荐)

项目提供了优化的 `Dockerfile`，基于 `python:3.10-slim`，内置了 ffmpeg 和 perl 依赖。

1.  **构建镜像**
    ```bash
    docker build -t autowatermark-web .
    ```

2.  **启动容器**
    ```bash
    # -d 后台运行
    # -p 映射端口 (宿主机:容器)
    # --name 容器名称
    docker run -d -p 5000:5000 --name watermark-app autowatermark-web
    ```

3.  **访问**
    浏览器打开 `http://localhost:5000`

### 方式二：手动部署

**前置要求**:
* Python 3.8+
* FFmpeg (用于处理动态照片)
* Perl (用于 ExifTool)

1.  **克隆代码**
    ```bash
    git clone https://github.com/sqliu07/AutoWatermark-Web
    cd AutoWatermark-Web
    ```

2.  **创建虚拟环境并安装依赖**
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    ```

3.  **运行应用**
    * **开发模式**:
        ```bash
        python3 app.py
        ```
    * **生产模式**:
        ```bash
        # 启动 4 个 Worker 进程
        gunicorn -w 4 -b 0.0.0.0:5000 app:app
        ```
---

## 🧪 自动化测试

运行测试：
```bash
pytest -q
```

或者使用脚本（构建发布会自动调用）：
```bash
./scripts/run_tests.sh
```

测试素材放在 `tests/fixtures/`：
- `sample_with_exif.jpg`：普通带 EXIF 的照片（主流程）
- `motion_photo.jpg`：带 Motion Photo 的 JPEG（需 ffmpeg）
- `ultrahdr.jpg`：Ultra HDR (JPEG_R) 示例
- `no_exif.jpg`：无 EXIF 的照片（用于报错分支）
- `unsupported_brand.jpg`：EXIF 中品牌不在 `logos/` 的照片

## 📷 支持的相机品牌 (部分)

程序内置了复杂的映射逻辑 (`exif_utils.py`) 来匹配各品牌 Logo：

| 品牌 | 内部标识 (Aliases) | Logo 文件 |
| :--- | :--- | :--- |
| **Sony** | sony, sonycorporation | `logos/sony.png` |
| **Nikon** | nikon, nikoncorporation | `logos/nikon.png` |
| **Canon** | canon, canoninc | `logos/canon.png` |
| **Fujifilm** | fujifilm, fujifilmcorporation | `logos/fujifilm.png` |
| **Leica** | leica, leicacameraag | `logos/leica.png` |
| **Hasselblad** | hasselblad | `logos/hasselblad.png` |
| **Olympus** | olympus, olympuscorporation | `logos/olympus.png` |
| **Panasonic** | panasonic | `logos/panasonic.png` |
| **Pentax** | pentax, ricohimaging | `logos/pentax.png` |
| **Xiaomi** | xiaomi | `logos/xiaomi.png` |
| **Apple** | apple | `logos/apple.png` |
| **Huawei** | huawei, xmage | `logos/xmage.png` |

## 致谢 / 贡献

感谢以下开源项目：
[exiftool](https://github.com/exiftool/exiftool)

欢迎 PR、Issue，与我一起完善水印处理体验。

## 三方许可声明

本项目使用了由 Phil Harvey 开发的 ExifTool。

ExifTool 采用 双许可模式（Dual License） 发布，许可证为：

Artistic License 2.0

GNU GPL（版本 1 及以上）

根据 ExifTool 官方许可条款，本项目选择以 Artistic License 2.0 的方式使用 ExifTool，因此不会对本项目的整体开源协议产生 GPL 继承或附加要求。

ExifTool 主页：
https://exiftool.org/

ExifTool 的完整许可证文本可在其官方发布包中获取。
