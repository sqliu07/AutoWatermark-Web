import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 3000,
    proxy: {
      '/api': 'http://localhost:5000',
    },
  },
  build: {
    outDir: '../static/dist',
    emptyOutDir: true,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return undefined
          if (id.includes('ant-design-vue') || id.includes('@ant-design')) {
            return 'antd'
          }
          if (id.includes('/vue') || id.includes('pinia') || id.includes('vue-i18n')) {
            return 'vue-vendor'
          }
          return 'vendor'
        },
      },
    },
  },
})
