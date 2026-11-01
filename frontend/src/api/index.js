import axios from 'axios'

const http = axios.create({ baseURL: '/api', timeout: 30000 })
const language = () => encodeURIComponent(localStorage.getItem('lang') || 'zh')

http.interceptors.response.use(
  res => res,
  err => {
    const data = err.response?.data
    if (data?.error) {
      const e = new Error(data.error)
      e.code = err.response.status
      e.response = err.response
      throw e
    }
    throw err
  },
)

export async function getStyles() {
  const { data } = await http.get('/styles')
  return data
}

export async function uploadFile(file, options, { signal, onUploadProgress } = {}) {
  const form = new FormData()
  form.append('file', file)
  form.append('watermark_type', options.watermark_type)
  form.append('image_quality', options.image_quality)
  form.append('burn_after_read', options.burn_after_read)
  if (options.logo_preference) {
    form.append('logo_preference', options.logo_preference)
  }
  for (const name of ['preserve_hdr', 'preserve_motion']) {
    if (options[name] != null) form.append(name, String(options[name]))
  }

  const { data } = await http.post(`/upload?lang=${language()}`, form, {
    timeout: 180000, signal, onUploadProgress,
  })
  return data
}

export async function getTaskStatus(taskId, timeout = 15000, { signal } = {}) {
  const { data } = await http.get(`/status/${taskId}`, { timeout, signal })
  return data
}

export async function confirmLogoChoice(taskId, logoPreference, { signal } = {}) {
  const { data } = await http.post(`/upload/confirm_logo?lang=${language()}`, {
    task_id: taskId,
    logo_preference: logoPreference,
  }, { signal })
  return data
}

export async function confirmOptions(taskId, options, { signal } = {}) {
  const { data } = await http.post(`/upload/confirm_options?lang=${language()}`, {
    task_id: taskId,
    preserve_hdr: options.preserve_hdr,
    preserve_motion: options.preserve_motion,
  }, { signal })
  return data
}

export async function retryTask(taskId, { signal } = {}) {
  const { data } = await http.post(`/tasks/${taskId}/retry?lang=${language()}`, null, { signal })
  return data
}

export async function cancelTask(taskId) {
  const { data } = await http.post(`/tasks/${taskId}/cancel?lang=${language()}`, null, { timeout: 5000 })
  return data
}

export async function downloadZip(items, { signal } = {}) {
  const { data } = await http.post(`/download_zip?lang=${language()}`, { items }, { signal, timeout: 120000 })
  return data
}

export function buildMotionVideoUrl(imageUrl) {
  // imageUrl: "/api/upload/xxx.jpg?token=...&expires=..."
  // 视频端点: "/api/upload/xxx.jpg/video?token=...&expires=..."
  const [path, query] = imageUrl.split('?')
  return `${path}/video${query ? '?' + query : ''}`
}
