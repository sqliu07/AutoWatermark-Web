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
  gap: 12px;
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
  gap: 8px;
  padding: 8px 8px 10px;
  border: 1.5px solid transparent;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease-apple);
  background: var(--color-surface);
  box-shadow: var(--shadow-sm);
  position: relative;
}

.style-card:hover {
  box-shadow: var(--shadow-md);
  transform: translateY(-2px);
}

.style-card.active {
  border-color: var(--color-accent);
  background: var(--color-accent-bg);
  box-shadow: 0 0 0 2px var(--color-accent), var(--shadow-md);
}

.style-card.active::after {
  content: '';
  position: absolute;
  top: 6px;
  right: 6px;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--color-accent);
}

.style-preview {
  width: 100%;
  aspect-ratio: 4/3;
  border-radius: 8px;
  overflow: hidden;
  background: var(--color-bg);
}

.style-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  opacity: 0.88;
  transition: all var(--duration-normal) var(--ease-apple);
}

.style-card:hover .style-img,
.style-card.active .style-img {
  opacity: 1;
  transform: scale(1.03);
}

.style-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  font-weight: 700;
  color: var(--color-text-tertiary);
}

.style-name {
  font-size: 12px;
  font-weight: 600;
  color: var(--color-text-secondary);
  letter-spacing: -0.2px;
}

.style-card.active .style-name {
  color: var(--color-accent);
  font-weight: 700;
}
</style>
