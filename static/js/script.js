
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
        chooseFile: "Choose File",
        uploadedImage: "Uploaded Image",
        watermarkTypes: "Watermark types",
        processImage: "Process Image",
        processedImage: "Processed Image",
        downloadImage: "Download Processed Image",
        alerts: {
            uploadSuccess: "Watemark added successfully!",
            uploadError: "Unexpected error occurred.",
            selectWatermark: "Please select a watermark style!"
        }
    },
    zh: {
        title: "边框水印",
        chooseFile: "选择文件",
        uploadedImage: "已上传图片",
        watermarkTypes: "水印样式",
        processImage: "开始添加水印",
        processedImage: "已添加水印的图片",
        downloadImage: "下载已添加水印的图片",
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
    document.querySelector('.custom-file-label').textContent = translations[lang].chooseFile;
    document.querySelector('h2:nth-of-type(1)').textContent = translations[lang].uploadedImage;
    document.querySelector('h2:nth-of-type(2)').textContent = translations[lang].watermarkTypes;
    document.getElementById('processBtn').textContent = translations[lang].processImage;
    document.querySelector('h2:nth-of-type(3)').textContent = translations[lang].processedImage;
    document.getElementById('downloadBtn').textContent = translations[lang].downloadImage;
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

        const reader = new FileReader();
        reader.onload = function (e) {
            const imagePreview = document.getElementById('imagePreview');
            imagePreview.src = e.target.result;
            imagePreview.style.display = 'block';
            document.getElementById('processBtn').style.display = 'inline';
        };
        reader.readAsDataURL(file);
    }
});

let selectedWatermark = null;

const watermarkRadios = document.querySelectorAll('input[name="watermark_type"]');
watermarkRadios.forEach(radio => {
    radio.addEventListener('change', function () {
        selectedWatermark = this.value;  // 选中后更新水印类型
    });
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