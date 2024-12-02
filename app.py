import os
import time
from flask import Flask, request, redirect, render_template, jsonify, send_from_directory
import subprocess
from werkzeug.utils import secure_filename

app = Flask(__name__)

UPLOAD_FOLDER = './uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif'}
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 设置最大文件大小限制（例如 16MB）

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
        return jsonify(error="No file part"), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify(error="No selected file"), 400
    
    if file and allowed_file(file.filename):
        timestamp = int(time.time())
        
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
                ['python3', 'process.py', filepath],
                capture_output=True, text=True
            )

            if result.returncode != 0:
                return jsonify(error=f'Error processing file: {result.stderr}'), 500

        except Exception as e:
            return jsonify(error=f'Error calling process.py: {str(e)}'), 500
        
        # 处理后的图片路径
        processed_filename = filename_with_timestamp.replace('.jpg', '_watermark.jpg')
        processed_filepath = os.path.join(app.config['UPLOAD_FOLDER'], processed_filename)

        # 返回原图和处理后的图像路径
        return jsonify({
            'processed_image': f'/uploads/{processed_filename}'
        })
    
    return jsonify(error='Invalid file type'), 400

@app.route('/uploads/<filename>')
def upload_file_served(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

if __name__ == '__main__':
    app.run(debug=True)
