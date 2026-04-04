<template>
  <div class="thumbnail-strip">
    <div class="strip-scroll">
      <div
        v-for="(task, i) in store.tasks"
        :key="i"
        class="thumb-item"
        :class="{
          active: store.currentPreview === task,
          succeeded: task.status === 'succeeded',
          failed: task.status === 'failed',
          processing: task.status === 'processing' || task.status === 'uploading',
        }"
        @click="onClickThumb(task)"
      >
        <img
          v-if="thumbUrls[i]"
          :src="thumbUrls[i]"
          class="thumb-img"
          :alt="task.originalName"
        />
        <div v-if="task.status === 'processing' || task.status === 'uploading'" class="thumb-loading">
          <a-spin size="small" />
        </div>
        <div v-if="task.status === 'failed'" class="thumb-badge failed">!</div>

        <!-- 下载按钮 -->
        <a
          v-if="task.status === 'succeeded' && task.result?.processed_image"
          class="thumb-download"
          :href="task.result.processed_image"
          :download="task.originalName"
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
import { ref, watch } from 'vue'
import { useAppStore } from '../stores/app'

const store = useAppStore()

// 为每个任务生成缩略图 URL（优先处理后的图，否则用原图）
const thumbUrls = ref([])

watch(() => store.tasks, (tasks) => {
  thumbUrls.value = tasks.map((task, i) => {
    if (task.status === 'succeeded' && task.result?.processed_image) {
      return task.result.processed_image
    }
    if (task.file) {
      return URL.createObjectURL(task.file)
    }
    return null
  })
}, { deep: true, immediate: true })

function onClickThumb(task) {
  store.setPreview(task)
}
</script>

<style scoped>
.thumbnail-strip {
  height: 88px;
  background: var(--color-surface);
  border-top: 1px solid var(--color-border-light);
  flex-shrink: 0;
  padding: 10px 20px;
}

.strip-scroll {
  display: flex;
  gap: 8px;
  overflow-x: auto;
  height: 100%;
  align-items: center;
}

.thumb-item {
  position: relative;
  width: 64px;
  height: 64px;
  border-radius: var(--radius-sm);
  overflow: hidden;
  cursor: pointer;
  flex-shrink: 0;
  border: 2px solid transparent;
  transition: all 0.15s ease;
  background: var(--color-bg);
}

.thumb-item:hover {
  border-color: var(--color-border);
  box-shadow: var(--shadow-sm);
}

.thumb-item.active {
  border-color: var(--color-accent);
  box-shadow: 0 0 0 1px var(--color-accent);
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
  background: rgba(255,255,255,0.7);
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

.thumb-download {
  position: absolute;
  bottom: 2px;
  right: 2px;
  width: 22px;
  height: 22px;
  border-radius: 4px;
  background: rgba(255,255,255,0.9);
  color: var(--color-text);
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  transition: opacity 0.15s;
}

.thumb-item:hover .thumb-download {
  opacity: 1;
}
</style>
