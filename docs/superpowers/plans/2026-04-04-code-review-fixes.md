# AutoWatermark-Web 代码审阅修复 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复代码审阅中发现的 P0-P2 级别问题，涵盖内存泄漏、安全漏洞、线程安全、前端 XSS 和性能优化

**Architecture:** 逐模块修复，每个 Task 聚焦一个独立问题域。修复顺序严格按优先级 P0 → P1 → P2。每个 Task 完成后可独立提交和测试。

**Tech Stack:** Python/Flask, Pillow, subprocess, Jinja2, Vanilla JS

---

## 文件变更总览

| 文件 | 变更类型 | Task |
|------|----------|------|
| `process.py` | 修改：Image 关闭 | 1 |
| `image_utils.py` | 修改：Image 关闭 + 二分查找 | 1, 9 |
| `motion_photo_utils.py` | 修改：Image 关闭 + subprocess timeout | 1, 2 |
| `ultrahdr_utils.py` | 修改：Image/BytesIO 关闭 | 1 |
| `exif_utils.py` | 修改：subprocess timeout | 2 |
| `routes/download.py` | 修改：路径验证 + 错误信息 | 3, 7 |
| `routes/upload.py` | 修改：错误格式统一 | 6 |
| `app_factory.py` | 修改：安全头 + executor shutdown | 4, 8 |
| `Dockerfile` | 修改：非 root 用户 | 4 |
| `static/js/script.js` | 修改：XSS 修复 | 5 |
| `services/tasks.py` | 修改：错误格式 + metrics 锁 | 6, 10 |
| `services/state.py` | 修改：executor shutdown | 8 |
| `services/cleanup.py` | 修改：定时清理 tasks | 8 |

---

### Task 1: [P0] 修复 PIL Image 内存泄漏

**Files:**
- Modify: `process.py:111-114`
- Modify: `image_utils.py:170, 298, 576, 23, 30-31`
- Modify: `motion_photo_utils.py:120-128, 206-208`
- Modify: `ultrahdr_utils.py:421-446`

- [ ] **Step 1: 修复 process.py Image 泄漏**

在 `process.py` 的 `process_image()` 函数中，Image 在 finally 块之前始终不关闭。在 finally 块中添加关闭逻辑：

```python
# process.py:255 - 修改 finally 块
    finally:
        if 'image' in locals() and image is not None:
            try:
                image.close()
            except Exception:
                pass
        if 'new_image' in locals() and new_image is not None:
            try:
                new_image.close()
            except Exception:
                pass
        if 'motion_session' in locals() and motion_session is not None:
            motion_session.cleanup()
```

- [ ] **Step 2: 修复 image_utils.py Logo Image 泄漏**

`create_right_block()` (line 170), `_create_film_frame_caption_group()` (line 298), `_render_layout_center_stack()` (line 576) 三处 `Image.open(logo_path).convert("RGBA")` 需要确保原始 Image 关闭：

```python
# image_utils.py:170 - create_right_block 中
    logo_target_height = int(footer_height * ImageConstants.LOGO_HEIGHT_RATIO)
    with Image.open(logo_path) as _logo_raw:
        logo = _logo_raw.convert("RGBA")
    logo = image_resize(logo, logo_target_height)
```

```python
# image_utils.py:298 - _create_film_frame_caption_group 中
    logo_target_height = metrics["logo_height"]
    with Image.open(logo_path) as _logo_raw:
        logo_image = _logo_raw.convert("RGBA")
    logo_image = image_resize(logo_image, logo_target_height)
```

```python
# image_utils.py:576 - _render_layout_center_stack 中
    logo_target_height = int(footer_height * style["center_logo_ratio"])
    with Image.open(logo_path) as _logo_raw:
        logo = _logo_raw.convert("RGBA")
    logo = image_resize(logo, logo_target_height)
```

- [ ] **Step 3: 修复 image_utils.py is_image_bright 临时图片泄漏**

