<template>
  <div class="thumbnail-strip">
    <div class="strip-scroll">
      <div
        v-for="(task, i) in store.tasks"
        :key="task.clientId || task.id || i"
        class="thumb-item"
        :class="{
          active: store.currentPreview === task,
          succeeded: task.status === 'succeeded',
          failed: task.status === 'failed' || task.status === 'unavailable',
          processing: ['queued', 'processing', 'uploading'].includes(task.status),
        }"
        role="button"
        tabindex="0"
        :aria-label="task.originalName"
        :aria-pressed="store.currentPreview === task"
        @click="onClickThumb(task)"
        @keydown.enter.self.prevent="onClickThumb(task)"
        @keydown.space.self.prevent="onClickThumb(task)"
      >
        <img
          v-if="thumbUrls[i]"
          :src="thumbUrls[i]"
          class="thumb-img"
          :alt="task.originalName"
          loading="lazy"
          decoding="async"
        />
        <div v-if="['queued', 'processing', 'uploading'].includes(task.status)" class="thumb-loading">
          <a-spin size="small" />
        </div>
        <div v-if="task.status === 'failed' || task.status === 'unavailable'" class="thumb-badge failed">!</div>
        <button
          v-if="task.status === 'failed' || task.status === 'unavailable'"
          class="thumb-retry"
          type="button"
          :disabled="task.retrying"
          @click.stop="store.retryTask(task)"
        >
          {{ t(task.status === 'unavailable' ? 'action.resume' : 'action.retry') }}
        </button>

        <!-- 下载按钮 -->
        <a
          v-if="task.status === 'succeeded' && task.result?.download_url"
          class="thumb-download"
          :href="task.result.download_url"
          :download="task.result.download_name || task.originalName"
          :aria-label="t('action.download') + ' ' + task.originalName"
          @click.stop
        >
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
            <path d="M7 2v7M4 7l3 3 3-3M3 12h8" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </a>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAppStore } from '../stores/app'
import { createBlobUrlPool } from '../utils/blob-urls.js'

const { t } = useI18n()
const store = useAppStore()

const thumbUrls = ref([])
const blobUrls = createBlobUrlPool()

function rebuildThumbUrls() {
  const localFiles = []
  thumbUrls.value = store.tasks.map(task => {
    if (task.status === 'succeeded' && task.result?.preview_url) {
      return task.result.thumbnail_url || task.result.preview_url
    }
    // 本地文件预览：复用已创建的 blob URL
    if (task.file) {
      localFiles.push(task.file)
      return blobUrls.get(task.file)
    }
    return null
  })
  blobUrls.retain(localFiles)
}

watch(() => store.tasks.map(task => [task.file, task.status, task.result?.thumbnail_url, task.result?.preview_url]),
  rebuildThumbUrls, { immediate: true })

onUnmounted(() => blobUrls.clear())

function onClickThumb(task) {
  store.setPreview(task)
}
</script>

<style scoped>
.thumbnail-strip {
  height: 92px;
  background: rgba(255, 255, 255, 0.78);
  backdrop-filter: saturate(180%) blur(20px);
  -webkit-backdrop-filter: saturate(180%) blur(20px);
  border-top: 0.5px solid rgba(0, 0, 0, 0.06);
  flex-shrink: 0;
  padding: 12px 32px;
}

@media (max-width: 768px) {
  .thumbnail-strip {
    height: 56px;
    padding: 6px 10px;
  }

  .thumb-item {
    width: 44px;
    height: 44px;
  }
}

.strip-scroll {
  display: flex;
  gap: 10px;
  overflow-x: auto;
  height: 100%;
  align-items: center;
}

.thumb-item {
  position: relative;
  width: 68px;
  height: 68px;
  border-radius: var(--radius-sm);
  overflow: hidden;
  cursor: pointer;
  flex-shrink: 0;
  border: 2.5px solid transparent;
  transition: all var(--duration-fast) var(--ease-apple);
  background: var(--color-bg);
  box-shadow: var(--shadow-sm);
}

.thumb-item:hover {
  box-shadow: var(--shadow-md);
  transform: translateY(-2px);
}

.thumb-item.active {
  border-color: var(--color-accent);
  box-shadow: 0 0 0 2.5px var(--color-accent), var(--shadow-md);
}

.thumb-item.succeeded {
  border-color: var(--color-success);
}

.thumb-item.failed {
  border-color: var(--color-error);
}

.thumb-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.thumb-loading {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, 0.72);
  backdrop-filter: blur(4px);
  -webkit-backdrop-filter: blur(4px);
}

.thumb-badge.failed {
  position: absolute;
  top: 2px;
  right: 2px;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--color-error);
  color: white;
  font-size: 10px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
}

.thumb-retry {
  position: absolute;
  left: 4px;
  right: 4px;
  bottom: 4px;
  height: 20px;
  border: 0;
  border-radius: 5px;
  background: rgba(255, 255, 255, 0.9);
  color: var(--color-error);
  font-size: 10px;
  font-weight: 700;
  line-height: 20px;
  padding: 0;
  cursor: pointer;
}

.thumb-retry:disabled {
  cursor: default;
  opacity: 0.72;
}

.thumb-download {
  position: absolute;
  bottom: 2px;
  right: 2px;
  width: 22px;
  height: 22px;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.88);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  color: var(--color-text);
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  transition: opacity var(--duration-fast) var(--ease-apple);
}

.thumb-item:hover .thumb-download {
  opacity: 1;
}
</style>
