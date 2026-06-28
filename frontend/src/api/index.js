import axios from 'axios'

const http = axios.create({ baseURL: '/api' })

http.interceptors.response.use(
  res => res,
  err => {
    const data = err.response?.data
    if (data?.error) {
      const e = new Error(data.error)
      e.code = err.response.status
      throw e
    }
    throw err
  },
)

export async function getStyles() {
  const { data } = await http.get('/styles')
  return data
}

export async function uploadFile(file, options) {
  const form = new FormData()
  form.append('file', file)
  form.append('watermark_type', options.watermark_type)
  form.append('image_quality', options.image_quality)
  form.append('burn_after_read', options.burn_after_read)
  if (options.logo_preference) {
    form.append('logo_preference', options.logo_preference)
  }

  const lang = localStorage.getItem('lang') || 'zh'
  const { data } = await http.post(`/upload?lang=${lang}`, form)
  return data
}

export async function getTaskStatus(taskId) {
  const { data } = await http.get(`/status/${taskId}`)
  return data
}

export async function confirmLogoChoice(taskId, logoPreference) {
  const { data } = await http.post('/upload/confirm_logo', {
    task_id: taskId,
    logo_preference: logoPreference,
  })
  return data
}

export async function confirmOptions(taskId, options) {
  const { data } = await http.post('/upload/confirm_options', {
    task_id: taskId,
    preserve_hdr: options.preserve_hdr,
    preserve_motion: options.preserve_motion,
  })
  return data
}

export async function downloadZip(items) {
  const { data } = await http.post('/download_zip', { items })
  return data
}

export function buildMotionVideoUrl(imageUrl) {
  // imageUrl: "/api/upload/xxx.jpg?token=...&expires=..."
  // 视频端点: "/api/upload/xxx.jpg/video?token=...&expires=..."
  const [path, query] = imageUrl.split('?')
  return `${path}/video${query ? '?' + query : ''}`
}
