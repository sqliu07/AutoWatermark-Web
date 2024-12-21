import os
import time
from datetime import datetime

from flask import Flask, request, render_template, jsonify, send_from_directory
import subprocess
from werkzeug.utils import secure_filename

app = Flask(__name__, static_url_path='/types', static_folder='./types')

UPLOAD_FOLDER = './uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg'}
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 设置最大文件大小限制（例如 100MB）

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

def get_message(key, lang='zh'):
    return ERROR_MESSAGES.get(key, {}).get(lang)

# 确保上传文件夹存在
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    """检查文件扩展名是否允许"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

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
    if watermark_type is None:
        return jsonify(error="Watermark style not selected!"), 400
    if file and allowed_file(file.filename):
        lang = request.args.get('lang', 'zh')
        timestamp = int(time.time())
        timestamp = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d_%H-%M-%S')
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
                ['python3', 'process.py', filepath, lang, watermark_type],
                capture_output=True, text=True
            )


            if result.returncode != 0:
                return jsonify(error=f'{result.stderr}'), 500

        except Exception as e:
            return jsonify(error=f'Error calling process.py' + str(e)), 500
        
        # 处理后的图片路径
        # processed_filename = filename_with_timestamp.replace('.jpg', '_watermark.jpg')
        original_name, extension = os.path.splitext(filename_with_timestamp)
        processed_filename = f"{original_name}_watermark{extension}"

        # 返回原图和处理后的图像路径
        return jsonify({
            'processed_image': f'/uploads/{processed_filename}'
        })
    
    return jsonify(error='Invalid file type'), 400

@app.route('/uploads/<filename>')
def upload_file_served(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

if __name__ == '__main__':
    app.run(debug=False)
