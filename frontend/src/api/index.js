import axios from 'axios'

const http = axios.create({ baseURL: '/' })

export async function getStyles() {
  const { data } = await http.get('/api/styles')
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

export async function downloadZip(filenames) {
  const { data } = await http.post('/download_zip', { filenames })
  return data
}

export function buildMotionVideoUrl(imageUrl) {
  // imageUrl: "/upload/xxx.jpg?token=...&expires=..."
  // 视频端点: "/upload/xxx.jpg/video?token=...&expires=..."
  const [path, query] = imageUrl.split('?')
  return `${path}/video${query ? '?' + query : ''}`
}
