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
      <svg width="56" height="56" viewBox="0 0 48 48" fill="none">
        <rect x="4" y="8" width="40" height="32" rx="4" stroke="currentColor" stroke-width="1.5" />
        <circle cx="16" cy="22" r="4" stroke="currentColor" stroke-width="1.5" />
        <path d="M4 32 L16 24 L24 30 L34 20 L44 28" stroke="currentColor" stroke-width="1.5" fill="none" />
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
  const files = Array.from(e.target.files || []).filter(f =>
    /\.(jpe?g|png)$/i.test(f.name) || ['image/jpeg', 'image/png'].includes(f.type)
  )
  if (files.length) store.addFiles(files)
  e.target.value = ''
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
  gap: 16px;
  width: 100%;
  max-width: 540px;
  padding: 72px 48px 48px;
  border: 1.5px dashed var(--color-border);
  border-radius: var(--radius-lg);
  cursor: pointer;
  transition: all var(--duration-normal) var(--ease-apple);
  background: var(--color-surface);
}

@media (max-width: 768px) {
  .upload-zone {
    padding: 40px 24px 32px;
    max-width: 100%;
  }
}

.upload-zone:hover,
.upload-zone.dragging {
  border-color: var(--color-accent);
  border-style: solid;
  background: var(--color-accent-bg);
  box-shadow: 0 0 0 4px rgba(0, 113, 227, 0.06);
}

.upload-icon {
  color: var(--color-text-tertiary);
  transition: all var(--duration-normal) var(--ease-spring);
}

.upload-zone:hover .upload-icon,
.upload-zone.dragging .upload-icon {
  color: var(--color-accent);
  transform: scale(1.06);
}

.upload-text {
  font-size: 16px;
  font-weight: 500;
  color: var(--color-text);
  text-align: center;
  letter-spacing: -0.2px;
}

.upload-link {
  color: var(--color-accent);
  font-weight: 600;
}

.upload-formats {
  font-size: 12px;
  color: var(--color-text-tertiary);
  letter-spacing: -0.05px;
}
</style>
