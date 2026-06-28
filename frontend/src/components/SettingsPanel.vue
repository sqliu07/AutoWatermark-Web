<template>
  <div class="settings-panel">
    <!-- 水印样式 -->
    <section class="section">
      <h3 class="section-title">{{ t('settings.style') }}</h3>
      <StyleSelector />
    </section>

    <!-- 输出质量 -->
    <section class="section">
      <h3 class="section-title">{{ t('settings.quality') }}</h3>
      <a-segmented
        v-model:value="store.imageQuality"
        :options="qualityOptions"
        block
      />
    </section>

    <!-- 阅后即焚 -->
    <section class="section">
      <div class="toggle-row">
        <div>
          <div class="toggle-label">{{ t('settings.burnAfterRead') }}</div>
          <div class="toggle-desc">{{ t('settings.burnTip') }}</div>
        </div>
        <a-switch v-model:checked="store.burnAfterRead" />
      </div>
    </section>

    <div class="section-divider" />

    <!-- 操作按钮 -->
    <section class="section actions">
      <a-button
        type="primary"
        block
        size="large"
        :loading="store.isProcessing"
        :disabled="store.files.length === 0"
        class="process-btn"
        @click="store.processAll()"
      >
        {{ store.isProcessing ? t('action.processing') : t('action.process') }}
      </a-button>

      <a-button
        v-if="store.files.length > 0 && !store.isProcessing"
        block
        @click="reselect"
      >
        {{ t('upload.reselect') }}
      </a-button>

      <a-button
        v-if="store.canDownloadZip"
        block
        @click="store.downloadZip()"
      >
        {{ t('action.downloadAll') }}
      </a-button>
    </section>

    <!-- 状态 -->
    <Transition name="fade">
      <section v-if="store.allDone" class="section status-done">
        <div
          class="done-summary"
          :class="store.succeededTasks.length > 0 ? 'done-ok' : 'done-fail'"
        >
          <span class="done-title">{{ t('status.done') }}</span>
          <span class="done-count">{{ store.succeededTasks.length }}/{{ store.totalCount }}</span>
        </div>
      </section>
    </Transition>
  </div>
</template>

<script setup>
import { computed, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAppStore } from '../stores/app'
import StyleSelector from './StyleSelector.vue'

const { t } = useI18n()
const store = useAppStore()

function reselect() {
  store.clearFiles()
  // 等 DOM 更新后 UploadZone 挂载，触发其文件选择器
  nextTick(() => {
    const input = document.querySelector('.upload-zone input[type="file"]')
    if (input) input.click()
  })
}

const qualityOptions = computed(() => [
  { label: t('settings.qualityHigh'), value: 'high' },
  { label: t('settings.qualityMedium'), value: 'medium' },
  { label: t('settings.qualityLow'), value: 'low' },
])
</script>

<style scoped>
.settings-panel {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.section {
  padding-bottom: 24px;
}

.section-title {
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.8px;
  color: var(--color-text-tertiary);
  margin-bottom: 16px;
  position: relative;
  padding-left: 12px;
}

.section-title::before {
  content: '';
  position: absolute;
  left: 0;
  top: 2px;
  bottom: 2px;
  width: 3px;
  border-radius: 2px;
  background: var(--color-accent);
}

.section-divider {
  height: 0.5px;
  background: rgba(0, 0, 0, 0.06);
  margin: 4px 0 24px;
}

.toggle-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.toggle-label {
  font-size: 14px;
  font-weight: 500;
  color: var(--color-text);
  letter-spacing: -0.2px;
}

.toggle-desc {
  font-size: 12px;
  color: var(--color-text-tertiary);
  margin-top: 3px;
  letter-spacing: -0.1px;
}

.actions {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.process-btn {
  font-weight: 600;
  letter-spacing: -0.2px;
  transition: all var(--duration-fast) var(--ease-apple) !important;
}
.process-btn:hover:not(:disabled) {
  transform: scale(1.01);
}
.process-btn:disabled {
  background: var(--color-border-light) !important;
  border-color: var(--color-border-light) !important;
  color: var(--color-text-tertiary) !important;
}

.status-done {
  padding-top: 8px;
  padding-bottom: 0;
}

.done-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-radius: var(--radius-sm);
  border: 0.5px solid var(--color-border-light);
  padding: 10px 14px;
  background: var(--color-surface-hover);
}

.done-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text);
  letter-spacing: -0.2px;
}

.done-count {
  font-size: 12px;
  font-weight: 600;
}

.done-ok .done-count {
  color: var(--color-success);
}

.done-fail .done-count {
  color: var(--color-error);
}
</style>
