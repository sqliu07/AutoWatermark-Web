<template>
  <template v-if="task">
    <div class="compare-view">
      <div
        class="compare-card"
        @mouseenter="$emit('original-hover', true)"
        @mouseleave="$emit('original-hover', false)"
        @touchstart.passive="$emit('original-hover', true)"
        @touchend.passive="$emit('original-hover', false)"
      >
        <div class="compare-label">
          {{ t('compare.original') }}
          <span v-if="isMotion" class="motion-badge">LIVE</span>
        </div>
        <video
          v-if="isMotion && originalMotionPlaying && originalVideoUrl"
          :src="originalVideoUrl"
          class="compare-img"
          autoplay
          loop
          muted
          playsinline
        />
        <img
          v-else-if="originalUrl"
          :src="originalUrl"
          class="compare-img"
          :alt="task.originalName"
          decoding="async"
          @click="$emit('fullscreen', originalUrl)"
        />
      </div>
      <div class="compare-arrow">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
          <path d="M5 12h14M13 6l6 6-6 6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
      </div>
      <div
        class="compare-card result"
        @mouseenter="$emit('motion-hover', true)"
        @mouseleave="$emit('motion-hover', false)"
        @touchstart.passive="$emit('motion-hover', true)"
        @touchend.passive="$emit('motion-hover', false)"
      >
        <div class="compare-label">
          {{ t('compare.watermarked') }}
          <span v-if="isMotion" class="motion-badge">LIVE</span>
        </div>
        <video
          v-if="isMotion && motionPlaying"
          :src="motionVideoUrl"
          class="compare-img"
          autoplay
          loop
          muted
          playsinline
        />
        <img
          v-else
          :src="task.result.preview_url"
          class="compare-img"
          :alt="task.originalName"
          decoding="async"
          @click="$emit('fullscreen', task.result.full_preview_url || task.result.preview_url)"
        />
      </div>
    </div>

    <div class="action-bar">
      <span class="action-filename">{{ task.originalName }}</span>
      <div class="action-buttons">
        <a-button size="small" @click="$emit('fullscreen', task.result.full_preview_url || task.result.preview_url)">
          {{ t('action.preview') }}
        </a-button>
        <a-button
          type="primary"
          size="small"
          :href="task.result.download_url"
          :download="task.result.download_name || task.originalName"
          tag="a"
        >
          {{ t('action.download') }}
        </a-button>
        <a-button v-if="store.canDownloadZip" size="small" :loading="store.isDownloadingZip" :disabled="store.isDownloadingZip" @click="store.downloadZip()">
          {{ t(store.isDownloadingZip ? 'action.packing' : 'action.downloadAll') }}
        </a-button>
        <a-button size="small" @click="store.reselectFiles()">
          {{ t('upload.reselect') }}
        </a-button>
      </div>
    </div>
  </template>
</template>

<script setup>
import { useI18n } from 'vue-i18n'
import { useAppStore } from '../../stores/app'

defineProps({
  task: { type: Object, default: null },
  originalUrl: { type: String, default: null },
  originalVideoUrl: { type: String, default: null },
  motionVideoUrl: { type: String, default: null },
  isMotion: { type: Boolean, default: false },
  motionPlaying: { type: Boolean, default: false },
  originalMotionPlaying: { type: Boolean, default: false },
})

defineEmits(['fullscreen', 'motion-hover', 'original-hover'])

const { t } = useI18n()
const store = useAppStore()
</script>

<style scoped>
.compare-view {
  display: flex;
  align-items: center;
  gap: 16px;
  max-width: 100%;
  max-height: calc(100% - 50px);
  padding: 0 8px;
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
  letter-spacing: 0.5px;
  color: var(--color-text-tertiary);
}

.compare-img {
  max-width: 100%;
  max-height: 60vh;
  object-fit: contain;
  border-radius: var(--radius-sm);
  box-shadow: var(--shadow-sm);
  cursor: zoom-in;
  transition: box-shadow var(--duration-normal) var(--ease-apple);
}

.compare-img:hover {
  box-shadow: var(--shadow-md);
}

.compare-arrow {
  color: var(--color-text-tertiary);
  flex-shrink: 0;
}

.motion-badge {
  display: inline-block;
  font-size: 9px;
  font-weight: 600;
  letter-spacing: 0.3px;
  padding: 1px 6px;
  border-radius: 4px;
  background: #ff453a;
  color: #fff;
  vertical-align: middle;
  margin-left: 6px;
  animation: live-pulse 2s ease-in-out infinite;
}

@keyframes live-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.6; }
}

.action-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  max-width: 720px;
  padding: 10px 16px;
  background: rgba(255, 255, 255, 0.8);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border-radius: var(--radius-sm);
  border: 0.5px solid var(--color-border-light);
}

.action-filename {
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  letter-spacing: -0.2px;
}

.action-buttons {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

@media (max-width: 768px) {
  .compare-view {
    flex-direction: row;
    align-items: stretch;
    gap: 10px;
    width: 100%;
    flex: 0 1 auto;
    height: clamp(220px, 42dvh, 360px);
    max-height: none;
    min-height: 0;
    overflow-x: auto;
    overflow-y: hidden;
    scroll-snap-type: x mandatory;
    padding: 0 2px 6px;
  }

  .compare-arrow {
    display: none;
  }

  .compare-card {
    flex: 0 0 84%;
    height: 100%;
    justify-content: center;
    scroll-snap-align: center;
  }

  .compare-label {
    flex-shrink: 0;
  }

  .compare-img {
    max-height: calc(100% - 24px);
  }

  .action-bar {
    flex-shrink: 0;
    gap: 8px;
    padding: 7px 10px;
    max-width: 100%;
    align-items: flex-start;
  }

  .action-filename {
    min-width: 0;
  }

  .action-buttons {
    gap: 6px;
    flex-wrap: wrap;
    justify-content: flex-end;
  }
}
</style>
