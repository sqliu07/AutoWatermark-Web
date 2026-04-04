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
        @click="store.clearFiles()"
      >
        {{ t('upload.reselect') }}
      </a-button>

      <a-button
        v-if="store.succeededTasks.length > 1"
        block
        @click="store.downloadZip()"
      >
        {{ t('action.downloadAll') }}
      </a-button>
    </section>

    <!-- 状态 -->
    <Transition name="fade">
      <section v-if="store.allDone" class="section status-done">
        <a-result
          :status="store.succeededTasks.length > 0 ? 'success' : 'error'"
          :title="t('status.done')"
          :sub-title="`${store.succeededTasks.length}/${store.totalCount}`"
          style="padding: 16px 0;"
        />
      </section>
    </Transition>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAppStore } from '../stores/app'
import StyleSelector from './StyleSelector.vue'

const { t } = useI18n()
const store = useAppStore()

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
  padding-bottom: 20px;
}

.section-title {
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.6px;
  color: var(--color-text-tertiary);
  margin-bottom: 12px;
}

.section-divider {
  height: 1px;
  background: var(--color-border-light);
  margin: 4px 0 20px;
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
}

.toggle-desc {
  font-size: 12px;
  color: var(--color-text-tertiary);
  margin-top: 2px;
}

.actions {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.process-btn {
  background: var(--color-accent) !important;
  border-color: var(--color-accent) !important;
  font-weight: 600;
  letter-spacing: 0.3px;
}
.process-btn:hover {
  background: var(--color-accent-hover) !important;
  border-color: var(--color-accent-hover) !important;
}

.status-done {
  padding-top: 8px;
}
</style>
