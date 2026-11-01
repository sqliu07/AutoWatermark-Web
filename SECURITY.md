# 安全审查与修复记录（2026-10-31）

## 当前目录修改分析

本次工作开始时已有 34 个受版本控制文件发生变更，另有未跟踪的实现、测试和前端构建产物；审查和修复保留了这些修改，随后按主题分类提交。

- `services/state.py`、任务流程、`gunicorn.conf.py`：SQLite 单进程所有权、任务原子状态迁移、执行器数量/输入字节限额和退出生命周期。
- `imaging/*`、`process.py`、`media/*`：在分配画布前限制像素、尺寸、比例及文本长度，减少资源泄漏和重复解码。
- 上传和下载：随机上传文件名、存储配额、ZIP 去重/总大小限制、阅后即焚响应关闭清理。
- 前端 API/store/polling：轮询超时、429 退避；另有日志轮转、Docker 上下文排除和依赖升级。

这些修改改善了资源边界，但初始全量测试仍有 2 处失败（97 项通过）：清理线程调用已删除的状态接口，以及测试仍模拟旧执行器入口。两者已修复，并保留容量限制。清理失败现在会重试，只有删除成功或文件已不存在才确认持久化焚烧记录。

## Dependabot 与依赖

通过经过认证的 GitHub API 读取了 [Dependabot 告警](https://github.com/sqliu07/AutoWatermark-Web/security/dependabot)：当时有 141 条未关闭告警，其中 108 条来自两份 requirements 中的 Pillow，33 条来自 npm 依赖。告警数量包含跨清单、跨组件重复记录，不代表 141 个独立可利用入口。

| 组件 | 修复后版本/最低版本 | 处理 |
| --- | --- | --- |
| Pillow | 13.0.0 | 覆盖最新解码器内存安全、EXIF 和资源耗尽告警；此前工作区的 12.3.0 仍受部分告警影响。 |
| Werkzeug | 至少 3.1.9 | 同时补齐审计发现的 GHSA-g6x2-hccm-hh4m。 |
| Axios / follow-redirects | 1.21.0 / 1.16.2 | 修复重定向、请求控制、原型污染相关告警。 |
| Vue / server-renderer | 3.5.44 | 修复 SSR 属性名处理告警。 |
| vue-i18n / @intlify | 11.4.16 | 迁移至有修复的 v11，覆盖 escapeParameter/srcdoc 等告警；保持现有 Composition API。 |
| Vite | 6.4.5 | 修复开发服务器及 launch-editor 相关告警。 |
| PostCSS / nanoid / source-map-js | 8.5.32 / 3.3.20 / 1.2.2 | 通过正常依赖解析升级传递依赖，无强制覆盖或忽略告警。 |

现有运行依赖没有新增。Pillow 13 要求 Python 3.11+，当前 vue-i18n 要求 Node 22+，Docker 构建环境相应升级到 Python 3.12 和 Node 22。镜像使用发行版维护的 FFmpeg，替换固定的旧版第三方静态二进制，并在构建时更新 pip。启动脚本根据依赖清单的 SHA-256 安装依赖，修复“包可导入就永久跳过安全升级”的问题。

参考：[Pillow 13 安全修复](https://pillow.readthedocs.io/en/stable/releasenotes/13.0.0.html)、[vue-i18n srcdoc 告警](https://github.com/advisories/GHSA-83rm-6c8r-g728)。

## 公网入口修复

| 问题 | 影响 | 已采取的措施 |
| --- | --- | --- |
| 仅按扩展名判断图片 | 伪装 JPG 的 TIFF/GIF/EPS 等进入额外解码器。 | 上传时验证 JPEG/PNG 内容和结构，在 EXIF、主图、gain map 各入口限制 Pillow 解码器。 |
| 不可信 XMP XML | DTD/实体展开可能增加内存和 CPU 消耗。 | 解析前拒绝 DTD/实体，限制为一个 APP1 段的大小；无新增 XML 依赖。 |
| 视频格式自动探测 | 含 `ftyp` 文本的 DASH 文档可伪装为 MP4，诱导 ffprobe 发起服务端请求。 | 仅使用 MOV/MP4 解复用器、file 协议，禁用外部数据引用；真实回环 HTTP 回归测试验证不发生请求。 |
| 视频资源无完整上限 | 小图片附带超大/超长视频，绕过图片像素保护。 | 检查视频及派生画布尺寸，30 秒、128 MiB、线程/帧数/超时限制；失败时清理输出。 |
| 文档固定示例密钥可直接使用 | 照抄部署后，攻击者可以伪造文件签名。 | 改为生成随机密钥，启动拒绝短密钥；文件类型白名单防止下载状态数据库；异常 token/expiry 安全拒绝。 |
| 私有结果可被缓存、链接可作 Referer | 共享代理或浏览器可保留照片、状态结果与签名。 | 所有 API 设置 no-store/private，Referrer-Policy 改为 no-referrer。 |
| 跨站匿名资源消耗、过大的表单/JSON | 恶意网页可借访客请求消耗处理资源。 | 写操作检查 Origin/Fetch Metadata，限制普通字段、表单项和 JSON 大小；命令行客户端仍受限流和准入限制。 |
| 元数据解析早于执行器准入 | 等待选项的任务及同步解析绕过后台队列限制。 | 上传解析串行准入，活动/等待任务满额时在元数据读取前拒绝。 |
| 清理线程退出/越界删除 | 文件和焚烧记录无法回收，符号链接可能跨越上传目录。 | 修复状态接口、停止与重试流程，保护 SQLite 锁和数据库文件，检查删除路径根目录。 |
| 反向代理共享限流身份 | 所有访客可能被当作同一代理 IP；盲目信任转发头则可绕过限流。 | 仅对明确配置的代理地址处理一跳客户端 IP/协议；增加域名白名单配置及部署示例。 |

默认 CSP 同时禁止 object、外部 base URI 和 iframe 嵌入，HTTPS 响应提供 HSTS。公网部署说明和代理配置见 [README.md](README.md#公网反向代理)。这些控制遵循 [Flask 安全建议](https://flask.palletsprojects.com/en/stable/web-security/)及 [Werkzeug 代理信任说明](https://werkzeug.palletsprojects.com/en/stable/middleware/proxy_fix/)。

## 验证和部署边界

验证记录位于本地忽略目录 `.omx/security/`。新增测试覆盖伪装图片、正常 JPEG/PNG、跨站请求、缓存策略、异常签名、域名/代理信任、上传准入、清理重试和启动依赖刷新；视频测试运行真实 FFmpeg/ffprobe，覆盖恶意播放列表和正常编码。

- 全量 pytest：184 项通过。3 条 Pillow 警告来自真实照片 fixture 的异常 MPO 元数据，已回退为普通 JPEG，不影响测试结果。
- 前端：5 项轮询测试通过；干净 `npm ci` 和生产构建通过，构建产物已更新。
- 依赖审计：npm audit 0 条已知漏洞；pip-audit 对解析后的开发依赖（25 包）、部署依赖（22 包）和实际本地环境（25 包）均为 0 条已知漏洞。没有忽略告警。
- 浏览器与 Gunicorn：中英文切换、真实照片上传、HDR/Motion 选项确认、处理、预览及下载成功；下载验证返回 200、非空照片、no-store/private，控制台无错误。
- 静态检查：相关修改通过 Pyflakes、Python 编译、Bash 语法及 `git diff --check`；Pyright 检查签名和可信代理两个安全模块，0 错误、0 警告。Bandit 无高危结果；16 条规则提示已逐条复核，主要是受限 XML、白名单 SQL 字段和参数化值、固定参数数组子进程与被拒绝的示例密钥，理由见 `bandit-review.json`。Ruff 下载受网络影响，使用 Pyflakes 完成 lint。
- 高置信度密钥模式扫描：受版本控制文件中未发现真实凭据；本地 `.env*` 同时从 Git 和 Docker 构建上下文排除。

GitHub 上的告警需要在修复提交进入默认分支后由 Dependabot 重新评估，不手动关闭告警。当前 WSL 未启用 Docker 引擎，本地未实际构建/启动镜像；版本标签会触发 GitHub Actions 构建镜像及发布 tar，结果以对应工作流为准。Git 提交和镜像发布不会自动更新 NAS 上的部署。

本服务保持匿名公开使用，任务 UUID 和带签名 URL 是持有者凭据；没有新增用户账户。TLS、入口速率/连接限制、隐藏签名查询参数的访问日志、可信代理网段及容器资源配额需要按部署拓扑配置。内存像素限制不能替代原生解码器的操作系统隔离；这些措施也无法保证抵御大规模 DDoS。
