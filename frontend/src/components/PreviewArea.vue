<template>
  <div class="preview-container">
    <ResultCompare
      v-if="previewTask?.status === 'succeeded'"
      :task="previewTask"
      :original-url="originalUrl"
      :original-video-url="originalVideoUrl"
      :motion-video-url="motionVideoUrl"
      :is-motion="isMotion"
      :motion-playing="motionPlaying"
      :original-motion-playing="originalMotionPlaying"
      @fullscreen="openFullscreen"
      @motion-hover="onMotionHover"
      @original-hover="onOriginalHover"
    />

    <template v-else-if="['failed', 'unavailable'].includes(previewTask?.status)">
      <div class="error-view">
        <div class="error-icon">
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none">
            <circle cx="12" cy="12" r="10" stroke="var(--color-error)" stroke-width="1.5"/>
            <path d="M8 8l8 8M16 8l-8 8" stroke="var(--color-error)" stroke-width="1.5" stroke-linecap="round"/>
          </svg>
        </div>
        <p class="error-name">{{ previewTask.originalName }}</p>
        <p v-if="previewTask.status === 'unavailable'" class="error-msg">{{ t('status.unavailable') }}</p>
        <p v-if="previewTask.status === 'failed'" class="error-msg">{{ previewTask.error }}</p>
        <a-button
          size="small"
          :loading="previewTask.retrying"
          @click="store.retryTask(previewTask)"
        >
          {{ t(previewTask.status === 'unavailable' ? 'action.resume' : 'action.retry') }}
        </a-button>
      </div>
    </template>

    <div v-else-if="previewTask?.status === 'needs_logo'" class="options-view">
      <p class="error-name">{{ previewTask.originalName }}</p>
      <p>{{ t('logo.message') }}</p>
      <a-button @click="store.processPendingLogoTasks('xiaomi')">{{ t('logo.xiaomi') }}</a-button>
      <a-button @click="store.processPendingLogoTasks('leica')">{{ t('logo.leica') }}</a-button>
    </div>

    <OptionsPrompt
      v-else-if="previewTask?.status === 'needs_options'"
      :task="previewTask"
      v-model:preserve-hdr="pendingPreserveHdr"
      v-model:preserve-motion="pendingPreserveMotion"
      v-model:apply-all="applyOptionsToAll"
      :can-apply-all="store.tasks.length > 1"
      @confirm="confirmOptions"
    />

    <template v-else-if="store.files.length > 0">
      <img
        v-if="originalUrl || localPreviewUrl"
        :src="originalUrl || localPreviewUrl"
        class="single-preview"
        :alt="previewTask?.originalName || store.files[0]?.name"
        decoding="async"
      />
      <div class="preview-filename">
        {{ previewTask?.originalName || store.files[0]?.name }}
        <a-tag v-if="store.files.length > 1" color="default">
          +{{ store.files.length - 1 }}
        </a-tag>
        <span v-if="previewTask?.status === 'pending'"> · {{ t('status.queued') }}</span>
      </div>
    </template>

    <ProgressOverlay
      :visible="isPreviewBusy"
      :percent="progressPercent"
      :completed-count="store.completedCount"
      :total-count="store.totalCount"
      :current-name="currentProcessingName"
      :stage="currentStage"
      :tasks="store.tasks"
    />

    <FullscreenPreview :src="fullscreenSrc" :alt="previewTask?.originalName || store.files[0]?.name" @close="fullscreenSrc = null" />
  </div>
</template>

<script setup>
import { ref, computed, watch, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAppStore } from '../stores/app'
import ResultCompare from './preview/ResultCompare.vue'
import OptionsPrompt from './preview/OptionsPrompt.vue'
import ProgressOverlay from './preview/ProgressOverlay.vue'
import FullscreenPreview from './preview/FullscreenPreview.vue'
import { extractMotionVideoBlob } from '../utils/motion-preview.js'

const { t } = useI18n()
const store = useAppStore()

const localPreviewUrl = ref(null)
const fullscreenSrc = ref(null)
const originalUrl = ref(null)
const originalVideoUrl = ref(null)
const motionPlaying = ref(false)
const originalMotionPlaying = ref(false)
let motionReadVersion = 0
let motionReadPending = false

const previewTask = computed(() => store.currentPreview)

watch(previewTask, () => {
  motionReadVersion++
  motionReadPending = false
  motionPlaying.value = false
  originalMotionPlaying.value = false
  fullscreenSrc.value = null
  if (originalVideoUrl.value) {
    URL.revokeObjectURL(originalVideoUrl.value)
    originalVideoUrl.value = null
  }
})

