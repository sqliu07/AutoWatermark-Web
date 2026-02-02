<template>
  <a-config-provider :theme="theme">
    <a-layout class="app-shell">
      <a-layout-header class="app-header">
        <div class="brand">AutoWatermark Web</div>
        <a-space>
          <a-button type="text" class="lang-button" ghost>中文</a-button>
          <span class="lang-divider">/</span>
          <a-button type="text" class="lang-button" ghost>English</a-button>
        </a-space>
      </a-layout-header>

      <a-layout-content class="app-content">
        <section class="hero">
          <h1>为照片赋予专业感</h1>
          <p>智能识别 EXIF 信息，一键生成水印参数相框。</p>
        </section>

        <a-card class="upload-card" bordered>
          <a-space direction="vertical" size="large" class="upload-area">
            <div class="upload-icon">
              <a-avatar size="large" shape="circle">
                <template #icon>
                  <span>📸</span>
                </template>
              </a-avatar>
            </div>
            <div>
              <div class="upload-title">点击或拖拽上传照片</div>
              <div class="upload-subtitle">支持批量上传，自动生成水印相框。</div>
            </div>
            <a-button type="primary" size="large">选择图片</a-button>
          </a-space>
        </a-card>

        <a-row :gutter="24" class="section">
          <a-col :xs="24" :lg="16">
            <h3 class="section-title">水印风格</h3>
            <a-row :gutter="16">
              <a-col :xs="24" :sm="12" v-for="style in styles" :key="style.key">
                <a-card class="style-card" hoverable>
                  <a-space>
                    <a-avatar shape="square" size="large">{{ style.badge }}</a-avatar>
                    <div>
                      <div class="style-name">{{ style.title }}</div>
                      <div class="style-desc">{{ style.desc }}</div>
                    </div>
                  </a-space>
                </a-card>
              </a-col>
            </a-row>
          </a-col>
          <a-col :xs="24" :lg="8">
            <div class="section">
              <h3 class="section-title">输出画质</h3>
              <a-segmented :options="qualityOptions" block />
            </div>
            <div class="section">
              <h3 class="section-title">隐私设置</h3>
              <a-card class="privacy-card">
                <a-space direction="vertical">
                  <div class="privacy-title">阅后即焚</div>
                  <div class="privacy-desc">闲置 2 分钟后自动销毁文件</div>
                  <a-switch />
                </a-space>
              </a-card>
            </div>
          </a-col>
        </a-row>

        <a-button type="primary" size="large" block class="primary-action">
          开始处理
        </a-button>
      </a-layout-content>
    </a-layout>
  </a-config-provider>
</template>

<script setup>
const theme = {
  token: {
    colorPrimary: '#1d4ed8',
    borderRadius: 12,
    fontFamily: 'Inter, "Helvetica Neue", Arial, sans-serif'
  }
};

const styles = [
  { key: 'style-1', badge: 'I', title: '拍立得', desc: '宽底边留白，复古相框感。' },
  { key: 'style-2', badge: 'II', title: '经典双行', desc: '左右分区展示拍摄参数。' },
  { key: 'style-3', badge: 'III', title: '居中极简', desc: '轻量布局，视觉更集中。' },
  { key: 'style-4', badge: 'IV', title: '毛玻璃特效', desc: '玻璃质感，自动适配明暗。' }
];

const qualityOptions = ['高', '中', '低'];
</script>

<style scoped>
.app-shell {
  min-height: 100vh;
  background: #f8fafc;
}

.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: rgba(255, 255, 255, 0.9);
  border-bottom: 1px solid #e2e8f0;
  padding: 0 40px;
}

.brand {
  font-size: 18px;
  font-weight: 700;
  color: #0f172a;
}

.lang-button {
  color: #1d4ed8;
  font-weight: 600;
}

.lang-divider {
  color: #cbd5f5;
}

.app-content {
  max-width: 1100px;
  margin: 0 auto;
  padding: 40px 24px 80px;
}

.hero {
  text-align: center;
  margin-bottom: 32px;
}

.hero h1 {
  font-size: 36px;
  font-weight: 800;
  color: #0f172a;
  margin-bottom: 8px;
}

.hero p {
  font-size: 16px;
  color: #64748b;
}

.upload-card {
  border-radius: 20px;
  border: 1px dashed #e2e8f0;
  margin-bottom: 32px;
  background: #ffffff;
}

.upload-area {
  text-align: center;
  padding: 32px 0;
}

.upload-title {
  font-size: 18px;
  font-weight: 600;
  color: #1e293b;
}

.upload-subtitle {
  font-size: 14px;
  color: #94a3b8;
  margin-top: 6px;
}

.section {
  margin-top: 24px;
}

.section-title {
  font-size: 12px;
  font-weight: 700;
  color: #94a3b8;
  text-transform: uppercase;
  margin-bottom: 12px;
}

.style-card {
  border-radius: 16px;
  border: 1px solid #e2e8f0;
  margin-bottom: 16px;
}

.style-name {
  font-weight: 600;
  color: #0f172a;
}

.style-desc {
  font-size: 12px;
  color: #64748b;
}

.privacy-card {
  border-radius: 16px;
}

.privacy-title {
  font-weight: 600;
  color: #0f172a;
}

.privacy-desc {
  font-size: 12px;
  color: #94a3b8;
}

.primary-action {
  margin-top: 32px;
  height: 52px;
  font-size: 18px;
  font-weight: 600;
}
</style>
