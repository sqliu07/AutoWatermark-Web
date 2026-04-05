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

      <!-- 主体 -->
      <main class="app-main">
        <!-- 预览区 -->
        <section class="preview-area">
          <UploadZone v-if="store.files.length === 0" />
          <PreviewArea v-else />
        </section>

        <!-- 设置栏 -->
        <aside class="settings-sidebar">
          <SettingsPanel />
        </aside>
      </main>

      <footer class="app-footer">
        <span>&copy; {{ copyrightYears }} Gabriel Liu</span>
        <span class="footer-dot">•</span>
        <a
          href="https://github.com/sqliu07"
          target="_blank"
          rel="noopener noreferrer"
          class="footer-link"
          aria-label="GitHub profile"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 24 24"
            fill="currentColor"
            class="footer-github-icon"
          >
            <path
              d="M12 0.296c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.387 0.6 0.113 0.82-0.258 0.82-0.577 0-0.285-0.01-1.04-0.015-2.04-3.338 0.724-4.042-1.61-4.042-1.61-0.546-1.387-1.333-1.757-1.333-1.757-1.09-0.745 0.082-0.73 0.082-0.73 1.205 0.084 1.84 1.236 1.84 1.236 1.07 1.835 2.809 1.305 3.495 0.998 0.108-0.776 0.418-1.305 0.762-1.605-2.665-0.305-5.466-1.332-5.466-5.93 0-1.31 0.47-2.38 1.235-3.22-0.135-0.303-0.54-1.523 0.105-3.176 0 0 1.005-0.322 3.3 1.23 0.96-0.267 1.98-0.399 3-0.405 1.02 0.006 2.04 0.138 3 0.405 2.28-1.552 3.285-1.23 3.285-1.23 0.645 1.653 0.24 2.873 0.12 3.176 0.765 0.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92 0.42 0.36 0.81 1.096 0.81 2.22 0 1.606-0.015 2.896-0.015 3.286 0 0.315 0.21 0.69 0.825 0.57 C20.565 22.092 24 17.592 24 12.296 c0-6.627-5.373-12-12-12z"
            />
          </svg>
        </a>
      </footer>

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
const startYear = 2024
const currentYear = new Date().getFullYear()
const copyrightYears = currentYear === startYear ? `${startYear}` : `${startYear}-${currentYear}`
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
  showLogoModal.value = false
  store.processPendingLogoTasks(choice)
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

/* 桌面端：左右分栏 */
.app-main {
  display: grid;
  grid-template-columns: 1fr 320px;
  flex: 1;
  overflow: hidden;
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

.app-footer {
  height: 38px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  border-top: 1px solid var(--color-border-light);
  background: var(--color-surface);
  font-size: 12px;
  color: var(--color-text-tertiary);
}

.footer-dot {
  opacity: 0.7;
}

.footer-link {
  color: var(--color-text-secondary);
  text-decoration: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.footer-link:hover {
  color: var(--color-accent);
}

.footer-github-icon {
  width: 14px;
  height: 14px;
}

/* 移动端：上下堆叠 */
@media (max-width: 768px) {
  .app-header {
    padding: 0 16px;
    height: 48px;
  }

  .brand-sub {
    display: none;
  }

  .app-main {
    grid-template-columns: 1fr;
    grid-template-rows: auto 1fr;
    overflow-y: auto;
  }

  .preview-area {
    padding: 16px;
    min-height: 200px;
  }

  .settings-sidebar {
    border-left: none;
    border-top: 1px solid var(--color-border-light);
    padding: 16px;
  }

  .app-footer {
    height: 34px;
    font-size: 11px;
  }
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