watch(() => previewTask.value?.file, (file) => {
  if (originalUrl.value) {
    URL.revokeObjectURL(originalUrl.value)
    originalUrl.value = null
  }
  if (file) {
    originalUrl.value = URL.createObjectURL(file)
  }
}, { immediate: true })

watch(() => store.files[0], (file) => {
  if (localPreviewUrl.value) URL.revokeObjectURL(localPreviewUrl.value)
  localPreviewUrl.value = file ? URL.createObjectURL(file) : null
}, { immediate: true })

onUnmounted(() => {
  motionReadVersion++
  if (localPreviewUrl.value) URL.revokeObjectURL(localPreviewUrl.value)
  if (originalVideoUrl.value) URL.revokeObjectURL(originalVideoUrl.value)
  if (originalUrl.value) URL.revokeObjectURL(originalUrl.value)
})

const progressPercent = computed(() => {
  const task = previewTask.value
  const progress = task?.status === 'uploading' ? task.uploadProgress : task?.progress
  return Math.round(Math.max(0, Math.min(1, progress || 0)) * 100)
})

const isPreviewBusy = computed(() => ['uploading', 'queued', 'processing'].includes(previewTask.value?.status))
const currentProcessingName = computed(() => previewTask.value?.originalName || '')
const currentStage = computed(() => {
  const task = previewTask.value
  if (task?.status === 'uploading') return t(task.uploadProgress >= 1 ? 'status.identifying' : 'status.uploading')
  if (task?.status === 'queued') return t('status.queued')
  const stage = ['loaded', 'metadata', 'rendered', 'saving', 'saved', 'previews'].includes(task?.stage) ? task.stage : 'processing'
  return t(`status.stages.${stage}`)
})

const isMotion = computed(() => previewTask.value?.result?.is_motion === true)
const motionVideoUrl = computed(() => {
  if (!isMotion.value) return null
  return previewTask.value.result.motion_video_url || null
})

const pendingOptions = ref({})
const applyOptionsToAll = ref(false)
watch(previewTask, () => { applyOptionsToAll.value = false })
watch(() => store.tasks, () => { pendingOptions.value = {} })
const currentPendingKey = computed(() => previewTask.value?.id || '__none__')
const currentPendingOptions = computed(() => {
  const key = currentPendingKey.value
  if (!pendingOptions.value[key]) {
    pendingOptions.value[key] = {
      preserve_hdr: previewTask.value?.preserveOptions?.preserve_hdr !== false,
      preserve_motion: previewTask.value?.preserveOptions?.preserve_motion !== false,
    }
  }
  return pendingOptions.value[key]
})
const pendingPreserveHdr = computed({
  get: () => currentPendingOptions.value.preserve_hdr,
  set: value => {
    currentPendingOptions.value.preserve_hdr = value
  },
})
const pendingPreserveMotion = computed({
  get: () => currentPendingOptions.value.preserve_motion,
  set: value => {
    currentPendingOptions.value.preserve_motion = value
  },
})

async function confirmOptions() {
  await store.processPendingOptionsTask(previewTask.value, {
    preserve_hdr: currentPendingOptions.value.preserve_hdr,
    preserve_motion: currentPendingOptions.value.preserve_motion,
  }, { applyAll: applyOptionsToAll.value })
}

function onMotionHover(entering) {
  if (!isMotion.value) return
  motionPlaying.value = entering
}

function onOriginalHover(entering) {
  if (!isMotion.value) return
  originalMotionPlaying.value = entering
  if (entering && !originalVideoUrl.value && !motionReadPending && previewTask.value?.file) {
    extractVideoFromFile(previewTask.value.file)
  }
}

async function extractVideoFromFile(file) {
  const version = motionReadVersion
  motionReadPending = true
  try {
    const videoBlob = await extractMotionVideoBlob(file)
    if (videoBlob && version === motionReadVersion && previewTask.value?.file === file) {
      originalVideoUrl.value = URL.createObjectURL(videoBlob)
    }
  } catch {
    // Local preview motion extraction is best effort.
  } finally {
    if (version === motionReadVersion) motionReadPending = false
  }
}

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
  letter-spacing: -0.2px;
}

.options-view,
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
  letter-spacing: -0.2px;
}

.error-msg {
  font-size: 13px;
  color: var(--color-error);
  letter-spacing: -0.1px;
}

@media (max-width: 768px) {
  .preview-container {
    justify-content: center;
    min-height: 0;
    height: auto;
  }

  .single-preview {
    max-height: calc(100% - 32px);
  }
}
</style>
