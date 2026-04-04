<template>
  <div
    class="upload-zone"
    :class="{ dragging }"
    @dragover.prevent="dragging = true"
    @dragleave="dragging = false"
    @drop.prevent="onDrop"
    @click="triggerInput"
  >
    <input
      ref="fileInput"
      type="file"
      multiple
      accept=".jpg,.jpeg,.png"
      style="display: none"
      @change="onSelect"
    />

    <div class="upload-icon">
      <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
        <rect x="4" y="8" width="40" height="32" rx="4" stroke="currentColor" stroke-width="2" />
        <circle cx="16" cy="22" r="4" stroke="currentColor" stroke-width="2" />
        <path d="M4 32 L16 24 L24 30 L34 20 L44 28" stroke="currentColor" stroke-width="2" fill="none" />
      </svg>
    </div>

    <p class="upload-text">
      {{ t('upload.dragHint') }}
      <span class="upload-link">{{ t('upload.clickHint') }}</span>
    </p>
    <p class="upload-formats">{{ t('upload.formats') }}</p>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAppStore } from '../stores/app'

const { t } = useI18n()
const store = useAppStore()

const fileInput = ref(null)
const dragging = ref(false)

function triggerInput() {
  fileInput.value?.click()
}

function onSelect(e) {
  const files = Array.from(e.target.files || [])
  if (files.length) store.addFiles(files)
}

function onDrop(e) {
  dragging.value = false
  const files = Array.from(e.dataTransfer.files || []).filter(f =>
    /\.(jpe?g|png)$/i.test(f.name)
  )
  if (files.length) store.addFiles(files)
}
</script>

<style scoped>
.upload-zone {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 14px;
  width: 100%;
  max-width: 520px;
  padding: 64px 40px;
  border: 2px dashed var(--color-border);
  border-radius: var(--radius-lg);
  cursor: pointer;
  transition: all 0.2s ease;
  background: var(--color-surface);
}

.upload-zone:hover,
.upload-zone.dragging {
  border-color: var(--color-accent);
  background: var(--color-surface-hover);
  box-shadow: var(--shadow-md);
}

.upload-icon {
  color: var(--color-text-tertiary);
  transition: color 0.2s;
}

.upload-zone:hover .upload-icon,
.upload-zone.dragging .upload-icon {
  color: var(--color-accent);
}

.upload-text {
  font-size: 15px;
  color: var(--color-text-secondary);
  text-align: center;
}

.upload-link {
  color: var(--color-accent);
  font-weight: 600;
  text-decoration: underline;
  text-underline-offset: 2px;
}

.upload-formats {
  font-size: 12px;
  color: var(--color-text-tertiary);
}
</style>