```python
# image_utils.py:15-36 - 替换 is_image_bright 函数
def is_image_bright(image, threshold=ImageConstants.WATERMARK_GLASS_BG_THRESHOLD):
    """
    判断图片是否为浅色背景
    """
    gray_img = image.convert("L")
    try:
        stat = ImageStat.Stat(gray_img)
        avg_brightness = stat.mean[0]
        logger.info("Current image avg brightness: %s", str(avg_brightness))
    finally:
        gray_img.close()

    w, h = image.size
    bottom_half = image.crop((0, h // 2, w, h))
    try:
        gray_half = bottom_half.convert("L")
        try:
            stat = ImageStat.Stat(gray_half)
            avg_brightness_half = stat.mean[0]
            logger.info("Bottom-half avg brightness: %s", str(avg_brightness_half))
        finally:
            gray_half.close()
    finally:
        bottom_half.close()

    return avg_brightness > threshold and avg_brightness_half > threshold
```

- [ ] **Step 4: 修复 motion_photo_utils.py Image 泄漏**

```python
# motion_photo_utils.py:119-128 - finalize() 中 Ultra HDR 分支
                if self.ultrahdr_gainmap_xmp is not None:
                    new_im = Image.open(BytesIO(watermarked_still_bytes))
                    try:
                        new_im.load()
                        new_size = new_im.size
                    finally:
                        new_im.close()

                    orig_size = self.ultrahdr_primary_size
                    if orig_size is None:
                        src_im = Image.open(self.still_path)
                        try:
                            src_im.load()
                            orig_size = src_im.size
                        finally:
                            src_im.close()
```

```python
# motion_photo_utils.py:205-208 - prepare_motion_photo() 中
            try:
                im = Image.open(BytesIO(parts.primary_jpeg))
                try:
                    im.load()
                    ultrahdr_primary_size = im.size
                finally:
                    im.close()
            except Exception:
                ultrahdr_primary_size = None
```

- [ ] **Step 5: 修复 ultrahdr_utils.py Image 和 BytesIO 泄漏**

```python
# ultrahdr_utils.py:420-449 - expand_gainmap_for_borders 函数
    # Decode gainmap JPEG to image
    gm_img = Image.open(BytesIO(orig_gainmap_jpeg))
    try:
        gm_img.load()
        gm_rgb = gm_img.convert("RGB")
    finally:
        gm_img.close()

    try:
        gw, gh = gm_rgb.size

        new_gw = max(1, int(round(gw * (nw / bw))))
        new_gh = max(1, int(round(gh * (nh / bh))))

        pad_x = int(round(left_px * (gw / bw)))
        pad_y = int(round(top_px * (gh / bh)))

        params = parse_gainmap_params_from_xmp(orig_gainmap_xmp)
        neutral = neutral_encoded_recovery_for_gain_1(params)

        canvas = Image.new("L", (new_gw, new_gh), color=neutral)
        canvas.paste(gm_rgb, (pad_x, pad_y))
    finally:
        gm_rgb.close()

    out = BytesIO()
    try:
        canvas.save(out, format="JPEG", quality=100, optimize=False)
        result = inject_xmp(out.getvalue(), orig_gainmap_xmp)
    finally:
        canvas.close()
        out.close()

    return result
```

- [ ] **Step 6: 运行测试验证**

Run: `cd /home/lsq/workspace/project/pythonProj/AutoWatermark-Web && python -m pytest tests/ -v`
Expected: 所有测试通过

- [ ] **Step 7: 提交**

```bash
git add process.py image_utils.py motion_photo_utils.py ultrahdr_utils.py
git commit -m "fix(memory): close PIL Image objects to prevent memory leaks"
```

---

### Task 2: [P0] 子进程调用添加 timeout

**Files:**
- Modify: `exif_utils.py:212-218`
- Modify: `motion_photo_utils.py:604-618, 627-640, 752-753, 765-781`

- [ ] **Step 1: 修复 exif_utils.py exiftool 超时**

```python
# exif_utils.py:212-218 - 添加 timeout=30
                    try:
                        output = subprocess.check_output(
                            [str(exif_tool_path), exif_id, image_path],
                            stderr=subprocess.STDOUT,
                            timeout=30,
                        )
                    except subprocess.TimeoutExpired:
                        logger.warning("ExifTool timed out for %s with %s", image_path, exif_id)
                        continue
                    except Exception:
                        continue
```

