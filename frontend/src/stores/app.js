import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import * as api from '../api'

export const useAppStore = defineStore('app', () => {
  // 上传的文件列表
  const files = ref([])
  // 水印样式列表（从后端加载）
  const watermarkStyles = ref([])
  // 当前选中样式
  const selectedStyle = ref(1)
  // 输出质量
  const imageQuality = ref('high')
  // 阅后即焚
  const burnAfterRead = ref(false)
  // Logo 偏好 (xiaomi/leica)
  const logoPreference = ref(null)

  // 处理状态
  const isProcessing = ref(false)
  const tasks = ref([]) // { id, file, originalName, status, progress, result, error }
  const currentPreview = ref(null) // 当前大预览的任务
  const stylesLoaded = ref(false)

  async function loadStyles() {
    try {
      const data = await api.getStyles()
      watermarkStyles.value = data.styles || []
      if (data.default_style_id != null) {
        selectedStyle.value = data.default_style_id
      } else if (watermarkStyles.value.length > 0) {
        selectedStyle.value = watermarkStyles.value[0].style_id
      }
      stylesLoaded.value = true
    } catch {
      stylesLoaded.value = true
    }
  }

  const completedCount = computed(() =>
    tasks.value.filter(t => t.status === 'succeeded' || t.status === 'failed').length
  )
  const totalCount = computed(() => tasks.value.length)
  const allDone = computed(() =>
    tasks.value.length > 0 && tasks.value.every(t => t.status === 'succeeded' || t.status === 'failed')
  )
  const succeededTasks = computed(() =>
    tasks.value.filter(t => t.status === 'succeeded')
  )

  function addFiles(newFiles) {
    files.value = [...files.value, ...newFiles]
  }

  function clearFiles() {
    files.value = []
    tasks.value = []
    currentPreview.value = null
  }

  function setPreview(task) {
    currentPreview.value = task
  }

  async function processAll() {
    if (files.value.length === 0) return
    isProcessing.value = true

    // 一次性创建所有 task，total 从一开始就确定
    tasks.value = files.value.map(file => ({
      id: null,
      file,
      originalName: file.name,
      status: 'pending',
      progress: 0,
      result: null,
      error: null,
    }))

    // 并发上传+轮询，限制并发数
    const concurrency = 3
    const queue = [...tasks.value]

    async function processOne(task) {
      task.status = 'uploading'
      task.progress = 0.05  // 上传开始
      try {
        const res = await api.uploadFile(task.file, {
          watermark_type: selectedStyle.value,
          image_quality: imageQuality.value,
          burn_after_read: burnAfterRead.value ? '1' : '0',
          logo_preference: logoPreference.value,
        })

        if (res.needs_logo_choice) {
          task.status = 'needs_logo'
          return
        }

        task.id = res.task_id
        task.status = 'processing'
        await pollTask(task)
      } catch (e) {
        task.status = 'failed'
        task.progress = 1
        task.error = e.message || 'Upload failed'
      }
    }

    const executing = new Set()
    for (const task of queue) {
      const p = processOne(task).then(() => executing.delete(p))
      executing.add(p)
      if (executing.size >= concurrency) {
        await Promise.race(executing)
      }
    }
    await Promise.all(executing)

    isProcessing.value = false
  }

  async function pollTask(task) {
    const interval = tasks.value.length > 1 ? 1000 : 200
    while (true) {
      try {
        const data = await api.getTaskStatus(task.id)
        task.progress = data.progress || 0
        task.status = data.status

        if (data.status === 'succeeded') {
          task.progress = 1
          task.result = data.result
          if (!currentPreview.value || currentPreview.value.status !== 'succeeded') {
            currentPreview.value = task
          }
          return
        }
        if (data.status === 'failed') {
          task.progress = 1
          task.error = data.error
          return
        }
      } catch {
        task.status = 'failed'
        task.progress = 1
        task.error = 'Connection lost'
        return
      }
      await new Promise(r => setTimeout(r, interval))
    }
  }

  async function downloadZip() {
    const filenames = succeededTasks.value
      .map(t => {
        const url = t.result?.processed_image
        if (!url) return null
        const match = url.match(/\/upload\/([^?]+)/)
        return match ? match[1] : null
      })
      .filter(Boolean)

    if (filenames.length === 0) return
    const data = await api.downloadZip(filenames)
    if (data.zip_url) {
      window.open(data.zip_url, '_blank')
    }
  }

  return {
    files, watermarkStyles, selectedStyle, imageQuality,
    burnAfterRead, logoPreference, isProcessing, tasks,
    currentPreview, completedCount, totalCount, allDone,
    succeededTasks, stylesLoaded, loadStyles, addFiles,
    clearFiles, setPreview, processAll, downloadZip,
  }
})
