from constants import CommonConstants
import os
import time
import json
import zipfile
import tempfile
import uuid
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

from flask import Flask, after_this_request, request, render_template, jsonify, send_file, abort
from werkzeug.utils import secure_filename
import threading

from process import process_image
from errors import WatermarkError
from logging_utils import get_logger

logger = get_logger("autowatermark.app")

app = Flask(__name__, static_url_path='/static', static_folder='./static')
app.logger.handlers.clear()
for handler in logger.handlers:
    app.logger.addHandler(handler)
app.logger.setLevel(logger.level)
app.logger.propagate = False

app.config['UPLOAD_FOLDER'] = CommonConstants.UPLOAD_FOLDER
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg'}
app.config['MAX_CONTENT_LENGTH'] = 200 * 1024 * 1024  # 最大文件 200MB

# --- 异步处理配置 ---
executor = ThreadPoolExecutor(max_workers=4)  # 限制最大并发数为4
tasks = {}  # 存储任务状态: {task_id: {'status': '...', 'result': ...}}

ERROR_MESSAGES = {
    "invalid_file_type": {
        'en': "Invalid file type! Please upload a PNG, JPG or JPEG file.",
        'zh': "无效的文件类型！请上传PNG、JPG或JPEG文件。"
    },
    "no_file_uploaded": {
        'en': "No file uploaded!",
        'zh': "未上传文件！"
    },
    "no_file_selected": {
        'en': "No file selected!",
        'zh': "未选择文件！"
    },
}

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
os.makedirs(CommonConstants.UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    """检查文件扩展名是否允许"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def cleanup_old_tasks():
    """清理超过 1 小时的旧任务，防止内存泄漏"""
    current_time = time.time()
    to_remove = []
    for tid, info in tasks.items():
        if current_time - info.get('submitted_at', 0) > 3600:
            to_remove.append(tid)
    for tid in to_remove:
        tasks.pop(tid, None)

def background_process(task_id, filepath, lang, watermark_type, image_quality, burn_after_read):
    """后台执行图片处理，并更新任务状态"""
    try:
        tasks[task_id]['status'] = 'processing'
        
        # 调用 process.py 中的核心逻辑
        process_image(filepath, lang=lang, watermark_type=watermark_type, image_quality=image_quality)
        
        # 计算生成的文件名
        filename = os.path.basename(filepath)
        original_name, extension = os.path.splitext(filename)
        processed_filename = f"{original_name}_watermark{extension}"
        
        # 成功：更新状态并保存结果 URL
        tasks[task_id]['status'] = 'succeeded'
        tasks[task_id]['result'] = {
            'processed_image': f'/upload/{processed_filename}?lang={lang}&burn={burn_after_read}'
        }
        
    except WatermarkError as err:
        message_key = err.get_message_key()
        detail = err.get_detail()
        message = get_common_message(message_key, lang) or detail or get_common_message('unexpected_error', lang)
        if message_key == 'unsupported_manufacturer' and detail:
            message = f"{message} ({detail})"
            
        tasks[task_id]['status'] = 'failed'
        tasks[task_id]['error'] = message
        logger.warning(f"Task {task_id} failed: {message}")
        
    except Exception as exc:
        logger.exception(f"Unexpected error in background task {task_id}")
        tasks[task_id]['status'] = 'failed'
        tasks[task_id]['error'] = get_common_message('unexpected_error', lang)

@app.errorhandler(404)
def not_found_error(error):
    lang = request.args.get('lang', 'zh').split('?')[0]
    return render_template('image_deleted.html', lang=lang, translations=translations), 404

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
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
    
    # 质量参数转换
    if "high" == image_quality:
        image_quality_int = 95
    elif "medium" == image_quality:
        image_quality_int = 85
    else:
        image_quality_int = 75

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

        try:
            watermark_type_int = int(watermark_type)
        except ValueError:
            return jsonify(error=get_common_message('unexpected_error', lang)), 400

        # --- 异步处理逻辑 ---
        task_id = str(uuid.uuid4())
        tasks[task_id] = {
            'status': 'queued',
            'submitted_at': time.time()
        }
        
        executor.submit(
            background_process, 
            task_id, 
            filepath, 
            lang, 
            watermark_type_int, 
            image_quality_int, 
            burn_after_read
        )

        # 立即返回任务 ID
        return jsonify({'task_id': task_id}), 202

    return jsonify(error='Invalid file type'), 400

@app.route('/status/<task_id>', methods=['GET'])
def get_task_status(task_id):
    task = tasks.get(task_id)
    if not task:
        return jsonify({'status': 'unknown'}), 404
    return jsonify(task)

@app.route('/upload/<filename>')
def upload_file_served(filename):
    lang = request.args.get('lang', 'zh').split('?')[0]
    burn_after_read = request.args.get('burn', '0')
    
    # 安全检查：确保 filename 不包含路径分隔符
    filename = secure_filename(filename) 
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

    @after_this_request
    def delete_file(response):
        def delayed_delete():
            if str(burn_after_read).strip() == '1':
                time.sleep(120)
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except OSError:
                        pass

                # 尝试删除原图
                original_name = filename.split('_watermark')[0]
                # 这里需要小心匹配原图扩展名，简单起见我们尝试查找
                # 更好的方式是在生成时记录原图路径，这里简化处理
                for ext in app.config['ALLOWED_EXTENSIONS']:
                    original_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{original_name}.{ext}")
                    if os.path.exists(original_path):
                        try:
                            os.remove(original_path)
                        except OSError:
                            pass
                        break

        threading.Thread(target=delayed_delete).start()
        return response

    if not os.path.exists(file_path):
        accept = request.headers.get("Accept", "")
        if "text/html" in accept:
            return render_template(
                'image_deleted.html', lang=lang, translations=translations
            ), 404
        else:
            return jsonify(error="File not found"), 404

    return send_file(file_path)

@app.route('/not_found')
def not_found_page():
    lang = request.args.get('lang', 'zh')
    return render_template('image_deleted.html', lang=lang, translations=translations), 404

@app.route('/download_zip', methods=['POST'])
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
    if not os.path.exists(file_path):
        return "File not found", 404
    return send_file(file_path, as_attachment=True, download_name=safe_filename)

if __name__ == '__main__':
    is_production = os.environ.get("FLASK_ENV") == "production"

    if is_production:
        logger.info("请使用 gunicorn 启动：gunicorn -w 4 -b 0.0.0.0:5000 app:app")
    else:
        app.run(host='0.0.0.0', port=5000, debug=True)