- [ ] **Step 2: 修复 motion_photo_utils.py 所有 subprocess 调用**

```python
# motion_photo_utils.py:604-618 - _copy_all_metadata_with_exiftool 添加 timeout
    try:
        subprocess.run(
            [
                "exiftool",
                "-overwrite_original",
                "-TagsFromFile",
                str(src_jpg),
                "-all:all",
                "-unsafe",
                str(dst_jpg),
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
        )
    except Exception:
        return
```

```python
# motion_photo_utils.py:627-640 - _get_video_wh 添加 timeout
        r = subprocess.run(
            [
                ffprobe_path,
                "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-of", "csv=p=0:s=x",
                str(video_path),
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
        )
```

```python
# motion_photo_utils.py:752-753 - _apply_watermark_to_video ffmpeg 添加 timeout + stderr PIPE
    try:
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=300)
    except subprocess.TimeoutExpired:
        raise RuntimeError("ffmpeg timed out while processing motion video")
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"Failed to overlay watermark onto motion video: {exc.stderr.decode(errors='ignore')}"
        ) from exc
```

```python
# motion_photo_utils.py:765-781 - _get_video_rotation 添加 timeout
        result = subprocess.run(
            [
                ffprobe_path,
                "-v", "error",
                "-select_streams", "v:0",
                "-show_streams",
                "-of", "json",
                str(video_path),
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
        )
```

- [ ] **Step 3: 运行测试验证**

Run: `cd /home/lsq/workspace/project/pythonProj/AutoWatermark-Web && python -m pytest tests/ -v`
Expected: 所有测试通过

- [ ] **Step 4: 提交**

```bash
git add exif_utils.py motion_photo_utils.py
git commit -m "fix(security): add timeout to all subprocess calls"
```

---

### Task 3: [P0] /download_zip 路径验证 + 大小限制

**Files:**
- Modify: `routes/download.py:17-53`

- [ ] **Step 1: 添加路径验证和 ZIP 大小限制**

```python
# routes/download.py - 完整替换 download_zip 函数
@bp.route("/download_zip", methods=["POST"])
@limiter.limit(AppConstants.ZIP_RATE_LIMIT)
def download_zip():
    data = request.json or {}
    filenames = data.get("filenames", [])

    if not filenames:
        return jsonify(error="No files provided"), 400

    count = len(filenames)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_filename = f"Packed_Watermark_Images_{count}_{timestamp}.zip"
    zip_path = os.path.join(tempfile.gettempdir(), zip_filename)

    upload_folder = os.path.realpath(current_app.config["UPLOAD_FOLDER"])
    max_zip_bytes = 500 * 1024 * 1024  # 500 MB

    try:
        total_size = 0
        with zipfile.ZipFile(zip_path, "w") as zipf:
            for fname in filenames:
                safe_fname = secure_filename(fname)
                full_path = os.path.join(upload_folder, safe_fname)
                real_path = os.path.realpath(full_path)

                # 路径穿越防护
                if not real_path.startswith(upload_folder + os.sep) and real_path != upload_folder:
                    current_app.logger.warning("Path traversal attempt blocked: %s", fname)
                    continue

                if os.path.exists(real_path) and os.path.isfile(real_path):
                    file_size = os.path.getsize(real_path)
                    if total_size + file_size > max_zip_bytes:
                        current_app.logger.warning("ZIP size limit exceeded, stopping at %d bytes", total_size)
                        break
                    zipf.write(real_path, arcname=safe_fname)
                    total_size += file_size
                else:
                    current_app.logger.warning("Skipping zip for invalid file: %s", fname)
    except Exception:
        current_app.logger.exception("Zip creation failed")
        return jsonify(error="Failed to create zip file"), 500

    zip_url = f"/download_temp_zip/{zip_filename}"
    return jsonify(zip_url=zip_url)
```

- [ ] **Step 2: 加固 download_temp_zip 路径验证**

