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
        <div class="style-mockup" v-html="getMockup(style.layout)"></div>
      </div>
      <span class="style-name">{{ style.name }}</span>
    </div>
  </div>
</template>

<script setup>
import { useAppStore } from '../stores/app'

const store = useAppStore()

const MOCKUPS = {
  split_lr: `<svg viewBox="0 0 60 50" fill="none"><rect x="5" y="2" width="50" height="36" rx="1" fill="#e8e5df"/><rect x="5" y="38" width="50" height="10" rx="1" fill="#f7f6f3" stroke="#e8e5df" stroke-width="0.5"/><rect x="8" y="40" width="16" height="3" rx="0.5" fill="#ccc"/><rect x="8" y="44" width="12" height="2" rx="0.5" fill="#ddd"/><line x1="36" y1="40" x2="36" y2="47" stroke="#ddd" stroke-width="0.5"/><rect x="39" y="40" width="14" height="3" rx="0.5" fill="#ccc"/><rect x="39" y="44" width="10" height="2" rx="0.5" fill="#ddd"/></svg>`,
  center_stack: `<svg viewBox="0 0 60 50" fill="none"><rect x="8" y="8" width="44" height="34" rx="2" fill="#e8e5df"/><circle cx="30" cy="22" r="6" fill="#ddd"/><rect x="20" y="34" width="20" height="3" rx="0.5" fill="#ccc"/></svg>`,
  film_frame: `<svg viewBox="0 0 60 50" fill="none"><rect x="10" y="4" width="40" height="30" rx="1" fill="#333" stroke="#222" stroke-width="0.5"/><rect x="12" y="6" width="36" height="26" fill="#e8e5df"/><rect x="18" y="38" width="24" height="3" rx="0.5" fill="#bbb"/><rect x="22" y="42" width="16" height="2" rx="0.5" fill="#ccc"/></svg>`,
}

const DEFAULT_MOCKUP = `<svg viewBox="0 0 60 50" fill="none"><rect x="5" y="2" width="50" height="36" rx="1" fill="#e8e5df"/><rect x="5" y="38" width="50" height="10" rx="1" fill="#f7f6f3" stroke="#e8e5df" stroke-width="0.5"/><rect x="8" y="40" width="16" height="3" rx="0.5" fill="#ccc"/><rect x="8" y="44" width="12" height="2" rx="0.5" fill="#ddd"/><rect x="42" y="40" width="10" height="6" rx="0.5" fill="#ddd"/></svg>`

function getMockup(layout) {
  return MOCKUPS[layout] || DEFAULT_MOCKUP
}
</script>

<style scoped>
.style-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.style-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 10px 8px 8px;
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
  aspect-ratio: 6/5;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  background: #fff;
}

.style-mockup {
  width: 80%;
}
.style-mockup :deep(svg) {
  width: 100%;
  height: auto;
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
