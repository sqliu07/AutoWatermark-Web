from constants import CommonConstants, AppConstants 
import os
import time
import json
import zipfile
import tempfile
import uuid
import glob
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

from flask import Flask, after_this_request, request, render_template, jsonify, send_file, abort, Response, stream_with_context
from werkzeug.utils import secure_filename
import threading
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_limiter.errors import RateLimitExceeded

from process import process_image
from exif_utils import get_manufacturer
from PIL import Image
import piexif
from errors import WatermarkError
from logging_utils import get_logger

burn_queue = {}
burn_queue_lock = threading.Lock()
metrics_lock = threading.Lock()
tasks_lock = threading.Lock()
metrics = {
    'total_tasks': 0,
    'succeeded_tasks': 0,
    'failed_tasks': 0,
}

logger = get_logger("autowatermark.app")

def background_cleaner():
    """全能后台清洁工：清理阅后即焚、过期临时文件、过期的普通上传"""
    while True:
        time.sleep(AppConstants.CLEANER_INTERVAL_SECONDS) # 检查频率
        current_time = time.time()

        cleaned_burn = 0
        cleaned_zip = 0
        cleaned_stale = 0

        # --- 1. 处理阅后即焚 (保留原有逻辑) ---
        to_burn = []
        with burn_queue_lock:
            for fp, expire_at in list(burn_queue.items()):
                if current_time > expire_at:
                    to_burn.append(fp)
                    del burn_queue[fp]

        for fp in to_burn:
            cleanup_file_and_original(fp) # 封装删除逻辑
            cleaned_burn += 1

        # --- 2. 清理遗留的 ZIP 压缩包 (新增) ---
        # 假设 ZIP 文件保留 1 小时
        temp_dir = tempfile.gettempdir()
        # 匹配对应模式的文件
        zip_pattern = os.path.join(temp_dir, "Packed_Watermark_Images_*.zip")
        for zip_file in glob.glob(zip_pattern):
            try:
                # 获取文件最后修改时间
                if current_time - os.path.getmtime(zip_file) > AppConstants.ZIP_RETENTION_SECONDS:
                    os.remove(zip_file)
                    logger.info(f"[Auto-Clean] Deleted old zip: {zip_file}")
                    cleaned_zip += 1
            except OSError:
                pass

        # --- 3. 兜底清理：清理 UPLOAD_FOLDER 中超过 24小时 的所有文件 (新增) ---
        # 防止非阅后即焚文件的无限堆积
        upload_dir = app.config['UPLOAD_FOLDER']
        for filename in os.listdir(upload_dir):
            file_path = os.path.join(upload_dir, filename)
            try:
                # 如果文件超过 24 小时 (86400秒)
                if os.path.isfile(file_path) and (current_time - os.path.getmtime(file_path) > 86400):
                    os.remove(file_path)
                    logger.info(f"[Auto-Clean] Deleted stale file: {filename}")
                    cleaned_stale += 1
            except OSError:
                pass

        if cleaned_burn or cleaned_zip or cleaned_stale:
            logger.info(
                "[Auto-Clean] Summary - burn: %s, zip: %s, stale: %s",
                cleaned_burn,
                cleaned_zip,
                cleaned_stale,
            )

def cleanup_file_and_original(file_path):
    """封装的删除单个文件及其原图的逻辑"""
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
            logger.info(f"[Burn] Deleted: {os.path.basename(file_path)}")
        except OSError: pass

# 启动后台线程 (Daemon 线程会随主程序退出而退出)
threading.Thread(target=background_cleaner, daemon=True).start()

app = Flask(__name__, static_url_path='/static', static_folder='./static')
app.logger.handlers.clear()
for handler in logger.handlers:
    app.logger.addHandler(handler)
app.logger.setLevel(logger.level)
app.logger.propagate = False

app.config['UPLOAD_FOLDER'] = AppConstants.UPLOAD_FOLDER
app.config['ALLOWED_EXTENSIONS'] = AppConstants.ALLOWED_EXTENSIONS
app.config['MAX_CONTENT_LENGTH'] = AppConstants.MAX_CONTENT_LENGTH

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=AppConstants.DEFAULT_RATE_LIMITS, # 全局默认限制（宽松）
    storage_uri="memory://" 
)