```python
# routes/download.py - 替换 download_temp_zip 函数
@bp.route("/download_temp_zip/<filename>")
def download_temp_zip(filename):
    safe_filename = secure_filename(filename)
    temp_dir = os.path.realpath(tempfile.gettempdir())
    file_path = os.path.join(temp_dir, safe_filename)
    real_path = os.path.realpath(file_path)

    if not real_path.startswith(temp_dir + os.sep):
        return jsonify(error="File not found"), 404

    if not os.path.exists(real_path):
        return jsonify(error="File not found"), 404
    return send_file(real_path, as_attachment=True, download_name=safe_filename)
```

- [ ] **Step 3: 运行测试验证**

Run: `cd /home/lsq/workspace/project/pythonProj/AutoWatermark-Web && python -m pytest tests/test_routes.py -v`
Expected: 所有路由测试通过

- [ ] **Step 4: 提交**

```bash
git add routes/download.py
git commit -m "fix(security): add path traversal protection and ZIP size limit"
```

---

### Task 4: [P1] 安全响应头 + Docker 非 root

**Files:**
- Modify: `app_factory.py:49` (在 register_error_handlers 之后)
- Modify: `Dockerfile:48-51`

- [ ] **Step 1: 添加安全响应头**

在 `app_factory.py` 的 `register_error_handlers(app)` (line 49) 之后添加：

```python
# app_factory.py:49 之后添加
    @app.after_request
    def set_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        return response
```

- [ ] **Step 2: Docker 添加非 root 用户**

在 Dockerfile 的 `ENV FLASK_ENV=production` (line 48) 之前添加：

```dockerfile
# Dockerfile: 在 ENV 之前添加
RUN useradd -m -u 1000 appuser && \
    mkdir -p /app/upload /app/logs && \
    chown -R appuser:appuser /app

USER appuser
```

- [ ] **Step 3: 运行测试验证**

Run: `cd /home/lsq/workspace/project/pythonProj/AutoWatermark-Web && python -m pytest tests/ -v`
Expected: 所有测试通过

- [ ] **Step 4: 提交**

```bash
git add app_factory.py Dockerfile
git commit -m "fix(security): add response headers and run Docker as non-root"
```

---

### Task 5: [P1] 前端 XSS 修复

**Files:**
- Modify: `static/js/script.js:346-395`

- [ ] **Step 1: 重写 renderSuccess 使用 DOM API**

将 `renderSuccess` 函数 (line 346-370) 从 innerHTML 改为安全的 DOM 构建：

```javascript
// static/js/script.js:346-370 - 替换 renderSuccess 函数
    function renderSuccess(originalName, url) {
        const t = window.t;
        const div = document.createElement('div');
        div.className = "bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden fade-in";

        const imgWrap = document.createElement('div');
        imgWrap.className = "relative group bg-slate-100 aspect-[4/3] flex items-center justify-center overflow-hidden";

        const img = document.createElement('img');
        img.src = url;
        img.className = "max-w-full max-h-full object-contain shadow-sm";
        img.alt = originalName;

        const overlay = document.createElement('div');
        overlay.className = "absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center gap-4 backdrop-blur-[2px]";

        const previewLink = document.createElement('a');
        previewLink.href = url;
        previewLink.target = "_blank";
        previewLink.className = "px-4 py-2 bg-white text-slate-900 rounded-full text-sm font-bold hover:scale-105 transition-transform";
        previewLink.textContent = t.btnPreview;

        const downloadLink = document.createElement('a');
        downloadLink.href = url;
        downloadLink.download = originalName + "_watermark";
        downloadLink.className = "px-4 py-2 bg-brand-600 text-white rounded-full text-sm font-bold hover:scale-105 transition-transform";
        downloadLink.textContent = t.btnDownload;

        overlay.appendChild(previewLink);
        overlay.appendChild(downloadLink);
        imgWrap.appendChild(img);
        imgWrap.appendChild(overlay);

        const info = document.createElement('div');
        info.className = "p-4 flex items-center justify-between";

        const nameDiv = document.createElement('div');
        nameDiv.className = "truncate text-sm font-medium text-slate-700 max-w-[70%]";
        nameDiv.textContent = originalName;

        const badgeWrap = document.createElement('div');
        badgeWrap.className = "flex gap-2";
        const badge = document.createElement('span');
        badge.className = "text-xs px-2 py-1 bg-green-100 text-green-700 rounded-md";
        badge.textContent = t.statusSuccess;
        badgeWrap.appendChild(badge);

        info.appendChild(nameDiv);
        info.appendChild(badgeWrap);

        div.appendChild(imgWrap);
        div.appendChild(info);
        resultContainer.appendChild(div);
    }
```

