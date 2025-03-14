
const watermarkSelection = document.querySelector('.watermark-selection');
const images = watermarkSelection.querySelectorAll('img');

watermarkSelection.addEventListener('scroll', function () {
    const scrollLeft = watermarkSelection.scrollLeft;
    const scrollWidth = watermarkSelection.scrollWidth;
    const clientWidth = watermarkSelection.clientWidth;

    // 滚动到最左边时隐藏最左边图片
    if (scrollLeft === 0) {
        labels[0].style.visibility = 'hidden';  // 最左边的图片消失
    } else {
        labels[0].style.visibility = 'visible'; // 恢复显示
    }

    // 滚动到最右边时隐藏最右边图片
    if (scrollLeft + clientWidth >= scrollWidth) {
        labels[labels.length - 1].style.visibility = 'hidden';  // 最右边的图片消失
    } else {
        labels[labels.length - 1].style.visibility = 'visible'; // 恢复显示
    }
});

const translations = {
    en: {
        title: "Image Watermark Web",
        uploadWarn: "Notice: The uploaded image will be stored on our server. Please consider carefully before uploading.",
        chooseFile: "Choose File",
        uploadedImage: "Uploaded Image",
        watermarkTypes: "Watermark types",
        burnAfterReading: "Burn After Reading",
        burnAfterReadingText: "If you check \"Burn After Reading\", \n your uploaded image and the watermarked image will be deleted within two minutes after processing is completed. Please download them in time.",
        processImage: "Process Image",
        processedImage: "Processed Image",
        downloadImage: "Download Processed Image",
        imageQuality: "Image Quality",
        highQuality: "High",
        mediumQuality: "Medium",
        lowQuality: "Low",
        alerts: {
            uploadSuccess: "Watemark added successfully!",
            uploadError: "Unexpected error occurred.",
            selectWatermark: "Please select a watermark style!"
        }
    },
    zh: {
        title: "边框水印",
        uploadWarn: "注意：上传的图片会被存储在我们的服务器上，请您自行斟酌。",
        chooseFile: "选择文件",
        uploadedImage: "已上传图片",
        watermarkTypes: "水印样式",
        burnAfterReading: "阅后即焚",
        burnAfterReadingText: "若您勾选“阅后即焚”，您上传的图片以及添加水印的图片将在处理完成两分钟内被删除，请您及时下载。",
        processImage: "开始添加水印",
        processedImage: "已添加水印的图片",
        downloadImage: "下载已添加水印的图片",
        imageQuality: "图像质量",
        highQuality: "高",
        mediumQuality: "中",
        lowQuality: "低",
        alerts: {
            uploadSuccess: "水印添加成功！",
            uploadError: "发生意外错误。",
            selectWatermark: "请选择一种水印样式！"
        }
    }
};

let currentLang = 'zh';

function switchLanguage(lang) {
    currentLang = lang;
    document.querySelector('h1').textContent = translations[lang].title;
    document.getElementById('uploadWarning').textContent = translations[lang].uploadWarn;
    document.querySelector('.custom-file-label').textContent = translations[lang].chooseFile;
    document.querySelector('h2:nth-of-type(1)').textContent = translations[lang].uploadedImage;
    document.querySelector('h2:nth-of-type(2)').textContent = translations[lang].watermarkTypes;
    document.getElementById('processBtn').textContent = translations[lang].processImage;
    document.querySelector('h2:nth-of-type(3)').textContent = translations[lang].processedImage;
    document.getElementById('downloadBtn').textContent = translations[lang].downloadImage;
    document.getElementById('burnAfterReadDivPrompt').textContent = translations[lang].burnAfterReadingText;
    document.getElementById('imgQuality').textContent = translations[lang].imageQuality;
    document.getElementById('highQ').textContent = translations[lang].highQuality;
    document.getElementById('mediumQ').textContent = translations[lang].mediumQuality;
    document.getElementById('lowQ').textContent = translations[lang].lowQuality;

    const burnAfterReadLabel = document.querySelector('#burnAfterReadDiv label');
    if (burnAfterReadLabel) {
        burnAfterReadLabel.textContent = translations[lang].burnAfterReading;
    }
}

