<template>
  <a-config-provider :locale="antLocale">
    <div class="app-shell">
      <!-- 顶栏 -->
      <header class="app-header">
        <div class="header-left">
          <h1 class="brand">AutoWatermark</h1>
          <span class="brand-sub">{{ t('app.subtitle') }}</span>
        </div>
        <div class="header-right">
          <a-segmented
            v-model:value="currentLang"
            :options="langOptions"
            size="small"
            @change="onLangChange"
          />
        </div>
      </header>

      <!-- 主体：三栏布局 -->
      <main class="app-main" :class="{ 'has-results': store.tasks.length > 0 }">
        <!-- 左侧：大预览区 -->
        <section class="preview-area">
          <UploadZone v-if="store.files.length === 0" />
          <PreviewArea v-else />
        </section>

        <!-- 右侧：设置栏 -->
        <aside class="settings-sidebar">
          <SettingsPanel />
        </aside>
      </main>

      <!-- 底部：缩略图条 -->
      <Transition name="slide-up">
        <ThumbnailStrip v-if="store.tasks.length > 0" />
      </Transition>

      <!-- Logo 选择弹窗 -->
      <a-modal
        v-model:open="showLogoModal"
        :title="t('logo.title')"
        :footer="null"
        :width="360"
        centered
      >
        <p class="logo-desc">{{ t('logo.message') }}</p>
        <div class="logo-choices">
          <a-button block size="large" @click="chooseLogo('xiaomi')">{{ t('logo.xiaomi') }}</a-button>
          <a-button block size="large" @click="chooseLogo('leica')">{{ t('logo.leica') }}</a-button>
        </div>
      </a-modal>
    </div>
  </a-config-provider>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import zhCN from 'ant-design-vue/es/locale/zh_CN'
import enUS from 'ant-design-vue/es/locale/en_US'
import { setLanguage } from './i18n'
import { useAppStore } from './stores/app'
import UploadZone from './components/UploadZone.vue'
import PreviewArea from './components/PreviewArea.vue'
import SettingsPanel from './components/SettingsPanel.vue'
import ThumbnailStrip from './components/ThumbnailStrip.vue'

const { t, locale } = useI18n()
const store = useAppStore()

// 加载水印样式列表
store.loadStyles()

const currentLang = ref(locale.value)
const langOptions = [
  { label: '中文', value: 'zh' },
  { label: 'EN', value: 'en' },
]
const antLocale = computed(() => currentLang.value === 'zh' ? zhCN : enUS)

function onLangChange(val) {
  setLanguage(val)
}

const showLogoModal = ref(false)

watch(() => store.tasks, (tasks) => {
  const needsLogo = tasks.find(t => t.status === 'needs_logo')
  showLogoModal.value = !!needsLogo
}, { deep: true })

function chooseLogo(choice) {
  store.logoPreference = choice
  showLogoModal.value = false
  store.processAll()
}
</script>

<style scoped>
.app-shell {
  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow: hidden;
}

.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 28px;
  height: 56px;
  background: var(--color-surface);
  border-bottom: 1px solid var(--color-border-light);
  flex-shrink: 0;
}

.header-left {
  display: flex;
  align-items: baseline;
  gap: 12px;
}

.brand {
  font-family: var(--font-display);
  font-size: 18px;
  font-weight: 700;
  letter-spacing: -0.3px;
  color: var(--color-text);
}

.brand-sub {
  font-size: 13px;
  color: var(--color-text-tertiary);
  font-weight: 400;
}

.app-main {
  display: grid;
  grid-template-columns: 1fr 320px;
  flex: 1;
  overflow: hidden;
  transition: grid-template-rows 0.3s ease;
}

.preview-area {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  overflow: hidden;
  background: var(--color-bg);
}

.settings-sidebar {
  background: var(--color-surface);
  border-left: 1px solid var(--color-border-light);
  overflow-y: auto;
  padding: 24px 20px;
}

.logo-desc {
  margin-bottom: 16px;
  color: var(--color-text-secondary);
  font-size: 14px;
}

.logo-choices {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
</style>
