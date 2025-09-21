from constants import CommonConstants
import os
import time
import json
import zipfile
import tempfile
from datetime import datetime

from flask import Flask, after_this_request, request, render_template, jsonify, send_file, abort
import subprocess
from werkzeug.utils import secure_filename
import threading

app = Flask(__name__, static_url_path='/static', static_folder='./static')

app.config['UPLOAD_FOLDER'] = CommonConstants.UPLOAD_FOLDER
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg'}
app.config['MAX_CONTENT_LENGTH'] = 200 * 1024 * 1024  # 最大文件 200MB

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
with open("static/i18n/translations.json", "r", encoding="utf-8") as f:
    translations = json.load(f)


def get_message(key, lang='zh'):
    return ERROR_MESSAGES.get(key, {}).get(lang)

# 确保上传文件夹存在
os.makedirs(CommonConstants.UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    """检查文件扩展名是否允许"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

@app.errorhandler(404)
def not_found_error(error):
    lang = request.args.get('lang', 'zh').split('?')[0]
    return render_template('image_deleted.html', lang=lang, translations=translations), 404

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/upload', methods=['POST'])
def upload_file():
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
    if "high" == image_quality:
        image_quality = '95'
    elif "medium" == image_quality:
        image_quality = '85'
    else:
        image_quality = '75'

    if watermark_type is None:
        return jsonify(error="Watermark style not selected!"), 400
    if file and allowed_file(file.filename):
        lang = request.args.get('lang', 'zh')
        timestamp = datetime.fromtimestamp(int(time.time())).strftime('%Y-%m-%d_%H-%M-%S')
        # 获取文件名和扩展名
        filename = secure_filename(file.filename)
        extension = filename.rsplit('.', 1)[1]

        # 生成带时间戳的文件名
        filename_with_timestamp = f"{filename.rsplit('.', 1)[0]}_{timestamp}.{extension}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename_with_timestamp)

        # 保存上传的文件
        file.save(filepath)

        # 处理图片（调用外部process.py脚本）
        try:
            # 确保传递正确的路径给 process.py
            result = subprocess.run(
                ['python3', 'process.py', filepath, lang, watermark_type, image_quality],
                capture_output=True, text=True
            )

            if result.returncode != 0:
                return jsonify(error=f'{result.stderr}'), 500

        except Exception as e:
            return jsonify(error=f'Error calling process.py: {str(e)}'), 500

        # 处理后的图片路径
        original_name, extension = os.path.splitext(filename_with_timestamp)
        processed_filename = f"{original_name}_watermark{extension}"

        # 返回图像的路径，带上 lang 和 burn 参数
        return jsonify({
            'processed_image': f'/upload/{processed_filename}?lang={lang}&burn={burn_after_read}'
        })

    return jsonify(error='Invalid file type'), 400

@app.route('/upload/<filename>')
def upload_file_served(filename):
    lang = request.args.get('lang', 'zh').split('?')[0]
    burn_after_read = request.args.get('burn', '0')

    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

    @after_this_request
    def delete_file(response):
        def delayed_delete():
            if str(burn_after_read).strip() == '1':
                time.sleep(10)
                if os.path.exists(file_path):
                    os.remove(file_path)

                original_file_path = os.path.join(
                    app.config['UPLOAD_FOLDER'], filename.split('_watermark')[0]
                )
                original_file_path = original_file_path + os.path.splitext(filename)[1]
                if os.path.exists(original_file_path):
                    os.remove(original_file_path)  # 删除原图    

        threading.Thread(target=delayed_delete).start()
        return response

    if not os.path.exists(file_path):
        # 根据 Accept 判断是浏览器访问还是下载请求
        accept = request.headers.get("Accept", "")
        if "text/html" in accept:
            return render_template(
                'image_deleted.html', lang=lang, translations=translations
            ), 404
        else:
            return jsonify(error="File not found"), 404

    return send_file(file_path)


# 专门的 not_found 页面，前端可主动跳转
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

    # 拼接打包文件名：Packed_Watermark_Images_{数量}_{时间}.zip
    count = len(filenames)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_filename = f"Packed_Watermark_Images_{count}_{timestamp}.zip"
    zip_path = os.path.join(tempfile.gettempdir(), zip_filename)

    try:
        with zipfile.ZipFile(zip_path, 'w') as zipf:
            for fname in filenames:
                full_path = os.path.join(app.config['UPLOAD_FOLDER'], fname)
                if os.path.exists(full_path):
                    zipf.write(full_path, arcname=fname)
    except Exception as e:
        return jsonify(error=str(e)), 500

    zip_url = f"/download_temp_zip/{zip_filename}"
    return jsonify(zip_url=zip_url)

# 提供 ZIP 文件下载
@app.route('/download_temp_zip/<filename>')
def download_temp_zip(filename):
    file_path = os.path.join(tempfile.gettempdir(), filename)
    if not os.path.exists(file_path):
        return "File not found", 404
    return send_file(file_path, as_attachment=True, download_name=filename)

if __name__ == '__main__':
    is_production = os.environ.get("FLASK_ENV") == "production"

    if is_production:
        # 生产环境不在这里启动，由 gunicorn 启动
        print("请使用 gunicorn 启动：gunicorn -w 4 -b 0.0.0.0:5000 app:app")
    else:
        # 本地开发模式：默认 localhost，仅开发使用
        app.run(host='0.0.0.0', port=5000, debug=True)