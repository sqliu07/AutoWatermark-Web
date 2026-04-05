import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 3000,
    proxy: {
      '/upload': 'http://localhost:5000',
      '/status': 'http://localhost:5000',
      '/download_zip': 'http://localhost:5000',
      '/download_temp_zip': 'http://localhost:5000',
    },
  },
  build: {
    outDir: '../static/dist',
    emptyOutDir: true,
  },
})
