<template>
  <div class="preview-container">
    <!-- 处理完成：并排对比 -->
    <template v-if="previewTask?.status === 'succeeded'">
      <div class="compare-view">
        <div class="compare-card">
          <div class="compare-label">{{ t('compare.original') }}</div>
          <img
            v-if="originalUrl"
            :src="originalUrl"
            class="compare-img"
            :alt="previewTask.originalName"
            @click="openFullscreen(originalUrl)"
          />
        </div>
        <div class="compare-arrow">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
            <path d="M5 12h14M13 6l6 6-6 6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </div>
        <div class="compare-card result">
          <div class="compare-label">{{ t('compare.watermarked') }}</div>
          <img
            :src="previewTask.result.processed_image"
            class="compare-img"
            :alt="previewTask.originalName"
            @click="openFullscreen(previewTask.result.processed_image)"
          />
        </div>
      </div>

      <!-- 操作栏 -->
      <div class="action-bar">
        <span class="action-filename">{{ previewTask.originalName }}</span>
        <div class="action-buttons">
          <a-button
            size="small"
            @click="openFullscreen(previewTask.result.processed_image)"
          >
            {{ t('action.preview') }}
          </a-button>
          <a-button
            type="primary"
            size="small"
            :href="previewTask.result.processed_image"
            :download="previewTask.originalName"
            tag="a"
          >
            {{ t('action.download') }}
          </a-button>
        </div>
      </div>
    </template>

    <!-- 处理失败 -->
    <template v-else-if="previewTask?.status === 'failed'">
      <div class="error-view">
        <div class="error-icon">
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none">
            <circle cx="12" cy="12" r="10" stroke="var(--color-error)" stroke-width="1.5"/>
            <path d="M8 8l8 8M16 8l-8 8" stroke="var(--color-error)" stroke-width="1.5" stroke-linecap="round"/>
          </svg>
        </div>
        <p class="error-name">{{ previewTask.originalName }}</p>
        <p class="error-msg">{{ previewTask.error }}</p>
      </div>
    </template>

    <!-- 处理前：原图预览 -->
    <template v-else-if="store.files.length > 0">
      <img
        v-if="localPreviewUrl"
        :src="localPreviewUrl"
        class="single-preview"
        :alt="store.files[0]?.name"
      />
      <div class="preview-filename">
        {{ store.files[0]?.name }}
        <a-tag v-if="store.files.length > 1" color="default">
          +{{ store.files.length - 1 }}
        </a-tag>
      </div>
    </template>

    <!-- 处理进度覆盖层 -->
    <Transition name="fade">
      <div v-if="store.isProcessing" class="progress-overlay">
        <div class="progress-card">
          <a-progress
            type="circle"
            :percent="progressPercent"
            :size="96"
            :stroke-width="6"
            :stroke-color="{ '0%': '#2c2c2c', '100%': '#6b6860' }"
            :format="() => `${progressPercent}%`"
          />

          <div class="progress-info">
            <span class="progress-count">
              {{ t('status.processing', { current: store.completedCount, total: store.totalCount }) }}
            </span>
            <span v-if="currentProcessingName" class="progress-filename">
              {{ currentProcessingName }}
            </span>
          </div>

          <!-- 微型文件列表 -->
          <div v-if="store.totalCount > 1" class="progress-list">
            <div
              v-for="(task, i) in store.tasks"
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

    <!-- 全屏预览 -->
    <Transition name="fade">
      <div v-if="fullscreenSrc" class="fullscreen-overlay" @click="fullscreenSrc = null">
        <img :src="fullscreenSrc" class="fullscreen-img" @click.stop />
        <button class="fullscreen-close" @click="fullscreenSrc = null">
          <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
            <path d="M4 4l10 10M14 4L4 14" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
          </svg>
        </button>
      </div>
    </Transition>
  </div>
</template>

<script setup>
import { ref, computed, watch, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAppStore } from '../stores/app'

const { t } = useI18n()
const store = useAppStore()

const localPreviewUrl = ref(null)
const fullscreenSrc = ref(null)

const previewTask = computed(() => store.currentPreview)

// 原图的本地 URL
const originalUrl = computed(() => {
  const task = previewTask.value
  if (!task?.file) return null
  return URL.createObjectURL(task.file)
})

