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

    <OptionsPrompt
      v-else-if="previewTask?.status === 'needs_options'"
      :task="previewTask"
      v-model:preserve-hdr="pendingPreserveHdr"
      v-model:preserve-motion="pendingPreserveMotion"
      @confirm="confirmOptions"
    />

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

    <ProgressOverlay
      :visible="store.isProcessing"
      :percent="progressPercent"
      :completed-count="store.completedCount"
      :total-count="store.totalCount"
      :current-name="currentProcessingName"
      :tasks="store.tasks"
    />

    <FullscreenPreview :src="fullscreenSrc" @close="fullscreenSrc = null" />
  </div>
</template>

<script setup>
import { ref, computed, watch, onUnmounted } from 'vue'
import { useAppStore } from '../stores/app'
import ResultCompare from './preview/ResultCompare.vue'
import OptionsPrompt from './preview/OptionsPrompt.vue'
import ProgressOverlay from './preview/ProgressOverlay.vue'
import FullscreenPreview from './preview/FullscreenPreview.vue'

const store = useAppStore()

const localPreviewUrl = ref(null)
const fullscreenSrc = ref(null)
const originalUrl = ref(null)
const originalVideoUrl = ref(null)
const motionPlaying = ref(false)
const originalMotionPlaying = ref(false)

const previewTask = computed(() => store.currentPreview)

watch(previewTask, () => {
  motionPlaying.value = false
  originalMotionPlaying.value = false
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
  if (localPreviewUrl.value) URL.revokeObjectURL(localPreviewUrl.value)
  if (originalVideoUrl.value) URL.revokeObjectURL(originalVideoUrl.value)
  if (originalUrl.value) URL.revokeObjectURL(originalUrl.value)
})

const progressPercent = computed(() => {
  if (store.totalCount === 0) return 0
  const sum = store.tasks.reduce((acc, task) => acc + (task.progress || 0), 0)
  return Math.round((sum / store.totalCount) * 100)
})

const currentProcessingName = computed(() => {
  const task = store.tasks.find(t => t.status === 'processing' || t.status === 'uploading')
  return task?.originalName || ''
})

const isMotion = computed(() => previewTask.value?.result?.is_motion === true)
const motionVideoUrl = computed(() => {
  if (!isMotion.value) return null
  return previewTask.value.result.motion_video_url || null
})

const pendingOptions = ref({})
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
  })
}

function onMotionHover(entering) {
  if (!isMotion.value) return
  motionPlaying.value = entering
}

function onOriginalHover(entering) {
  if (!isMotion.value) return
  originalMotionPlaying.value = entering
  if (entering && !originalVideoUrl.value && previewTask.value?.file) {
    extractVideoFromFile(previewTask.value.file)
  }
}

async function extractVideoFromFile(file) {
  try {
    const buffer = await file.arrayBuffer()
    const bytes = new Uint8Array(buffer)
    const videoStart = findMp4Start(bytes)
    if (videoStart === null) return
    const videoBlob = new Blob([bytes.slice(videoStart)], { type: 'video/mp4' })
    originalVideoUrl.value = URL.createObjectURL(videoBlob)
  } catch {
    // Local preview motion extraction is best effort.
  }
}

function findMp4Start(bytes) {
  const ftyp = [0x66, 0x74, 0x79, 0x70]
  const searchStart = Math.max(0, bytes.length - 32 * 1024 * 1024)
  for (let i = bytes.length - 8; i >= searchStart; i--) {
    if (bytes[i] === ftyp[0] && bytes[i + 1] === ftyp[1] &&
        bytes[i + 2] === ftyp[2] && bytes[i + 3] === ftyp[3] && i >= 4) {
      const start = i - 4
      const size = (bytes[start] << 24) | (bytes[start + 1] << 16) | (bytes[start + 2] << 8) | bytes[start + 3]
      if (size >= 8 && size <= bytes.length - start) {
        return start
      }
    }
  }
  return null
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
