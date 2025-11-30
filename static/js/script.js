/**
 * static/js/script.js
 * 完整版：包含异步任务轮询、交互式预览、多语言支持
 */

let currentLang = 'zh';
let translations = {};

// === 1. 初始化与多语言支持 ===

// 获取翻译文件
fetch('/static/i18n/translations.json')
  .then(res => res.json())
  .then(data => {
    translations = data;
    switchLanguage(currentLang);
  });

function switchLanguage(lang) {
  currentLang = lang;
  const t = translations[lang];
  if (!t) return;

  // 更新页面文本
  document.querySelector('h1').textContent = t.title;
  const uploadWarn = document.getElementById('uploadWarning');
  if (uploadWarn) uploadWarn.textContent = t.uploadWarn;
  
  document.querySelector('.custom-file-label').textContent = t.chooseFile;
  
  // 更新各个标题
  const h2s = document.querySelectorAll('h2');
  if (h2s.length > 0) h2s[0].textContent = t.uploadedImage;
  if (h2s.length > 1) h2s[1].textContent = t.watermarkTypes;
  if (h2s.length > 2) h2s[2].textContent = t.processedImage;

  document.getElementById('processBtn').textContent = t.processImage;
  document.getElementById('burnAfterReadDivPrompt').textContent = t.burnAfterReadingText;
  document.getElementById('imgQuality').textContent = t.imageQuality;
  document.getElementById('highQ').textContent = t.highQuality;
  document.getElementById('mediumQ').textContent = t.mediumQuality;
  document.getElementById('lowQ').textContent = t.lowQuality;

  const burnLabel = document.querySelector('#burnAfterReadDiv label');
  if (burnLabel) burnLabel.textContent = t.burnAfterReading;

  // 清空动态提示
  document.getElementById('previewNote').textContent = '';
  document.getElementById('progressText').textContent = '';
}

document.getElementById('langZh').addEventListener('click', () => switchLanguage('zh'));
document.getElementById('langEn').addEventListener('click', () => switchLanguage('en'));


// === 2. 全局变量与 DOM 元素 ===

const fileInput = document.getElementById('fileInput');
const previewContainer = document.getElementById('previewContainer');
const resultContainer = document.getElementById('resultContainer');
const zipButton = document.getElementById('zipDownloadBtn');
const progressText = document.getElementById('progressText');
const previewNote = document.getElementById('previewNote');
const loader = document.getElementById('loader');

let processedFilenames = [];
// 存储当前用于预览的源文件名（服务器上的文件名）
let currentSourceFilename = null;

// 存储当前的高级设置配置
let currentConfig = {
    font_ratio: 0.19,
    logo_ratio: 0.55,
    border_ratio: 0.25,
    item_spacing_ratio: 0.2
};


// === 3. 高级设置与实时预览逻辑 ===

// 防抖函数：避免滑块拖动时频繁请求
function debounce(func, wait) {
    let timeout;
    return function(...args) {
        clearTimeout(timeout);
        timeout = setTimeout(() => func.apply(this, args), wait);
    };
}

// 执行预览更新
const updatePreview = debounce(() => {
    // 只有当有图片处理成功，且页面上显示了结果图时，才进行预览更新
    if (!currentSourceFilename) return;
    
    // 找到结果区域的第一张图片（通常我们只预览第一张）
    const resultImg = document.querySelector('#resultContainer img');
    if (!resultImg) return;
    
    // 获取当前选中的水印类型
    const watermarkTypeInput = document.querySelector('input[name="watermark_type"]:checked');
    const watermarkType = watermarkTypeInput ? watermarkTypeInput.value : '1';
    
    // 构建查询参数
    const params = new URLSearchParams({
        filename: currentSourceFilename,
        watermark_type: watermarkType,
        ...currentConfig // 展开当前配置
    });
    
    // 更新图片 src，添加时间戳防止浏览器缓存
    // 注意：这里调用的是 /preview 接口，返回的是二进制流
    resultImg.src = `/preview?${params.toString()}&t=${Date.now()}`;
    
}, 300); // 300ms 延迟

// 绑定滑块事件
const sliders = ['font_ratio', 'logo_ratio', 'border_ratio', 'item_spacing_ratio'];
sliders.forEach(id => {
    const slider = document.getElementById(id);
    const labelSpan = document.getElementById('val_' + id);
    
    if (slider && labelSpan) {
        // 初始化显示的数值
        labelSpan.textContent = Math.round(slider.value * 100) + '%';
        
        slider.addEventListener('input', (e) => {
            const val = e.target.value;
            // 更新百分比显示
            labelSpan.textContent = Math.round(val * 100) + '%';
            // 更新配置对象
            currentConfig[id] = val;
            // 触发预览
            updatePreview();
        });
    }
});


