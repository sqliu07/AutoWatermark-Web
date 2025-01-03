import os
import time
from datetime import datetime

from flask import Flask, after_this_request, request, render_template, jsonify, send_file, abort
import subprocess
from werkzeug.utils import secure_filename
import threading

app = Flask(__name__, static_url_path='/static', static_folder='./static')

# 确保上传文件夹存在
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

# 语言翻译字典
translations = {
    'en': {
        'title': "Image Deleted",
        'imageDeleted': "The image has been deleted",
        'imageDeletedMessage': "Sorry, the image you requested has been deleted or does not exist."
    },
    'zh': {
        'title': "图片已删除",
        'imageDeleted': "图片已被删除",
        'imageDeletedMessage': "抱歉，您请求的图片已被删除或不存在。"
    }
}

burn_after_read = '1'

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
    global burn_after_read
    burn_after_read = request.form.get('burn_after_read', '0')
    
    if watermark_type is None:
        return jsonify(error="Watermark style not selected!"), 400
    if file and allowed_file(file.filename):
        lang = request.args.get('lang', 'zh')
        print("current language: " + lang)
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
        original_name, extension = os.path.splitext(filename_with_timestamp)
        processed_filename = f"{original_name}_watermark{extension}"

        # 返回图像的路径，带上 lang 查询参数
        return jsonify({
            'processed_image': f'/uploads/{processed_filename}?lang={lang}'
        })
    
    return jsonify(error='Invalid file type'), 400

@app.route('/uploads/<filename>')
def upload_file_served(filename):
    # 获取 lang 参数并去除查询字符串部分
    lang = request.args.get('lang', 'zh').split('?')[0]

    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

    @after_this_request
    def delete_file(response):
        def delayed_delete():
            if burn_after_read == '1':  # 如果 burn_after_read 为 True，则延时10秒后删除文件
                time.sleep(120)
                if os.path.exists(file_path):
                    os.remove(file_path)
                    
                original_file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename.split('_watermark')[0])
                original_file_path = original_file_path + os.path.splitext(filename)[1]
                print(f"Delete original file: {original_file_path}")
                if os.path.exists(original_file_path):
                    os.remove(original_file_path)  # 删除原图    

        # 启动一个线程来延时删除文件
        threading.Thread(target=delayed_delete).start()

        return response

    if not os.path.exists(file_path):
        print("lang from path:", lang)  # 打印 lang 参数，确保它正确传递
        return render_template('image_deleted.html', lang=lang, translations=translations)
    
    return send_file(file_path)

if __name__ == '__main__':
    app.run(debug=False)