// 没有选中任务时，预览第一个文件
watch(() => store.files[0], (file) => {
  if (localPreviewUrl.value) URL.revokeObjectURL(localPreviewUrl.value)
  localPreviewUrl.value = file ? URL.createObjectURL(file) : null
}, { immediate: true })

onUnmounted(() => {
  if (localPreviewUrl.value) URL.revokeObjectURL(localPreviewUrl.value)
})

const progressPercent = computed(() => {
  if (store.totalCount === 0) return 0
  // 所有任务的 progress 加权平均（每个任务 0.0~1.0）
  const sum = store.tasks.reduce((acc, t) => acc + (t.progress || 0), 0)
  return Math.round((sum / store.totalCount) * 100)
})

const currentProcessingName = computed(() => {
  const task = store.tasks.find(t => t.status === 'processing' || t.status === 'uploading')
  return task?.originalName || ''
})

function openFullscreen(src) {
  fullscreenSrc.value = src
}
</script>

<style scoped>
.preview-container {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  gap: 12px;
}

/* --- 并排对比 --- */
.compare-view {
  display: flex;
  align-items: center;
  gap: 16px;
  max-width: 100%;
  max-height: calc(100% - 50px);
  padding: 0 8px;
}

@media (max-width: 768px) {
  .compare-view {
    flex-direction: column;
    gap: 12px;
    max-height: none;
    overflow-y: auto;
  }

  .compare-arrow {
    transform: rotate(90deg);
  }

  .compare-img {
    max-height: 40vh;
  }

  .action-bar {
    flex-direction: column;
    gap: 8px;
    text-align: center;
  }
}

.compare-card {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.compare-label {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.6px;
  color: var(--color-text-tertiary);
}

.compare-img {
  max-width: 100%;
  max-height: 60vh;
  object-fit: contain;
  border-radius: var(--radius-sm);
  box-shadow: var(--shadow-sm);
  cursor: zoom-in;
  transition: box-shadow 0.2s;
}

.compare-img:hover {
  box-shadow: var(--shadow-md);
}

.compare-arrow {
  color: var(--color-text-tertiary);
  flex-shrink: 0;
}

/* --- 操作栏 --- */
.action-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  max-width: 720px;
  padding: 8px 16px;
  background: var(--color-surface);
  border-radius: var(--radius-sm);
  border: 1px solid var(--color-border-light);
}

.action-filename {
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.action-buttons {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

/* --- 单张预览 --- */
.single-preview {
  max-width: 100%;
  max-height: calc(100% - 40px);
  object-fit: contain;
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-md);
}

.preview-filename {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--color-text-secondary);
  font-weight: 500;
}

/* --- 错误视图 --- */
.error-view {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.error-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text);
}

.error-msg {
  font-size: 13px;
  color: var(--color-error);
}

/* --- 进度覆盖 --- */
.progress-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: auto;
  background: rgba(247, 246, 243, 0.88);
  backdrop-filter: blur(6px);
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
  animation: progress-enter 0.35s cubic-bezier(0.16, 1, 0.3, 1);
}

@keyframes progress-enter {
  from { opacity: 0; transform: scale(0.95) translateY(8px); }
  to { opacity: 1; transform: scale(1) translateY(0); }
}

.progress-circle-text {
  font-size: 18px;
  font-weight: 700;
  color: var(--color-text);
  letter-spacing: -0.5px;
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
  transition: all 0.3s ease;
}

.progress-dot.done {
  background: var(--color-success);
}

.progress-dot.fail {
  background: var(--color-error);
}

.progress-dot.active {
  background: var(--color-accent);
  animation: dot-pulse 1s ease-in-out infinite;
}

@keyframes dot-pulse {
  0%, 100% { transform: scale(1); opacity: 1; }
  50% { transform: scale(1.4); opacity: 0.7; }
}

/* --- 全屏预览 --- */
.fullscreen-overlay {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.75);
  backdrop-filter: blur(8px);
  cursor: zoom-out;
}

.fullscreen-img {
  max-width: 92vw;
  max-height: 92vh;
  object-fit: contain;
  border-radius: var(--radius-sm);
  cursor: default;
}

.fullscreen-close {
  position: absolute;
  top: 16px;
  right: 20px;
  width: 40px;
  height: 40px;
  border: none;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.15);
  color: white;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.15s;
}

.fullscreen-close:hover {
  background: rgba(255, 255, 255, 0.3);
}
</style>
