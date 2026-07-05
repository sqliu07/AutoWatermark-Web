<template>
  <Transition name="fade">
    <div v-if="visible" class="progress-overlay">
      <div class="progress-card">
        <a-progress
          type="circle"
          :percent="percent"
          :size="96"
          :stroke-width="6"
          :stroke-color="{ '0%': '#0071e3', '100%': '#0077ed' }"
          :format="() => `${percent}%`"
        />

        <div class="progress-info">
          <span class="progress-count">
            {{ t('status.processing', { current: completedCount, total: totalCount }) }}
          </span>
          <span v-if="currentName" class="progress-filename">
            {{ currentName }}
          </span>
        </div>

        <div v-if="totalCount > 1" class="progress-list">
          <div
            v-for="(task, i) in tasks"
            :key="i"
            class="progress-dot"
            :class="{
              done: task.status === 'succeeded',
              fail: task.status === 'failed',
              active: task.status === 'processing' || task.status === 'uploading',
            }"
          />
        </div>
      </div>
    </div>
  </Transition>
</template>

<script setup>
import { useI18n } from 'vue-i18n'

defineProps({
  visible: { type: Boolean, default: false },
  percent: { type: Number, default: 0 },
  completedCount: { type: Number, default: 0 },
  totalCount: { type: Number, default: 0 },
  currentName: { type: String, default: '' },
  tasks: { type: Array, default: () => [] },
})

const { t } = useI18n()
</script>

<style scoped>
.progress-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: auto;
  background: rgba(245, 245, 247, 0.85);
  backdrop-filter: blur(20px) saturate(180%);
  -webkit-backdrop-filter: blur(20px) saturate(180%);
  border-radius: var(--radius-md);
  z-index: 10;
}

.progress-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 20px;
  padding: 40px 48px;
  background: var(--color-surface);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  min-width: 260px;
  max-width: 90%;
  overflow: visible;
  animation: progress-enter var(--duration-slow) var(--ease-spring);
}

@keyframes progress-enter {
  from { opacity: 0; transform: scale(0.92) translateY(12px); }
  to { opacity: 1; transform: scale(1) translateY(0); }
}

.progress-info {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}

.progress-count {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text);
  letter-spacing: -0.2px;
}

.progress-filename {
  font-size: 12px;
  line-height: 1.6;
  color: var(--color-text-tertiary);
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  padding-bottom: 2px;
  letter-spacing: -0.1px;
}

.progress-list {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  justify-content: center;
  max-width: 200px;
}

.progress-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--color-border);
  transition: all var(--duration-normal) var(--ease-apple);
}

.progress-dot.done {
  background: var(--color-success);
}

.progress-dot.fail {
  background: var(--color-error);
}

.progress-dot.active {
  background: var(--color-accent);
  animation: dot-pulse 1.2s var(--ease-apple) infinite;
}

@keyframes dot-pulse {
  0%, 100% { transform: scale(1); opacity: 1; }
  50% { transform: scale(1.3); opacity: 0.7; }
}

@media (max-width: 768px) {
  .progress-card {
    padding: 28px 30px;
  }
}
</style>
