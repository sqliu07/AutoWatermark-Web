# 浏览器本地处理可行性评估

## 结论

可以把照片处理和照片存储迁到手机／电脑浏览器，由 NAS 仅托管 Vue 页面、Logo、字体和按需加载的 WASM。照片可不上传 NAS，也不需要 Python 接收和渲染。

这需要迁移处理流水线，目前完成的后端优化不会自动成为浏览器处理模式。本次只做 NAS 只读检查和方案评估，没有改变 NAS 上的配置或部署。

## 部署环境依据

只读检查发现：Intel Celeron N5105、4 核、约 8 GB RAM，采样时可用约 2.5 GB，UGOS x86_64；运行 Docker 20.10.16 和 Nginx Proxy Manager。当前水印容器为 `autowatermark:v4.0`、单 Gunicorn worker，上传和日志目录挂载到 NAS，未设置 CPU／内存硬上限。反向代理已提供 HTTPS。

容器 CPU／内存采样存在明显异常，未据此评估吞吐，也没有进行远程压力测试。硬件足以托管静态页面；照片本地处理能减少与 NAS 其他服务之间的资源竞争。

## 技术路线

| 能力 | 浏览器方案 | 手机与电脑的主要约束 |
| --- | --- | --- |
| JPEG／PNG 水印和五种版式 | 保留 Vue；本地文件读取、JS EXIF 解析、Web Worker＋OffscreenCanvas 绘图，客户端保存／ZIP。 | 字体度量、方向、色彩和编码质量需做跨浏览器对比；Canvas 重新编码不会自动完成所有 EXIF 保留工作。 |
| Ultra HDR | 采用支持 WASM 构建的 libultrahdr，或移植当前 gain map／XMP 重封装逻辑。 | 必须处理主图、gain map、边框映射及元数据，不能只导出 Canvas JPEG 后宣称保留 HDR。需要真实设备和相册回读验证。 |
| 动态照片，仅修改封面 | 本地识别 MP4 尾部、保留原视频、重建静态封面及 XMP 偏移。 | 原视频可以不重新编码，但视频本身不会新增水印，产品上必须明确说明。 |
| 动态视频也加水印 | 优先评估 WebCodecs 编解码＋本地 MP4 解封装／封装；ffmpeg.wasm 按需作为备选。 | 设备编码器、浏览器支持、旋转、音轨和相册识别需要验证。ffmpeg.wasm 的加载、内存和耗电不适合直接作为所有手机的默认路径。 |

WASM 应用于需要稳定编码或特殊格式的模块；普通图片流程可以先使用浏览器原生能力。直接把 Flask、Pillow、ExifTool、FFmpeg 子进程整套搬进浏览器会带来较大兼容和启动成本。

## 手机资源预算

- 4000 万像素的一张 RGBA 缓冲约 160 MB，多份画布加解码、输入和输出可能达到数百 MB。因此手机默认一张一张处理，及时关闭 ImageBitmap／VideoFrame、释放 Blob URL，并在能力不足时明确提示降低尺寸。
- 大文件应尽量使用 Blob／File.slice 和流式封装，避免反复复制整文件。客户端 ZIP 也需要数量和内存限制。
- 当前三份主要 OTF 字体合计约 21 MB，需压缩、裁剪或按使用情况加载，不能把所有字体与视频 WASM 一起作为首屏资源。
- 首选单线程 WASM，确认收益后再评估多线程；SharedArrayBuffer 模式需要 HTTPS 和相应跨源隔离配置。

## 建议实施顺序与验收

1. 先建立纯本地 JPEG／PNG 路径：五种版式、EXIF 常用字段、方向、批量排队、文件名及下载／ZIP；网络抓包确认照片字节没有上传。
2. 用 Android Chrome 与真实 iPhone Safari 对比成片、字体、色彩、峰值内存和大图失败提示，验证 PWA／离线可用性。
3. 增加本地 HDR，并用现有真实 fixture 检查 gain map 和相册显示。
4. 再决定动态照片保留原视频还是视频也渲染；针对不同设备做运行时编码能力检测。
5. 若采用纯本地目标，未支持的情况明确提示，不静默上传服务器回退；NAS 最终只保留静态服务。

## 一手资料

- [OffscreenCanvas 标准](https://html.spec.whatwg.org/multipage/canvas.html#the-offscreencanvas-interface)
- [libultrahdr 官方 WASM 构建目标](https://github.com/google/libultrahdr/blob/main/docs/building.md#target---wasm)
- [Chrome WebCodecs 工作流](https://developer.chrome.com/docs/web-platform/best-practices/webcodecs)
- [ffmpeg.wasm 官方性能示例](https://ffmpegwasm.netlify.app/docs/performance/)、[加载及多线程要求](https://ffmpegwasm.netlify.app/docs/getting-started/usage/)