- [ ] **Step 2: 重写 renderError 使用 DOM API**

将 `renderError` 函数 (line 382-395) 改为安全的 DOM 构建：

```javascript
// static/js/script.js:382-395 - 替换 renderError 函数
    function renderError(originalName, errorMsg) {
        const div = document.createElement('div');
        div.className = "bg-white rounded-xl shadow-sm border border-red-100 p-4 flex items-center gap-4 fade-in";

        const iconWrap = document.createElement('div');
        iconWrap.className = "w-10 h-10 bg-red-50 rounded-full flex items-center justify-center flex-shrink-0";
        iconWrap.innerHTML = '<svg class="w-5 h-5 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>';

        const textWrap = document.createElement('div');
        textWrap.className = "min-w-0 flex-1";

        const nameP = document.createElement('p');
        nameP.className = "text-sm font-bold text-slate-900";
        nameP.textContent = originalName;

        const errorP = document.createElement('p');
        errorP.className = "text-xs text-red-500 truncate";
        errorP.textContent = errorMsg;

        textWrap.appendChild(nameP);
        textWrap.appendChild(errorP);
        div.appendChild(iconWrap);
        div.appendChild(textWrap);
        resultContainer.appendChild(div);
    }
```

- [ ] **Step 3: 修复 displayedResultCount 变量声明**

```javascript
// static/js/script.js:226 - 用 let 声明
        let displayedResultCount = 0;
```

注意：此变量在 `uploadBtn.addEventListener` 回调的闭包内，需确保 `pollTask` 也在同一闭包中可以访问它。当前代码结构中它已在同一闭包，所以添加 `let` 即可。

- [ ] **Step 4: 运行测试验证**

Run: `cd /home/lsq/workspace/project/pythonProj/AutoWatermark-Web && python -m pytest tests/test_routes.py -v`
Expected: 路由测试通过（前端变更不影响后端测试）

- [ ] **Step 5: 提交**

```bash
git add static/js/script.js
git commit -m "fix(security): replace innerHTML with DOM API to prevent XSS"
```

---

### Task 6: [P1] 统一错误响应格式

**Files:**
- Modify: `routes/upload.py:52, 92`
- Modify: `services/tasks.py:170-171`

- [ ] **Step 1: 修复 upload.py 硬编码错误消息**

```python
# routes/upload.py:52 - 替换硬编码英文
    if watermark_type is None:
        return jsonify(error=get_message("invalid_file_type", lang)), 400
```

```python
# routes/upload.py:92 - 替换硬编码英文
    return jsonify(error=get_message("invalid_file_type", lang)), 400
```

- [ ] **Step 2: 修复 tasks.py 错误详情泄露**

```python
# services/tasks.py:170-171 - 不将内部错误详情暴露给客户端
        elif message_key == "unexpected_error" and detail:
            logger.error("Task %s internal error detail: %s", task_id, detail)
            message = get_common_message("unexpected_error", lang)
```

- [ ] **Step 3: 修复 download.py 错误详情泄露**

已在 Task 3 中完成（`return jsonify(error="Failed to create zip file"), 500`）。

- [ ] **Step 4: 运行测试验证**

Run: `cd /home/lsq/workspace/project/pythonProj/AutoWatermark-Web && python -m pytest tests/ -v`
Expected: 所有测试通过

- [ ] **Step 5: 提交**

```bash
git add routes/upload.py services/tasks.py
git commit -m "fix(security): unify error responses and hide internal details"
```

---

### Task 7: [P2] Executor shutdown + 定时清理 tasks

**Files:**
- Modify: `services/state.py:31` (添加 shutdown 方法)
- Modify: `app_factory.py:55-56` (注册 shutdown)
- Modify: `services/cleanup.py:23-77` (添加 task 清理)

