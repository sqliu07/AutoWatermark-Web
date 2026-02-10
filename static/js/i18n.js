// static/js/i18n.js

(function () {
  const i18n = {
    zh: {
      appName: "边框水印",
      title: "为照片赋予专业感",
      subtitle: "智能识别 EXIF 信息，一键生成水印相框。",

      dragText: "点击或拖拽上传照片",
      selected: "已选择 {n} 张",
      btnChange: "更换图片",

      styleTitle: "水印风格",
      descStyle1: "拍立得",
      descStyle2: "经典双行",
      descStyle3: "居中极简",
      descStyle4: "毛玻璃特效",

      qualityTitle: "输出画质",
      qualityHigh: "高",
      qualityMedium: "中",
      qualityLow: "低",

      xiaomiLogoTitle: "选择 Logo",
      xiaomiLogoMessage: "检测到 Xiaomi 机型，请选择要使用的 Logo。",
      xiaomiLogoOptionXiaomi: "Xiaomi",
      xiaomiLogoOptionLeica: "Leica",

      privacyTitle: "隐私设置",
      burnTitle: "阅后即焚",
      burnDesc: "闲置 2 分钟后自动销毁文件",

      btnProcess: "开始处理",
      btnProcessing: "处理中...",
      btnZip: "打包下载所有图片",
      selectWatermark: "请选择一种水印样式！",

      statusUploading: "正在上传...",
      statusProcessing: "处理中...",
      statusDone: "处理完成",
      statusSuccess: "成功",

      btnDownload: "下载原图",
      btnPreview: "全屏预览",
      morePreviews: "+ {n} 张",
      moreResults: "剩余 {n} 张图片已隐藏，请打包下载",

      imageDeleted: "图片已删除",
      imageDeletedMessage: "该图片已被成功删除，无法再次访问。",
      backToHome: "返回首页"
    },

    en: {
      appName: "AutoWatermark Web",
      title: "Professional Watermarks",
      subtitle: "Auto-generate watermarked frames from EXIF data.",

      dragText: "Click or Drag to Upload",
      selected: "{n} Selected",
      btnChange: "Change",

      styleTitle: "Watermark Style",
      descStyle1: "Polaroid Style",
      descStyle2: "Classic Layout",
      descStyle3: "Minimal Center",
      descStyle4: "Frosted Glass",

      qualityTitle: "Image Quality",
      qualityHigh: "High",
      qualityMedium: "Medium",
      qualityLow: "Low",

      xiaomiLogoTitle: "Choose Logo",
      xiaomiLogoMessage: "Xiaomi detected. Choose which logo to use.",
      xiaomiLogoOptionXiaomi: "Xiaomi",
      xiaomiLogoOptionLeica: "Leica",

      privacyTitle: "Privacy",
      burnTitle: "Burn After Read",
      burnDesc: "Files deleted after 2 mins of inactivity",

      btnProcess: "Process Images",
      btnProcessing: "Processing...",
      btnZip: "Download All as ZIP",
      selectWatermark: "Please select a watermark style.",

      statusUploading: "Uploading...",
      statusProcessing: "Processing...",
      statusDone: "Completed",
      statusSuccess: "Success",

      btnDownload: "Download",
      btnPreview: "Preview",
      morePreviews: "+ {n} more",
      moreResults: "{n} more images hidden, please download ZIP",

      imageDeleted: "Image deleted",
      imageDeletedMessage: "The image has been deleted.",
      backToHome: "Back to Home"
    }
  };

  function getInitialLang() {
    const urlLang = new URLSearchParams(window.location.search).get("lang");
    if (urlLang && i18n[urlLang]) return urlLang;

    const saved = localStorage.getItem("lang");
    if (saved && i18n[saved]) return saved;

    return "zh";
  }

  function setLang(lang) {
    if (!i18n[lang]) return;
    localStorage.setItem("lang", lang);
    window.currentLang = lang;
    window.t = i18n[lang];
  }

  window.initI18n = function () {
    setLang(getInitialLang());
  };

  window.switchLang = function (lang) {
    setLang(lang);
    if (typeof window.applyI18n === "function") {
      window.applyI18n();
    }
  };

  window.i18nData = i18n;
})();