@app.errorhandler(RateLimitExceeded)
def handle_rate_limit_error(e):
    # 获取当前的语言设置，以便返回对应语言的错误提示
    lang = request.args.get('lang', 'zh').split('?')[0]
    msg = "请求过于频繁，请稍后再试。" if lang == 'zh' else "Too many requests, please try again later."
    return jsonify(error=msg), 429

# --- 异步处理配置 ---
executor = ThreadPoolExecutor(max_workers=AppConstants.EXECUTOR_MAX_WORKERS)   # 限制最大并发数为4
tasks = {}  # 存储任务状态: {task_id: {'status': '...', 'result': ...}}

ERROR_MESSAGES = AppConstants.ERROR_MESSAGES

# 语言翻译字典
try:
    with open("static/i18n/translations.json", "r", encoding="utf-8") as f:
        translations = json.load(f)
except FileNotFoundError:
    translations = {}
    logger.error("Translation file not found!")

def get_message(key, lang='zh'):
    return ERROR_MESSAGES.get(key, {}).get(lang)

def get_common_message(key, lang='zh'):
    return CommonConstants.ERROR_MESSAGES.get(key, {}).get(lang)

# 确保上传文件夹存在
os.makedirs(AppConstants.UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    """检查文件扩展名是否允许"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def cleanup_old_tasks():
    """清理超过 1 小时的旧任务，防止内存泄漏"""
    current_time = time.time()
    to_remove = []
    with tasks_lock:
        for tid, info in list(tasks.items()):
            if current_time - info.get('submitted_at', 0) > AppConstants.TASK_RETENTION_SECONDS:
                to_remove.append(tid)
        for tid in to_remove:
            tasks.pop(tid, None)

def detect_manufacturer(filepath):
    try:
        with Image.open(filepath) as image:
            exif_bytes = image.info.get('exif')
            if not exif_bytes:
                return None
            exif_dict = piexif.load(exif_bytes)
            return get_manufacturer(filepath, exif_dict)
    except Exception:
        return None

def background_process(task_id, filepath, lang, watermark_type, image_quality, burn_after_read, logo_preference):
    """后台执行图片处理，并更新任务状态"""
    start_time = time.time()
    try:
        with tasks_lock:
            tasks[task_id]['status'] = 'processing'
            tasks[task_id]['progress'] = max(tasks[task_id].get('progress', 0), 0.01)
            tasks[task_id]['stage'] = 'processing'

        def update_progress(progress, stage=None):
            with tasks_lock:
                task = tasks.get(task_id)
                if not task:
                    return
                current = task.get('progress', 0)
                task['progress'] = max(current, min(progress, 1))
                if stage:
                    task['stage'] = stage

        # 调用 process.py 中的核心逻辑
        process_image(
            filepath,
            lang=lang,
            watermark_type=watermark_type,
            image_quality=image_quality,
            logo_preference=logo_preference,
            progress_callback=update_progress,
        )

        # 计算生成的文件名
        filename = os.path.basename(filepath)
        original_name, extension = os.path.splitext(filename)
        processed_filename = f"{original_name}_watermark{extension}"

        # 成功：更新状态并保存结果 URL
        with tasks_lock:
            tasks[task_id]['status'] = 'succeeded'
            tasks[task_id]['result'] = {
                'processed_image': f'/upload/{processed_filename}?lang={lang}&burn={burn_after_read}'
            }
            tasks[task_id]['progress'] = 1.0
            tasks[task_id]['stage'] = 'done'

        with metrics_lock:
            metrics['succeeded_tasks'] += 1

    except WatermarkError as err:
        message_key = err.get_message_key()
        detail = err.get_detail()
        message = get_common_message(message_key, lang) or detail or get_common_message('unexpected_error', lang)
        if message_key == 'unsupported_manufacturer' and detail:
            message = f"{message} ({detail})"

        with tasks_lock:
            tasks[task_id]['status'] = 'failed'
            tasks[task_id]['error'] = message
            tasks[task_id]['progress'] = 1.0
            tasks[task_id]['stage'] = 'failed'
        logger.warning(f"Task {task_id} failed: {message}")
        with metrics_lock:
            metrics['failed_tasks'] += 1

    except Exception:
        logger.exception(f"Unexpected error in background task {task_id}")
        with tasks_lock:
            tasks[task_id]['status'] = 'failed'
            tasks[task_id]['error'] = get_common_message('unexpected_error', lang)
            tasks[task_id]['progress'] = 1.0
            tasks[task_id]['stage'] = 'failed'
        with metrics_lock:
            metrics['failed_tasks'] += 1

    finally:
        duration = time.time() - start_time
        with metrics_lock:
            total = metrics['total_tasks']
            failed = metrics['failed_tasks']
        failure_rate = (failed / total) if total else 0
        with tasks_lock:
            queue_length = sum(
                1 for info in tasks.values()
                if info.get('status') in {'queued', 'processing'}
            )
        logger.info(
            "Task %s finished in %.2f s | queue=%s | failure_rate=%.2f%%",
            task_id,
            duration,
            queue_length,
            failure_rate * 100,
        )

@app.errorhandler(404)
def not_found_error(error):
    lang = request.args.get('lang', 'zh').split('?')[0]
    return render_template('image_deleted.html', lang=lang, translations=translations), 404

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
@limiter.limit(AppConstants.UPLOAD_RATE_LIMIT)
def upload_file():
    # 顺便清理旧任务
    cleanup_old_tasks()

    if 'file' not in request.files:
        return jsonify(error=get_message('no_file_uploaded', request.args.get('lang', 'zh'))), 400

    file = request.files['file']

    if file.filename == '':
        return jsonify(error=get_message('no_file_selected', request.args.get('lang', 'zh'))), 400

    if not allowed_file(file.filename):
        return jsonify(error=get_message('invalid_file_type', request.args.get('lang', 'zh'))), 400

    watermark_type = request.form.get('watermark_type', '1')
    burn_after_read = request.form.get('burn_after_read', '0')
    image_quality = request.form.get('image_quality', "high")
    logo_preference = request.form.get('logo_preference')

    # 质量参数转换
    if "high" == image_quality:
        image_quality_int = CommonConstants.IMAGE_QUALITY_MAP.get("high")
    elif "medium" == image_quality:
        image_quality_int = CommonConstants.IMAGE_QUALITY_MAP.get("medium")
    else:
        image_quality_int = CommonConstants.IMAGE_QUALITY_MAP.get("low")

    if watermark_type is None:
        return jsonify(error="Watermark style not selected!"), 400

    if file and allowed_file(file.filename):
        lang = request.args.get('lang', 'zh')
        timestamp = datetime.fromtimestamp(int(time.time())).strftime('%Y-%m-%d_%H-%M-%S')

        filename = secure_filename(file.filename)
        extension = filename.rsplit('.', 1)[1]
        filename_with_timestamp = f"{filename.rsplit('.', 1)[0]}_{timestamp}.{extension}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename_with_timestamp)

        file.save(filepath)

        manufacturer = detect_manufacturer(filepath)
        if manufacturer and "xiaomi" in manufacturer.lower():
            normalized_preference = (logo_preference or "").lower()
            if normalized_preference not in {"xiaomi", "leica"}:
                return jsonify({'needs_logo_choice': True}), 200
            logo_preference = normalized_preference

        try:
            watermark_type_int = int(watermark_type)
        except ValueError:
            return jsonify(error=get_common_message('unexpected_error', lang)), 400

        # --- 异步处理逻辑 ---
        task_id = str(uuid.uuid4())
        with tasks_lock:
            tasks[task_id] = {
                'status': 'queued',
                'submitted_at': time.time(),
                'progress': 0.0,
                'stage': 'queued',
            }

        with metrics_lock:
            metrics['total_tasks'] += 1
            total = metrics['total_tasks']
            failed = metrics['failed_tasks']
        failure_rate = (failed / total) if total else 0
        with tasks_lock:
            queue_length = sum(1 for info in tasks.values() if info.get('status') == 'queued')
        logger.info(
            "Queued task %s | queue=%s | failure_rate=%.2f%%",
            task_id,
            queue_length,
            failure_rate * 100,
        )

        executor.submit(
            background_process, 
            task_id, 
            filepath, 
            lang, 
            watermark_type_int, 
            image_quality_int, 
            burn_after_read,
            logo_preference,
        )

        # 立即返回任务 ID
        return jsonify({'task_id': task_id}), 202

    return jsonify(error='Invalid file type'), 400

@app.route('/status/<task_id>', methods=['GET'])
def get_task_status(task_id):
    with tasks_lock:
        task = tasks.get(task_id)
        if task is not None:
            task = dict(task)
    if not task:
        return jsonify({'status': 'unknown'}), 404
    return jsonify(task)

@app.route('/upload/<filename>')
def upload_file_served(filename):
    lang = request.args.get('lang', 'zh').split('?')[0]
    burn_after_read = request.args.get('burn', '0')

    filename = secure_filename(filename) 
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

    if not os.path.exists(file_path):
        accept = request.headers.get("Accept", "")
        if "text/html" in accept:
            return render_template(
                'image_deleted.html', lang=lang, translations=translations
            ), 404
        else:
            return jsonify(error="File not found"), 404

    # === 修改核心逻辑 ===
    # 如果开启了阅后即焚，更新该文件的“存活时间”
    if str(burn_after_read).strip() == '1':
        with burn_queue_lock:
            # 每次请求（无论是预览还是下载），都将生命周期重置为 120 秒后
            # 这样只要用户还在操作，文件就不会被删
            burn_queue[file_path] = time.time() + AppConstants.BURN_TTL_SECONDS

    # 使用 send_file 正常发送，享受 Nginx/Flask 的静态文件优化
    return send_file(file_path)

@app.route('/not_found')
def not_found_page():
    lang = request.args.get('lang', 'zh')
    return render_template('image_deleted.html', lang=lang, translations=translations), 404

@app.route('/download_zip', methods=['POST'])
@limiter.limit(AppConstants.ZIP_RATE_LIMIT)
def download_zip():
    data = request.json
    filenames = data.get('filenames', [])
    lang = data.get('lang', 'zh')

    if not filenames:
        return jsonify(error="No files provided"), 400

    count = len(filenames)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_filename = f"Packed_Watermark_Images_{count}_{timestamp}.zip"
    zip_path = os.path.join(tempfile.gettempdir(), zip_filename)

    try:
        with zipfile.ZipFile(zip_path, 'w') as zipf:
            for fname in filenames:
                # --- 安全修复：防止路径遍历攻击 ---
                safe_fname = secure_filename(fname)
                full_path = os.path.join(app.config['UPLOAD_FOLDER'], safe_fname)

                # 必须确保文件确实存在于上传目录中
                if os.path.exists(full_path) and os.path.isfile(full_path):
                    zipf.write(full_path, arcname=safe_fname)
                else:
                    logger.warning(f"Skipping zip for invalid file: {fname}")

    except Exception as e:
        logger.error(f"Zip creation failed: {str(e)}")
        return jsonify(error=str(e)), 500

    zip_url = f"/download_temp_zip/{zip_filename}"
    return jsonify(zip_url=zip_url)

@app.route('/download_temp_zip/<filename>')
def download_temp_zip(filename):
    # 同样进行安全检查
    safe_filename = secure_filename(filename)
    file_path = os.path.join(tempfile.gettempdir(), safe_filename)
    logger.info(f"zip file path: {file_path}")
    if not os.path.exists(file_path):
        return "File not found", 404
    return send_file(file_path, as_attachment=True, download_name=safe_filename)

if __name__ == '__main__':
    is_production = os.environ.get("FLASK_ENV") == "production"

    if is_production:
        logger.info("请使用 gunicorn 启动：gunicorn -w 4 -b 0.0.0.0:5000 app:app")
    else:
        app.run(host='0.0.0.0', port=5000, debug=True)
