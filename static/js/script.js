document.addEventListener('DOMContentLoaded', () => {
    initI18n();
    function t() {
        return window.t;
    }
    // === DOM 元素 ===
    const dropZone = document.getElementById('drop-zone');
    const uploadPrompt = document.getElementById('upload-prompt');
    const previewGallery = document.getElementById('preview-gallery');
    
    const fileInput = document.getElementById('file-input');
    const uploadBtn = document.getElementById('upload-btn');
    const resultContainer = document.getElementById('result-container');
    
    // 进度条
    const progressArea = document.getElementById('progress-area');
    const progressBar = document.getElementById('progress-bar');
    const progressPercent = document.getElementById('progress-percent');
    const statusTextLabel = document.getElementById('ui-status-uploading');
    
    // 状态栏
    const fileInfo = document.getElementById('file-info');
    const selectedCount = document.getElementById('selected-count');
    const reselectBtn = document.getElementById('reselect-btn');
    const btnChangeText = document.getElementById('ui-btn-change');
    
    const downloadAllArea = document.getElementById('download-all-area');
    const zipBtn = document.getElementById('zip-btn');
    const langZhBtn = document.getElementById('lang-zh');
    const langEnBtn = document.getElementById('lang-en');

    // === 状态 ===
    let currentFiles = [];
    let processedFilenames = [];

    function switchLanguage(lang) {
        switchLang(lang);
        const t = window.t;

        if(lang === 'zh') {
            langZhBtn.classList.add('text-brand-600', 'font-semibold');
            langZhBtn.classList.remove('text-slate-500');
            langEnBtn.classList.add('text-slate-500');
            langEnBtn.classList.remove('text-brand-600', 'font-semibold');
        } else {
            langEnBtn.classList.add('text-brand-600', 'font-semibold');
            langEnBtn.classList.remove('text-slate-500');
            langZhBtn.classList.add('text-slate-500');
            langZhBtn.classList.remove('text-brand-600', 'font-semibold');
        }

        document.getElementById('ui-app-name').textContent = t.appName;
        document.getElementById('ui-title').textContent = t.title;
        document.getElementById('ui-subtitle').textContent = t.subtitle;
        document.getElementById('ui-drag-text').textContent = t.dragText;
        document.getElementById('ui-style-title').textContent = t.styleTitle;
        document.getElementById('reselect-btn').textContent = t.btnChange;
        
        if(document.getElementById('desc-style-1')) document.getElementById('desc-style-1').textContent = t.descStyle1;
        if(document.getElementById('desc-style-2')) document.getElementById('desc-style-2').textContent = t.descStyle2;
        if(document.getElementById('desc-style-3')) document.getElementById('desc-style-3').textContent = t.descStyle3;
        if(document.getElementById('desc-style-4')) document.getElementById('desc-style-4').textContent = t.descStyle4;

        document.getElementById('ui-quality-title').textContent = t.qualityTitle;
        document.getElementById('ui-quality-high').textContent = t.qualityHigh;
        document.getElementById('ui-quality-medium').textContent = t.qualityMedium;
        document.getElementById('ui-quality-low').textContent = t.qualityLow;
        document.getElementById('ui-xiaomi-logo-title').textContent = t.xiaomiLogoTitle;
        document.getElementById('ui-xiaomi-logo-xiaomi').textContent = t.xiaomiLogoXiaomi;
        document.getElementById('ui-xiaomi-logo-leica').textContent = t.xiaomiLogoLeica;
        document.getElementById('ui-xiaomi-logo-hint').textContent = t.xiaomiLogoHint;
        document.getElementById('ui-privacy-title').textContent = t.privacyTitle;
        document.getElementById('ui-burn-title').textContent = t.burnTitle;
        document.getElementById('ui-burn-desc').textContent = t.burnDesc;
        document.getElementById('ui-btn-process').textContent = t.btnProcess;
        document.getElementById('ui-btn-zip').textContent = t.btnZip;
        
        if(btnChangeText) btnChangeText.textContent = t.btnChange;

        if (currentFiles.length > 0) {
            selectedCount.textContent = t.selected.replace('{n}', currentFiles.length);
        }
    }

    langZhBtn.addEventListener('click', () => {
        if (window.currentLang !== 'zh') {
            switchLanguage('zh');
        }
    });
    
    langEnBtn.addEventListener('click', () => {
        if (window.currentLang !== 'en') {
            switchLanguage('en');
        }
    });


    // === 文件交互 ===
    dropZone.addEventListener('click', (e) => {
        if (e.target !== reselectBtn && !reselectBtn.contains(e.target)) {
            fileInput.click();
        }
    });

    fileInput.addEventListener('change', (e) => handleFiles(e.target.files));

    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
        }, false);
    });

    ['dragenter', 'dragover'].forEach(eventName => {
        dropZone.addEventListener(eventName, () => dropZone.classList.add('border-brand-500', 'bg-blue-50/50'));
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, () => dropZone.classList.remove('border-brand-500', 'bg-blue-50/50'));
    });

    dropZone.addEventListener('drop', (e) => handleFiles(e.dataTransfer.files));

    function handleFiles(files) {
        if (files.length > 0) {
            currentFiles = Array.from(files);
            generatePreviews(currentFiles); 
            updateUIState(true);
        }
    }

    // === 预览逻辑修正 ===
    function generatePreviews(files) {
        previewGallery.innerHTML = ''; 
        previewGallery.className = "hidden w-full p-6 z-10"; 
        
        const displayLimit = 3;
        const totalCount = files.length;
        const showCount = Math.min(totalCount, displayLimit);

        if (totalCount === 1) {
            previewGallery.classList.add('flex', 'items-center', 'justify-center', 'min-h-[320px]');
        } else {
            previewGallery.classList.add('grid', 'grid-cols-1', 'sm:grid-cols-2', 'gap-6', 'content-start');
        }

        // 只循环前3个文件读取
        for (let i = 0; i < showCount; i++) {
            const file = files[i];
            const reader = new FileReader();
            reader.onload = (e) => {
                const widthClass = totalCount === 1 ? 'w-full max-w-2xl' : 'w-full';
                const imgContainer = document.createElement('div');
                imgContainer.className = `${widthClass} relative aspect-[4/3] rounded-xl overflow-hidden bg-white shadow-md border border-slate-200 fade-in flex items-center justify-center`;
                
                const img = document.createElement('img');
                img.src = e.target.result;
                img.className = "max-w-full max-h-full object-contain";
                
                imgContainer.appendChild(img);
                previewGallery.appendChild(imgContainer);
            };
            reader.readAsDataURL(file);
        }

        // 如果超过3个，显示 "+N" 卡片
        if (totalCount > displayLimit) {
            const moreCount = totalCount - displayLimit;
            const t = window.t;
            
            const moreCard = document.createElement('div');
            moreCard.className = "w-full relative aspect-[4/3] rounded-xl overflow-hidden bg-slate-100 shadow-sm border border-slate-200 fade-in flex items-center justify-center";
            
            const text = document.createElement('span');
            text.className = "text-xl font-bold text-slate-400";
            text.textContent = t.morePreviews.replace('{n}', moreCount);
            
            moreCard.appendChild(text);
            previewGallery.appendChild(moreCard);
        }
    }

    reselectBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        fileInput.value = '';
        currentFiles = [];
        previewGallery.innerHTML = ''; 
        updateUIState(false);
        fileInput.click();
    });

    function updateUIState(hasFiles) {
        const t = window.t;
        if (hasFiles) {
            uploadPrompt.classList.add('hidden');
            previewGallery.classList.remove('hidden');
            fileInfo.classList.remove('hidden');
            requestAnimationFrame(() => fileInfo.classList.remove('translate-y-2', 'opacity-0'));
            selectedCount.textContent = t.selected.replace('{n}', currentFiles.length);
            uploadBtn.disabled = false;
        } else {
            uploadPrompt.classList.remove('hidden');
            previewGallery.classList.add('hidden');
            fileInfo.classList.add('translate-y-2', 'opacity-0');
            setTimeout(() => fileInfo.classList.add('hidden'), 300);
            uploadBtn.disabled = true;
        }
    }

    // === 上传与处理 ===
    uploadBtn.addEventListener('click', async () => {
        if (currentFiles.length === 0) return;

        resultContainer.innerHTML = '';
        downloadAllArea.classList.add('hidden');
        progressArea.classList.remove('hidden');
        
        // 进度条归零
        progressBar.classList.remove('transition-all', 'duration-300');
        progressBar.style.width = '0%';
        progressPercent.textContent = '0%';
        progressBar.offsetHeight; 
        progressBar.classList.add('transition-all', 'duration-300');
        
        if(statusTextLabel) statusTextLabel.textContent = window.t.statusProcessing;

        uploadBtn.disabled = true;
        uploadBtn.querySelector('span').textContent = window.t.btnProcessing;
        
        processedFilenames = [];
        let completedCount = 0;
        displayedResultCount = 0;
        const total = currentFiles.length;

        const watermarkType = document.querySelector('input[name="watermark_type"]:checked').value;
        const quality = document.querySelector('input[name="image_quality"]:checked').value;
        const logoPreference = document.querySelector('input[name="logo_preference"]:checked')?.value || 'xiaomi';
        const burn = document.getElementById('burn_after_read').checked ? '1' : '0';

        const promises = currentFiles.map((file) => {
            const formData = new FormData();
            formData.append('file', file);
            formData.append('watermark_type', watermarkType);
            formData.append('image_quality', quality);
            formData.append('logo_preference', logoPreference);
            formData.append('burn_after_read', burn);

            return fetch(`/upload?lang=${currentLang}`, {
                method: 'POST',
                body: formData
            })
            .then(res => res.json())
            .then(data => {
                if (data.task_id) {
                    pollTask(data.task_id, file.name);
                } else {
                    renderError(file.name, data.error || 'Upload Failed');
                    markCompleted();
                }
            })
            .catch(err => {
                renderError(file.name, 'Network Error');
                markCompleted();
            });
        });

        function markCompleted() {
            completedCount++;
            const percent = Math.round((completedCount / total) * 100);
            progressBar.style.width = `${percent}%`;
            progressPercent.textContent = `${percent}%`;

            if (completedCount === total) {
                if(statusTextLabel) statusTextLabel.textContent = window.t.statusDone;
                uploadBtn.disabled = false;
                uploadBtn.querySelector('span').textContent = window.t.btnProcess;
                if(processedFilenames.length > 0) {
                    downloadAllArea.classList.remove('hidden');
                }

                // 如果超过3张，显示提示信息
                if (processedFilenames.length > 3) {
                      renderHiddenNotice(processedFilenames.length - 3);
                }
            }
        }

        function pollTask(taskId, fileName) {
            const interval = setInterval(() => {
                fetch(`/status/${taskId}`)
                    .then(res => res.json())
                    .then(task => {
                        if (task.status === 'succeeded') {
                            clearInterval(interval);
                            const imgUrl = task.result.processed_image;
                            const cleanUrl = imgUrl.split('?')[0]; 
                            const serverFileName = cleanUrl.substring(cleanUrl.lastIndexOf('/') + 1);
                            processedFilenames.push(serverFileName);
                            if (displayedResultCount < 3) {
                                renderSuccess(fileName, imgUrl);
                                displayedResultCount++;
                            }
                            markCompleted();
                        } else if (task.status === 'failed') {
                            clearInterval(interval);
                            renderError(fileName, task.error);
                            markCompleted();
                        }
                    })
                    .catch(() => {
                        clearInterval(interval);
                        renderError(fileName, 'Polling Error');
                        markCompleted();
                    });
            }, 1000);
        }
    });

    function renderSuccess(originalName, url) {
        const t = window.t;
        const div = document.createElement('div');
        div.className = "bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden fade-in";
        div.innerHTML = `
            <div class="relative group bg-slate-100 aspect-[4/3] flex items-center justify-center overflow-hidden">
                <img src="${url}" class="max-w-full max-h-full object-contain shadow-sm" alt="${originalName}">
                <div class="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center gap-4 backdrop-blur-[2px]">
                    <a href="${url}" target="_blank" class="px-4 py-2 bg-white text-slate-900 rounded-full text-sm font-bold hover:scale-105 transition-transform">
                        ${t.btnPreview}
                    </a>
                    <a href="${url}" download="${originalName}_watermark" class="px-4 py-2 bg-brand-600 text-white rounded-full text-sm font-bold hover:scale-105 transition-transform">
                        ${t.btnDownload}
                    </a>
                </div>
            </div>
            <div class="p-4 flex items-center justify-between">
                <div class="truncate text-sm font-medium text-slate-700 max-w-[70%]">${originalName}</div>
                <div class="flex gap-2">
                     <span class="text-xs px-2 py-1 bg-green-100 text-green-700 rounded-md">${t.statusSuccess}</span>
                </div>
            </div>
        `;
        resultContainer.appendChild(div);
    }
    function renderHiddenNotice(count) {
        const t = window.t;
        const div = document.createElement('div');
        div.className = "text-center py-6 fade-in";
        div.innerHTML = `
            <p class="text-slate-400 text-sm bg-slate-50 inline-block px-4 py-2 rounded-full">
                ${t.moreResults.replace('{n}', count)}
            </p>
        `;
        resultContainer.appendChild(div);
    }
    function renderError(originalName, errorMsg) {
        const div = document.createElement('div');
        div.className = "bg-white rounded-xl shadow-sm border border-red-100 p-4 flex items-center gap-4 fade-in";
        div.innerHTML = `
            <div class="w-10 h-10 bg-red-50 rounded-full flex items-center justify-center flex-shrink-0">
                <svg class="w-5 h-5 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
            </div>
            <div class="min-w-0 flex-1">
                <p class="text-sm font-bold text-slate-900">${originalName}</p>
                <p class="text-xs text-red-500 truncate">${errorMsg}</p>
            </div>
        `;
        resultContainer.appendChild(div);
    }

    zipBtn.addEventListener('click', () => {
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
                a.download = `Watermarked_Images.zip`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
            }
        });
    });

    switchLanguage('zh');
});