document.getElementById('langEn').addEventListener('click', () => switchLanguage('en'));
document.getElementById('langZh').addEventListener('click', () => switchLanguage('zh'));

let selectedFile = null;

// 文件选择事件
document.getElementById('fileInput').addEventListener('change', function (event) {
    const file = event.target.files[0];
    if (file) {
        selectedFile = file;

        document.getElementById('imagePreview').style.display = 'none';
        document.getElementById('processBtn').style.display = 'none';
        document.getElementById('processedImage').style.display = 'none';
        document.getElementById('downloadBtn').style.display = 'none';
        document.getElementById('imageQuality').style.display = 'none';

        const reader = new FileReader();
        reader.onload = function (e) {
            const imagePreview = document.getElementById('imagePreview');
            imagePreview.src = e.target.result;
            imagePreview.style.display = 'block';
            document.getElementById('processBtn').style.display = 'inline';
            document.getElementById('imageQuality').style.display = 'flex';
        };
        reader.readAsDataURL(file);
    }
});

let selectedQuality = null;
let selectedWatermark = null;
let burnAfterRead = null;

const qualitySelect = document.getElementById('imageQualitySelect');
qualitySelect.addEventListener('change', function () {
    selectedQuality = qualitySelect.value;
    console.log('Selected quality:', selectedQuality);
});

const watermarkRadios = document.querySelectorAll('input[name="watermark_type"]');
watermarkRadios.forEach(radio => {
    radio.addEventListener('change', function () {
        selectedWatermark = this.value;  // 选中后更新水印类型
    });
});

const burnAfterReadCheckbox = document.getElementById('burnAfterRead');
burnAfterReadCheckbox.addEventListener('change', function () {
    const isChecked = burnAfterReadCheckbox.checked;  // 获取复选框的选中状态
    burnAfterRead = isChecked ? 1 : 0;  // 选中后更新是否删除上传的图片
    console.log('Burn After Reading:', burnAfterRead);
});

document.getElementById('processBtn').addEventListener('click', function () {
    document.getElementById('loader').style.display = 'block';
    document.getElementById('processedImage').style.display = 'none';
    document.getElementById('downloadBtn').style.display = 'none';

    if (!selectedWatermark) {
        alert(translations[currentLang].alerts.selectWatermark);
        document.getElementById('loader').style.display = 'none';
        return;
    }

    const formData = new FormData();
    formData.append("file", selectedFile);
    formData.append("watermark_type", selectedWatermark);
    formData.append("burn_after_read", burnAfterRead);
    formData.append("image_quality", selectedQuality || "high");

    fetch('/upload?lang=' + currentLang, {
        method: 'POST',
        body: formData
    })
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                alert(data.error);
                document.getElementById('loader').style.display = 'none';
                return;
            }
            if (data.processed_image) {
                const processedImage = document.getElementById('processedImage');
                const timestamp = new Date().getTime();
                processedImage.src = `${data.processed_image}?t=${timestamp}`;
                
                // 确保图片加载完成后再显示
                processedImage.onload = function () {
                    processedImage.style.display = 'block';

                    const downloadBtn = document.getElementById('downloadBtn');
                    downloadBtn.href = data.processed_image;
                    const originalName = selectedFile.name.split('.').slice(0, -1).join('.');
                    const extension = selectedFile.name.split('.').pop();
                    downloadBtn.download = `${originalName}_watermark.${extension}`;
                    downloadBtn.style.display = 'inline';

                    document.getElementById('loader').style.display = 'none';
                    alert(translations[currentLang].alerts.uploadSuccess);
                };
            } else {
                document.getElementById('loader').style.display = 'none';
                alert(translations[currentLang].alerts.uploadError);
            }
        })
        .catch(error => {
            alert(translations[currentLang].alerts.uploadError);
            console.error('Error uploading image:', error);
            document.getElementById('loader').style.display = 'none';
        });
});

document.addEventListener('DOMContentLoaded', () => {
    switchLanguage('zh');  // 默认语言
});