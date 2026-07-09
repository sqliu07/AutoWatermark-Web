<template>
  <Transition name="fade">
    <div v-if="src" class="fullscreen-overlay" @click="$emit('close')">
      <img :src="src" class="fullscreen-img" @click.stop />
      <button class="fullscreen-close" @click="$emit('close')">
        <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
          <path d="M4 4l10 10M14 4L4 14" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
        </svg>
      </button>
    </div>
  </Transition>
</template>

<script setup>
defineProps({
  src: { type: String, default: null },
})

defineEmits(['close'])
</script>

<style scoped>
.fullscreen-overlay {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.72);
  backdrop-filter: blur(20px) saturate(120%);
  -webkit-backdrop-filter: blur(20px) saturate(120%);
  cursor: zoom-out;
  animation: fullscreen-enter var(--duration-normal) var(--ease-apple);
}

@keyframes fullscreen-enter {
  from { opacity: 0; }
  to { opacity: 1; }
}

.fullscreen-img {
  max-width: 92vw;
  max-height: 92vh;
  object-fit: contain;
  border-radius: var(--radius-sm);
  cursor: default;
  animation: fullscreen-img-enter var(--duration-slow) var(--ease-spring);
}

@keyframes fullscreen-img-enter {
  from { opacity: 0; transform: scale(0.94); }
  to { opacity: 1; transform: scale(1); }
}

.fullscreen-close {
  position: absolute;
  top: 16px;
  right: 20px;
  width: 36px;
  height: 36px;
  border: none;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.15);
  color: white;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background var(--duration-fast) var(--ease-apple);
}

.fullscreen-close:hover {
  background: rgba(255, 255, 255, 0.3);
}
</style>
