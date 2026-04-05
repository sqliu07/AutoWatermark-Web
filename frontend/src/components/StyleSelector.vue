<template>
  <div class="style-grid">
    <div
      v-for="style in store.watermarkStyles"
      :key="style.style_id"
      class="style-card"
      :class="{ active: store.selectedStyle === style.style_id }"
      @click="store.selectedStyle = style.style_id"
    >
      <div class="style-preview">
        <img
          v-if="style.preview_image"
          :src="style.preview_image"
          :alt="styleName(style)"
          class="style-img"
        />
        <div v-else class="style-placeholder">{{ style.display_code || style.style_id }}</div>
      </div>
      <span class="style-name">{{ styleName(style) }}</span>
    </div>
  </div>
</template>

<script setup>
import { useI18n } from 'vue-i18n'
import { useAppStore } from '../stores/app'

const { locale } = useI18n()
const store = useAppStore()

function styleName(style) {
  return locale.value === 'zh' ? style.label_zh : style.label_en
}
</script>

<style scoped>
.style-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

@media (max-width: 768px) {
  .style-grid {
    grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  }
}

.style-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 6px 6px 8px;
  border: 2px solid var(--color-border-light);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all 0.15s ease;
  background: var(--color-surface);
}

.style-card:hover {
  border-color: var(--color-border);
  box-shadow: var(--shadow-sm);
}

.style-card.active {
  border-color: var(--color-accent);
  background: var(--color-surface-hover);
}

.style-preview {
  width: 100%;
  aspect-ratio: 4/3;
  border-radius: 4px;
  overflow: hidden;
  background: var(--color-bg);
}

.style-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  opacity: 0.85;
  transition: opacity 0.15s;
}

.style-card:hover .style-img,
.style-card.active .style-img {
  opacity: 1;
}

.style-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  font-weight: 700;
  color: var(--color-text-tertiary);
}

.style-name {
  font-size: 11px;
  font-weight: 600;
  color: var(--color-text-secondary);
  letter-spacing: 0.3px;
}

.style-card.active .style-name {
  color: var(--color-text);
}
</style>
