let currentLang = 'zh';
let translations = {};

fetch('/static/i18n/translations.json')
  .then(res => res.json())
  .then(data => {
    translations = data;
    switchLanguage(currentLang);
  });

function switchLanguage(lang) {
  currentLang = lang;
  const t = translations[lang];
  document.querySelector('h1').textContent = t.title;
  document.getElementById('uploadWarning').textContent = t.uploadWarn;
  document.querySelector('.custom-file-label').textContent = t.chooseFile;
  document.querySelector('h2:nth-of-type(1)').textContent = t.uploadedImage;
  document.querySelector('h2:nth-of-type(2)').textContent = t.watermarkTypes;
  document.querySelector('h2:nth-of-type(3)').textContent = t.processedImage;
  document.getElementById('processBtn').textContent = t.processImage;
  document.getElementById('burnAfterReadDivPrompt').textContent = t.burnAfterReadingText;
  document.getElementById('imgQuality').textContent = t.imageQuality;
  document.getElementById('highQ').textContent = t.highQuality;
  document.getElementById('mediumQ').textContent = t.mediumQuality;
  document.getElementById('lowQ').textContent = t.lowQuality;

  const label = document.querySelector('#burnAfterReadDiv label');
  if (label) label.textContent = t.burnAfterReading;

  document.getElementById('previewNote').textContent = '';
  document.getElementById('progressText').textContent = '';
}

document.getElementById('langZh').addEventListener('click', () => switchLanguage('zh'));
document.getElementById('langEn').addEventListener('click', () => switchLanguage('en'));

const fileInput = document.getElementById('fileInput');
const previewContainer = document.getElementById('previewContainer');
const resultContainer = document.getElementById('resultContainer');
const zipButton = document.getElementById('zipDownloadBtn');
const progressText = document.getElementById('progressText');
const previewNote = document.getElementById('previewNote');
const loader = document.getElementById('loader');

let processedFilenames = [];

fileInput.addEventListener('change', function () {
  const files = fileInput.files;
  previewContainer.innerHTML = '';
  resultContainer.innerHTML = '';
  progressText.textContent = '';
  previewNote.textContent = '';
  processedFilenames = [];
  zipButton.style.display = 'none';

  if (files.length === 0) {
    document.getElementById('processBtn').style.display = 'none';
    return;
  }

  // 只展示前 3 张预览图
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

  // 超过 3 张图时显示提示信息
  if (files.length > 3) {
    const rest = files.length - 3;
    previewNote.textContent = translations[currentLang].previewNote.replace('{rest}', rest);
  }

  document.getElementById('processBtn').style.display = 'inline';
});

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
  resultContainer.innerHTML = '';
  processedFilenames = [];
  zipButton.style.display = 'none';
  progressText.textContent = '';
  loader.style.display = 'block'; // Show loader

  let processedCount = 0;
  const totalFiles = files.length;

  const onComplete = () => {
    processedCount++;
    if (processedCount === totalFiles) {
      loader.style.display = 'none'; // Hide loader when all are done
    }
  };

  Array.from(files).forEach((file, index) => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('watermark_type', watermarkType);
    formData.append('image_quality', quality || 'high');
    formData.append('burn_after_read', burn);

    const progressTemplate = translations[currentLang].processingProgress;
    const progressInitialMessage = progressTemplate
      .replace('{done}', index)
      .replace('{total}', totalFiles);
    progressText.textContent = progressInitialMessage;

    fetch('/upload?lang=' + currentLang, {
      method: 'POST',
      body: formData
    })
      .then(res => res.json())
      .then(data => {
        if (data.error) {
          const error = document.createElement('div');
          error.textContent = file.name + ': ' + data.error;
          error.style.color = 'red';
          resultContainer.appendChild(error);
          onComplete(); // Mark as complete even on error
          return;
        }

        if (data.processed_image) {
          const processedName = data.processed_image.split('/').pop().split('?')[0];
          processedFilenames.push(processedName);

          if (isSingleImage || index < 3) {
            const wrapper = document.createElement('div');
            wrapper.style.textAlign = 'center';

            const img = document.createElement('img');
            img.src = data.processed_image + `?t=${Date.now()}`;
            img.style.maxWidth = '200px';
            img.style.maxHeight = '200px';
            wrapper.appendChild(img);
            if (isSingleImage) {
              const link = document.createElement('a');
              link.href = "#";
              link.textContent = translations[currentLang].downloadImage;
              link.style.display = 'block';
              link.style.marginTop = '6px';

              link.addEventListener('click', (e) => {
                e.preventDefault();
                fetch(data.processed_image)
                  .then(res => {
                    if (!res.ok) {
                      window.location.href = "/not_found?lang=" + currentLang;
                      throw new Error("File not found");
                    }
                    return res.blob();
                  })
                  .then(blob => {
                    const a = document.createElement("a");
                    a.href = URL.createObjectURL(blob);
                    a.download = file.name.replace(/\.[^/.]+$/, '') + '_watermark.jpg';
                    a.click();
                    URL.revokeObjectURL(a.href);
                  })
                  .catch(err => console.error(err));
              });

              wrapper.appendChild(link);
            }


            resultContainer.appendChild(wrapper);
          }

          const progressTemplate = translations[currentLang].processingProgress;
          const progressMessage = progressTemplate
            .replace('{done}', processedFilenames.length)
            .replace('{total}', files.length);
          progressText.textContent = progressMessage;

          if (!isSingleImage && processedFilenames.length === files.length) {
            zipButton.style.display = 'inline';
          }
        }
        onComplete(); // Mark as complete on success
      })
      .catch(err => {
        const error = document.createElement('div');
        error.textContent = file.name + ': ' + (err.message || 'Upload failed');
        error.style.color = 'red';
        resultContainer.appendChild(error);
        onComplete(); // Mark as complete on fetch error
      });
  });
});

zipButton.addEventListener('click', () => {
  if (processedFilenames.length === 0) return;

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
        alert('打包失败');
      }
    });
});