// === 4. 文件选择与预处理 ===

fileInput.addEventListener('change', function () {
  const files = fileInput.files;
  
  // 重置界面状态
  previewContainer.innerHTML = '';
  resultContainer.innerHTML = '';
  progressText.textContent = '';
  previewNote.textContent = '';
  processedFilenames = [];
  currentSourceFilename = null; // 重置预览源
  zipButton.style.display = 'none';

  if (files.length === 0) {
    document.getElementById('processBtn').style.display = 'none';
    // 隐藏高级设置（可选）
    const advSettings = document.getElementById('advancedSettings');
    if(advSettings) advSettings.style.display = 'none';
    return;
  }

  // 显示高级设置面板
  const advSettings = document.getElementById('advancedSettings');
  if(advSettings) advSettings.style.display = 'block';

  // 预览前 3 张上传的图片
  Array.from(files).slice(0, 3).forEach(file => {
    const reader = new FileReader();
    reader.onload = function (e) {
      const img = document.createElement('img');
      img.src = e.target.result;
      img.style.maxWidth = '200px';
      img.style.maxHeight = '200px';
      img.style.border = '1px solid #ccc';
      img.style.padding = '4px';
      previewContainer.appendChild(img);
    };
    reader.readAsDataURL(file);
  });

  if (files.length > 3) {
    const rest = files.length - 3;
    if (translations[currentLang] && translations[currentLang].previewNote) {
        previewNote.textContent = translations[currentLang].previewNote.replace('{rest}', rest);
    }
  }

  document.getElementById('processBtn').style.display = 'inline';
});


// === 5. 核心处理逻辑 (Process Button) ===

