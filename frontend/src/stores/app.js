import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import * as api from '../api'
import { pollStatus, retryRequest } from '../api/polling.js'

const SERVER_CAPACITY = 8
const ACTIVE_STATUSES = new Set(['uploading', 'queued', 'processing'])
const TERMINAL_STATUSES = new Set(['succeeded', 'failed', 'cancelled'])

export const useAppStore = defineStore('app', () => {
  const files = ref([])
  const watermarkStyles = ref([])
  const selectedStyle = ref(1)
  const imageQuality = ref('high')
  const burnAfterRead = ref(false)
  const logoPreference = ref(null)
  const tasks = ref([])
  const currentPreview = ref(null)
  const stylesLoaded = ref(false)
  const isDownloadingZip = ref(false)
  const zipError = ref(null)

  let generation = 0
  let controller = new AbortController()
  let uploadRunner = null
  let uploadsPaused = false
  let zipRequest = null
  const polls = new Map()
  let batchLogoChoice = null
  let batchOptions = null

  const isProcessing = computed(() => tasks.value.some(task =>
    ACTIVE_STATUSES.has(task.status) || task.confirming || task.retrying))
  const hasActiveBatch = computed(() => tasks.value.some(task => !TERMINAL_STATUSES.has(task.status)))
  const completedCount = computed(() => tasks.value.filter(task => TERMINAL_STATUSES.has(task.status)).length)
  const totalCount = computed(() => tasks.value.length)
  const allDone = computed(() => tasks.value.length > 0 && !hasActiveBatch.value)
  const succeededTasks = computed(() => tasks.value.filter(task => task.status === 'succeeded'))
  const hasPendingOptions = computed(() => tasks.value.some(task => task.status === 'needs_options'))
  const hasPendingLogo = computed(() => tasks.value.some(task => task.status === 'needs_logo'))
  const canDownloadZip = computed(() => succeededTasks.value.length > 1 && succeededTasks.value.every(task => {
    const url = task.result?.download_url
    if (!url) return false
    return (new URLSearchParams(url.split('?')[1] || '').get('burn') || '0') === '0'
  }))

  async function loadStyles() {
    try {
      const data = await api.getStyles()
      watermarkStyles.value = data.styles || []
      selectedStyle.value = data.default_style_id ?? watermarkStyles.value[0]?.style_id ?? selectedStyle.value
    } catch {
      watermarkStyles.value = []
    } finally {
      stylesLoaded.value = true
    }
  }

  function isCurrent(task, epoch = generation) {
    return epoch === generation && tasks.value.includes(task)
  }

  function resetBatch() {
    generation++
    controller.abort()
    controller = new AbortController()
    polls.clear()
    uploadRunner = null
    uploadsPaused = false
    zipRequest = null
    isDownloadingZip.value = false
    zipError.value = null
    batchLogoChoice = null
    batchOptions = null
  }

  function addFiles(newFiles) {
    files.value = [...files.value, ...newFiles]
  }

  function clearFiles() {
    const waiting = tasks.value.filter(task => task.id && ['needs_logo', 'needs_options'].includes(task.status))
    resetBatch()
    files.value = []
    tasks.value = []
    currentPreview.value = null
    return Promise.allSettled(waiting.map(task => api.cancelTask(task.id)))
  }

  function reselectFiles() {
    clearFiles()
    requestAnimationFrame(() => document.querySelector('.upload-zone input[type="file"]')?.click())
  }

  function setPreview(task) {
    currentPreview.value = task
  }

  function showNextPrompt(fallback) {
    const next = tasks.value.find(task => task.status === 'needs_options')
      || tasks.value.find(task => task.status === 'needs_logo')
    if (next) currentPreview.value = next
    else if (fallback && isCurrent(fallback)) currentPreview.value = fallback
  }

  function applyOptionsResponse(task, response) {
    task.status = 'needs_options'
    task.stage = 'awaiting_options'
    task.features = response.features || task.features || {}
    task.preserveOptions = {
      preserve_hdr: response.preserve_hdr !== false,
      preserve_motion: response.preserve_motion !== false,
    }
    if (!currentPreview.value || !['needs_options', 'needs_logo'].includes(currentPreview.value.status)) {
      currentPreview.value = task
    }
  }

  function applyServerStatus(task, data) {
    if (data.status === 'cancelled') {
      markMissing(task)
      return true
    }
    task.status = data.status
    task.stage = data.stage || data.status
    task.progress = Math.max(task.progress, data.progress || 0)
    task.error = null
    if (data.status === 'succeeded') {
      task.progress = 1
      task.result = data.result
      task.lastFailedStep = null
      if (!currentPreview.value || ACTIVE_STATUSES.has(currentPreview.value.status)) currentPreview.value = task
    } else if (data.status === 'failed') {
      task.progress = 1
      task.error = data.error
      task.lastFailedStep = 'processing'
    } else if (data.status === 'needs_options') {
      applyOptionsResponse(task, data)
    }
    return TERMINAL_STATUSES.has(data.status) || ['needs_logo', 'needs_options'].includes(data.status)
  }

  function markUnavailable(task, error, step) {
    task.status = 'unavailable'
    task.error = error.message || 'Connection lost'
    task.lastFailedStep = step
  }

  function markMissing(task) {
    task.id = null
    task.status = 'failed'
    task.error = 'Task expired. Retry to upload the photo again.'
    task.lastFailedStep = 'upload'
  }

  function startPolling(task) {
    if (polls.has(task)) return polls.get(task)
    const epoch = generation
    const signal = controller.signal
    const job = (async () => {
      try {
        await pollStatus(timeout => api.getTaskStatus(task.id, timeout, { signal }), data => {
          if (!isCurrent(task, epoch)) return true
          return applyServerStatus(task, data)
        }, { interval: tasks.value.length > 1 ? 3000 : 2000, signal })
      } catch (error) {
        if (!isCurrent(task, epoch) || signal.aborted) return
        if (Number(error.response?.status ?? error.code) === 404) markMissing(task)
        else markUnavailable(task, error, task.lastFailedStep || 'processing')
      } finally {
        if (polls.get(task) === job) polls.delete(task)
        if (isCurrent(task, epoch)) scheduleUploads()
      }
    })()
    polls.set(task, job)
    return job
  }

  function submitWithBackoff(task, operation) {
    const epoch = generation
    const signal = controller.signal
    return retryRequest(operation, { signal, onWait: () => {
      if (isCurrent(task, epoch)) task.stage = 'waiting'
    } })
  }

  async function uploadTask(task) {
    const epoch = generation
    const signal = controller.signal
    task.status = 'uploading'
    task.stage = 'uploading'
    task.progress = 0
    task.uploadProgress = 0
    task.error = null
    task.result = null
    task.lastFailedStep = 'upload'
    const options = {
      ...task.options,
      logo_preference: task.lastLogoChoice || batchLogoChoice || task.options.logo_preference,
      ...(task.lastOptions || batchOptions || {}),
    }
    if (options.logo_preference) task.lastLogoChoice = options.logo_preference
    if (options.preserve_hdr != null || options.preserve_motion != null) {
      task.lastOptions = { preserve_hdr: options.preserve_hdr, preserve_motion: options.preserve_motion }
    }
    try {
      const response = await submitWithBackoff(task, () => api.uploadFile(task.file, options, {
        signal,
        onUploadProgress: event => {
          if (!isCurrent(task, epoch)) return
          const fraction = event.total > 0 ? event.loaded / event.total : event.progress
          if (Number.isFinite(fraction)) {
            task.uploadProgress = Math.max(task.uploadProgress, Math.min(1, fraction))
            task.progress = task.uploadProgress * 0.1
          }
        },
      }))
      if (!isCurrent(task, epoch)) return false
      task.id = response.task_id
      task.uploadProgress = 1
      task.lastFailedStep = null
      if (response.needs_logo_choice) {
        task.status = 'needs_logo'
        task.stage = 'awaiting_logo'
      } else if (response.needs_options) {
        applyOptionsResponse(task, response)
        if (batchOptions) await confirmTaskOptions(task, batchOptions)
      } else {
        task.status = 'processing'
        task.stage = 'queued'
        startPolling(task)
      }
      return true
    } catch (error) {
      if (!isCurrent(task, epoch) || signal.aborted) return false
      const status = Number(error.response?.status ?? error.code)
      if (!status || [408, 429, 503].includes(status)) {
        markUnavailable(task, error, 'upload')
        return false
      }
      task.status = 'failed'
      task.progress = 1
      task.error = error.message || 'Upload failed'
      return true
    }
  }

  function scheduleUploads() {
    if (uploadRunner) return uploadRunner
    if (uploadsPaused) return Promise.resolve()
    const epoch = generation
    const runner = (async () => {
      while (epoch === generation) {
        const outstanding = tasks.value.filter(task => task.id && !TERMINAL_STATUSES.has(task.status)).length
        if (outstanding >= SERVER_CAPACITY) break
        const next = tasks.value.find(task => task.status === 'pending')
        if (!next) break
        if (!await uploadTask(next)) {
          if (epoch === generation) uploadsPaused = true
          break
        }
      }
    })().finally(() => {
      if (uploadRunner !== runner) return
      uploadRunner = null
      // A poll can finish between the capacity check and this cleanup.
      const outstanding = tasks.value.filter(task => task.id && !TERMINAL_STATUSES.has(task.status)).length
      if (epoch === generation && !uploadsPaused && outstanding < SERVER_CAPACITY
          && tasks.value.some(task => task.status === 'pending')) scheduleUploads()
    })
    uploadRunner = runner
    return runner
  }

  async function processAll() {
    if (!files.value.length || hasActiveBatch.value) return
    resetBatch()
    const options = Object.freeze({
      watermark_type: selectedStyle.value,
      image_quality: imageQuality.value,
      burn_after_read: burnAfterRead.value ? '1' : '0',
      logo_preference: logoPreference.value,
    })
    tasks.value = files.value.map(file => ({
      id: null, file, options, originalName: file.name,
      status: 'pending', stage: 'pending', progress: 0, uploadProgress: 0,
      result: null, error: null, lastFailedStep: null,
      lastLogoChoice: null, lastOptions: null, retrying: false, confirming: false,
    }))
    currentPreview.value = tasks.value[0]
    await scheduleUploads()
  }

  async function confirmTaskLogo(task, choice) {
    if (!isCurrent(task) || task.confirming) return
    const epoch = generation
    const signal = controller.signal
    task.confirming = true
    task.lastLogoChoice = choice
    task.lastFailedStep = 'confirm_logo'
    task.error = null
    try {
      const response = await submitWithBackoff(task, () => api.confirmLogoChoice(task.id, choice, { signal }))
      if (!isCurrent(task, epoch)) return
      if (response.needs_options) applyOptionsResponse(task, response)
      else {
        task.status = 'processing'
        task.stage = 'queued'
        startPolling(task)
      }
      task.lastFailedStep = null
    } catch (error) {
      if (isCurrent(task, epoch) && !signal.aborted) markUnavailable(task, error, 'confirm_logo')
    } finally {
      task.confirming = false
    }
  }

  async function confirmTaskOptions(task, options) {
    if (!isCurrent(task) || task.confirming) return
    const epoch = generation
    const signal = controller.signal
    task.confirming = true
    task.lastOptions = { ...options }
    task.lastFailedStep = 'confirm_options'
    task.error = null
    try {
      await submitWithBackoff(task, () => api.confirmOptions(task.id, options, { signal }))
      if (!isCurrent(task, epoch)) return
      task.status = 'processing'
      task.stage = 'queued'
      task.lastFailedStep = null
      startPolling(task)
    } catch (error) {
      if (isCurrent(task, epoch) && !signal.aborted) markUnavailable(task, error, 'confirm_options')
    } finally {
      task.confirming = false
    }
  }

  async function processPendingLogoTasks(choice) {
    const epoch = generation
    logoPreference.value = choice
    batchLogoChoice = choice
    const pending = tasks.value.filter(task => task.status === 'needs_logo' && task.id)
    for (const task of pending) {
      await confirmTaskLogo(task, choice)
      if (epoch !== generation) return
      if (task.status === 'needs_options' && batchOptions) await confirmTaskOptions(task, batchOptions)
      if (epoch !== generation) return
      showNextPrompt(task)
    }
    showNextPrompt(pending[0])
    scheduleUploads()
  }

  async function processPendingOptionsTask(task, options, { applyAll = false } = {}) {
    if (!task || task.status !== 'needs_options' || !task.id) return
    const epoch = generation
    if (applyAll) batchOptions = { ...options }
    const pending = applyAll ? tasks.value.filter(item => item.status === 'needs_options' && item.id) : [task]
    for (const item of pending) {
      await confirmTaskOptions(item, options)
      if (epoch !== generation) return
      showNextPrompt(item)
    }
    showNextPrompt(task)
    scheduleUploads()
  }

  async function retryTask(task) {
    if (!task || !isCurrent(task) || !['failed', 'unavailable'].includes(task.status) || task.retrying) return
    const epoch = generation
    const signal = controller.signal
    task.retrying = true
    task.error = null
    try {
      if (!task.id) {
        uploadsPaused = false
        task.status = 'pending'
        await scheduleUploads()
        return
      }
      const data = await submitWithBackoff(task, () => api.getTaskStatus(task.id, 15000, { signal }))
      if (!isCurrent(task, epoch)) return
      applyServerStatus(task, data)
      if (data.status === 'failed') {
        const response = await submitWithBackoff(task, () => api.retryTask(task.id, { signal }))
        if (!isCurrent(task, epoch)) return
        task.id = response.task_id || task.id
        task.status = 'processing'
        task.stage = 'queued'
        task.progress = 0
        task.lastFailedStep = null
        startPolling(task)
      } else if (data.status === 'needs_logo') {
        if (task.lastLogoChoice) await confirmTaskLogo(task, task.lastLogoChoice)
        else currentPreview.value = task
      } else if (data.status === 'needs_options') {
        if (task.lastOptions) await confirmTaskOptions(task, task.lastOptions)
        else currentPreview.value = task
      } else if (!TERMINAL_STATUSES.has(data.status)) startPolling(task)
      scheduleUploads()
    } catch (error) {
      if (!isCurrent(task, epoch) || signal.aborted) return
      if (Number(error.response?.status ?? error.code) === 404) markMissing(task)
      else markUnavailable(task, error, task.lastFailedStep || 'processing')
    } finally {
      task.retrying = false
      if (isCurrent(task, epoch)) scheduleUploads()
    }
  }

  function downloadZip() {
    if (zipRequest) return zipRequest
    if (!canDownloadZip.value) return Promise.resolve()
    const epoch = generation
    const signal = controller.signal
    const items = succeededTasks.value.map(task => {
      const match = task.result.download_url.match(/\/download\/([^?]+)(?:\?(.*))?/)
      if (!match) return null
      const params = new URLSearchParams(match[2] || '')
      return {
        filename: match[1], token: params.get('token') || '', expires: params.get('expires') || '',
        burn: params.get('burn') || '0', action: params.get('action') || 'download',
      }
    }).filter(Boolean)
    if (!items.length) return Promise.resolve()
    isDownloadingZip.value = true
    zipError.value = null
    zipRequest = (async () => {
      try {
        const data = await api.downloadZip(items, { signal })
        if (epoch === generation && data.zip_url) window.location.assign(data.zip_url)
      } catch (error) {
        if (epoch === generation && !signal.aborted) zipError.value = error.message || 'ZIP download failed'
      } finally {
        if (epoch === generation) {
          isDownloadingZip.value = false
          zipRequest = null
        }
      }
    })()
    return zipRequest
  }

  return {
    files, watermarkStyles, selectedStyle, imageQuality, burnAfterRead, logoPreference,
    isProcessing, hasActiveBatch, tasks, currentPreview, completedCount, totalCount, allDone,
    succeededTasks, canDownloadZip, stylesLoaded, isDownloadingZip, zipError,
    loadStyles, addFiles, clearFiles, reselectFiles, setPreview, processAll, processPendingLogoTasks,
    processPendingOptionsTask, retryTask, downloadZip, hasPendingOptions, hasPendingLogo,
  }
})