- [ ] **Step 1: AppState 添加 shutdown 方法**

```python
# services/state.py - 在 count_tasks_by_status 方法之后添加
    def shutdown(self) -> None:
        self.executor.shutdown(wait=False)
```

- [ ] **Step 2: app_factory.py 注册 atexit 清理**

在 `app_factory.py` 的 `return app` (line 58) 之前添加：

```python
# app_factory.py: return app 之前
    import atexit
    atexit.register(lambda: app.extensions["state"].shutdown())
```

- [ ] **Step 3: cleanup.py 添加定时 task 清理**

在 `background_cleaner()` 函数的 `# 3) Stale uploads` 之后添加：

```python
            # 4) Stale task entries
            from services.tasks import cleanup_old_tasks
            try:
                cleanup_old_tasks(state)
            except Exception:
                pass
```

- [ ] **Step 4: 运行测试验证**

Run: `cd /home/lsq/workspace/project/pythonProj/AutoWatermark-Web && python -m pytest tests/ -v`
Expected: 所有测试通过

- [ ] **Step 5: 提交**

```bash
git add services/state.py app_factory.py services/cleanup.py
git commit -m "fix(stability): add executor shutdown and periodic task cleanup"
```

---

### Task 8: [P2] 字体适配二分查找优化

**Files:**
- Modify: `image_utils.py:273-285`

- [ ] **Step 1: 替换线性搜索为二分查找**

```python
# image_utils.py:273-285 - 替换 _fit_text_font_size 函数
def _fit_text_font_size(text_lines, font_path, start_size, min_size, max_width):
    low = int(min_size)
    high = max(low, int(start_size))
    result = low

    while low <= high:
        mid = (low + high) // 2
        widest = 0
        for line in text_lines:
            if not line:
                continue
            width = text_to_image(line, font_path, mid, "black").width
            widest = max(widest, width)
        if widest <= max_width:
            result = mid
            low = mid + 1
        else:
            high = mid - 1
    return result
```

- [ ] **Step 2: 运行 film frame 相关测试**

Run: `cd /home/lsq/workspace/project/pythonProj/AutoWatermark-Web && python -m pytest tests/test_film_frame_style.py -v`
Expected: 所有测试通过

- [ ] **Step 3: 提交**

```bash
git add image_utils.py
git commit -m "perf: use binary search for font size fitting"
```

---

### Task 9: [P2] metrics 锁修复

**Files:**
- Modify: `services/tasks.py:53-65`

- [ ] **Step 1: 将计算移入锁内**

```python
# services/tasks.py:53-65 - 替换 _update_queue_metrics 函数
def _update_queue_metrics(state, task_id: str, logger) -> None:
    with state.metrics_lock:
        state.metrics["total_tasks"] += 1
        total = state.metrics["total_tasks"]
        failed = state.metrics["failed_tasks"]
        failure_rate = (failed / total) if total else 0
    queue_length = state.count_tasks_by_status("queued")
    logger.info(
        "Queued task %s | queue=%s | failure_rate=%.2f%%",
        task_id,
        queue_length,
        failure_rate * 100,
    )
```

- [ ] **Step 2: 运行测试验证**

Run: `cd /home/lsq/workspace/project/pythonProj/AutoWatermark-Web && python -m pytest tests/test_tasks.py -v`
Expected: 所有测试通过

- [ ] **Step 3: 提交**

```bash
git add services/tasks.py
git commit -m "fix(thread-safety): compute failure_rate inside metrics lock"
```

---

### Task 10: [P2] 像素限制边界条件修复

**Files:**
- Modify: `process.py:42`

- [ ] **Step 1: 修复边界条件**

```python
# process.py:42 - >= 改为 >
    if max_pixels and image_size > max_pixels:
```

- [ ] **Step 2: 运行测试验证**

Run: `cd /home/lsq/workspace/project/pythonProj/AutoWatermark-Web && python -m pytest tests/ -v`
Expected: 所有测试通过

- [ ] **Step 3: 提交**

```bash
git add process.py
git commit -m "fix: correct pixel limit boundary condition (>= to >)"
```