document.getElementById('processBtn').addEventListener('click', function () {
  const files = fileInput.files;
  const isSingleImage = files.length === 1;

  const watermarkRadio = document.querySelector('input[name="watermark_type"]:checked');
  const quality = document.getElementById('imageQualitySelect').value;
  const burn = document.getElementById('burnAfterRead').checked ? 1 : 0;

  if (!watermarkRadio) {
    alert(translations[currentLang].alerts.selectWatermark);
    return;
  }

  const watermarkType = watermarkRadio.value;
  
  // 清空结果区域，准备显示新结果
  resultContainer.innerHTML = '';
  processedFilenames = [];
  currentSourceFilename = null;
  zipButton.style.display = 'none';
  progressText.textContent = '';
  loader.style.display = 'block';

  let processedCount = 0;
  const totalFiles = files.length;

  // 检查是否所有任务完成
  const checkAllCompleted = () => {
    processedCount++;
    
    const t = translations[currentLang];
    if (t && t.processingProgress) {
        const progressMessage = t.processingProgress
          .replace('{done}', processedFilenames.length) // 显示成功的数量
          .replace('{total}', totalFiles);
        progressText.textContent = progressMessage;
    }

    if (processedCount === totalFiles) {
      loader.style.display = 'none';
      if (!isSingleImage && processedFilenames.length > 0) {
        zipButton.style.display = 'inline';
      }
    }
  };

  // 渲染成功图片
  const renderSuccessImage = (processedImageUrl, sourceFilename, originalFile, index) => {
      // 记录第一个成功的文件名，用于实时预览
      if (!currentSourceFilename) {
          currentSourceFilename = sourceFilename;
      }

      const processedName = processedImageUrl.split('/').pop().split('?')[0];
      processedFilenames.push(processedName);

      // 仅展示前3张结果，或者是单图模式
      if (isSingleImage || index < 3) {
        const wrapper = document.createElement('div');
        wrapper.style.textAlign = 'center';
        wrapper.style.margin = '10px';
        wrapper.style.display = 'inline-block';
        wrapper.style.verticalAlign = 'top';

        const img = document.createElement('img');
        img.src = processedImageUrl + `&t=${Date.now()}`;
        img.style.maxWidth = '200px';
        img.style.maxHeight = '200px';
        img.style.boxShadow = '0 2px 5px rgba(0,0,0,0.1)';
        wrapper.appendChild(img);

        // 单图模式提供直接下载链接
        if (isSingleImage) {
          const link = document.createElement('a');
          link.href = "#";
          link.textContent = translations[currentLang].downloadImage;
          link.style.display = 'block';
          link.style.marginTop = '6px';
          
          // 点击下载逻辑
// 点击下载逻辑
          link.addEventListener('click', (e) => {
            e.preventDefault();
            
            // 获取下载链接（如果开启了预览，这通常是带参数的 URL）
            const downloadUrl = img.src; 

            fetch(downloadUrl)
              .then(res => {
                // === 关键修改 ===
                if (!res.ok) {
                    // 如果后端返回错误（如 404），直接让浏览器跳转到该 URL
                    // 此时浏览器会发送 Accept: text/html 请求
                    // 后端 app.py 检测到 text/html 请求且文件不存在，就会渲染 image_deleted.html
                    window.location.href = downloadUrl;
                    return null; // 中断后续 Promise 链
                }
                return res.blob();
              })
              .then(blob => {
                if (!blob) return; // 如果上面跳转了，这里直接返回

                // 正常下载流程：创建临时链接触发下载
                const a = document.createElement("a");
                a.href = URL.createObjectURL(blob);
                // 尝试提取原文件名并保留 _watermark 后缀
                a.download = originalFile.name.replace(/\.[^/.]+$/, '') + '_watermark.jpg';
                document.body.appendChild(a); // 兼容性修复：部分浏览器需要将节点加入 DOM 才能点击
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(a.href);
              })
              .catch(err => {
                console.error("Download error:", err);
                // 如果是网络错误等导致 fetch 完全失败，也可以选择尝试跳转
                // window.location.href = downloadUrl;
              });
          });
          wrapper.appendChild(link);
        }
        resultContainer.appendChild(wrapper);
      }
  };

  const renderError = (fileName, errorMessage) => {
    const error = document.createElement('div');
    error.textContent = fileName + ': ' + errorMessage;
    error.style.color = 'red';
    error.style.fontSize = '14px';
    resultContainer.appendChild(error);
  };

  // 轮询任务状态
  const pollTaskStatus = (taskId, file, index) => {
    const intervalId = setInterval(() => {
      fetch(`/status/${taskId}`)
        .then(res => res.json())
        .then(data => {
          if (data.status === 'succeeded') {
            clearInterval(intervalId);
            renderSuccessImage(
                data.result.processed_image, 
                data.result.source_filename, // 后端返回的源文件名
                file, 
                index
            );
            checkAllCompleted();
          } else if (data.status === 'failed') {
            clearInterval(intervalId);
            renderError(file.name, data.error || 'Unknown error');
            checkAllCompleted();
          } 
          // status 'queued' or 'processing' -> continue polling
        })
        .catch(err => {
          clearInterval(intervalId);
          renderError(file.name, "Network error");
          checkAllCompleted();
        });
    }, 1000); // 1秒轮询一次
  };

  // 遍历上传所有文件
  Array.from(files).forEach((file, index) => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('watermark_type', watermarkType);
    formData.append('image_quality', quality || 'high');
    formData.append('burn_after_read', burn);
    
    // 将当前的高级配置也传给后端
    Object.keys(currentConfig).forEach(key => {
        formData.append(key, currentConfig[key]);
    });

    // 初始化进度文字
    if (index === 0) {
        const t = translations[currentLang];
        if (t && t.processingProgress) {
            progressText.textContent = t.processingProgress
              .replace('{done}', 0)
              .replace('{total}', totalFiles);
        }
    }

    // 发起上传请求
    fetch('/upload?lang=' + currentLang, {
      method: 'POST',
      body: formData
    })
      .then(res => res.json())
      .then(data => {
        if (data.error) {
          renderError(file.name, data.error);
          checkAllCompleted();
        } else if (data.task_id) {
          // 上传成功，开始轮询
          pollTaskStatus(data.task_id, file, index);
        } else {
          renderError(file.name, "Unknown server response");
          checkAllCompleted();
        }
      })
      .catch(err => {
        renderError(file.name, err.message || 'Upload failed');
        checkAllCompleted();
      });
  });
});


// === 6. ZIP 打包下载 ===

zipButton.addEventListener('click', () => {
  if (processedFilenames.length === 0) return;

  // 提示：ZIP 打包的是初始处理的图片，不会包含仅在预览模式下调整的变更
  // 如果需要下载调整后的，用户应该点击"处理"按钮重新生成
  
  fetch('/download_zip', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      filenames: processedFilenames,
      lang: currentLang
    })
  })
    .then(res => res.json())
    .then(data => {
      if (data.zip_url) {
        const a = document.createElement('a');
        a.href = data.zip_url;
        a.download = 'images_with_watermarks.zip';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
      } else {
        alert(data.error || 'Packaging failed');
      }
    })
    .catch(err => {
        console.error(err);
        alert('Network error during zip download');
    });
});