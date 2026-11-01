<template>
  <div class="options-view">
    <div class="options-icon">
      <svg width="40" height="40" viewBox="0 0 24 24" fill="none">
        <circle cx="12" cy="12" r="10" stroke="var(--color-accent)" stroke-width="1.5"/>
        <path d="M12 8v4M12 16h.01" stroke="var(--color-accent)" stroke-width="1.5" stroke-linecap="round"/>
      </svg>
    </div>
    <p class="options-title">{{ t('options.detected') }}</p>
    <p class="options-filename">{{ task?.originalName }}</p>

    <div class="options-toggle-group">
      <div v-if="task?.features?.is_hdr" class="option-toggle-item">
        <a-switch
          size="small"
          :checked="preserveHdr"
          :aria-label="t('options.preserve_hdr')"
          @change="$emit('update:preserveHdr', $event)"
        />
        <span class="option-toggle-label">{{ t('options.preserve_hdr') }}</span>
      </div>
      <div v-if="task?.features?.is_motion" class="option-toggle-item">
        <a-switch
          size="small"
          :checked="preserveMotion"
          :aria-label="t('options.preserve_motion')"
          @change="$emit('update:preserveMotion', $event)"
        />
        <span class="option-toggle-label">{{ t('options.preserve_motion') }}</span>
      </div>
    </div>

    <label v-if="canApplyAll" class="option-toggle-item">
      <input type="checkbox" :checked="applyAll" @change="$emit('update:applyAll', $event.target.checked)" />
      <span class="option-toggle-label">{{ t('options.applyAll') }}</span>
    </label>

    <a-button type="primary" size="large" @click="$emit('confirm')">
      {{ t('options.confirm') }}
    </a-button>
  </div>
</template>

<script setup>
import { useI18n } from 'vue-i18n'

defineProps({
  task: { type: Object, default: null },
  preserveHdr: { type: Boolean, default: true },
  preserveMotion: { type: Boolean, default: true },
  applyAll: { type: Boolean, default: false },
  canApplyAll: { type: Boolean, default: false },
})

defineEmits(['update:preserveHdr', 'update:preserveMotion', 'update:applyAll', 'confirm'])

const { t } = useI18n()
</script>

<style scoped>
.options-view {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 20px;
}

.options-icon {
  margin-bottom: 4px;
}

.options-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--color-text);
  letter-spacing: -0.2px;
  margin: 0;
}

.options-filename {
  font-size: 13px;
  color: var(--color-text-secondary);
  margin: 0;
}

.options-toggle-group {
  display: flex;
  flex-direction: column;
  gap: 12px;
  width: 100%;
  max-width: 280px;
  padding: 16px;
  background: rgba(255, 255, 255, 0.6);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  border-radius: var(--radius-sm);
  border: 0.5px solid var(--color-border-light);
}

.option-toggle-item {
  display: flex;
  align-items: center;
  gap: 10px;
}

.option-toggle-label {
  font-size: 13px;
  color: var(--color-text);
  user-select: none;
}
</style>
