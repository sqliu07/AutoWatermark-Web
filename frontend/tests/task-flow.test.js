import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createPinia, setActivePinia } from 'pinia'

let harnessId = 0
const tick = () => new Promise(resolve => setImmediate(resolve))
const deferred = () => {
  let resolve, reject
  const promise = new Promise((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}

async function harness(t, overrides = {}, poll) {
  const api = {
    uploadFile: async file => ({ task_id: file.name }),
    getTaskStatus: async () => ({ status: 'succeeded', progress: 1, result: { preview_url: '/photo' } }),
    confirmOptions: async () => ({}),
    confirmLogoChoice: async () => ({}),
    retryTask: async id => ({ task_id: id }),
    cancelTask: async () => ({}),
    ...overrides,
  }
  const polling = await import('../src/api/polling.js')
  globalThis.__taskFlowApi = api
  globalThis.__taskFlowPolling = { ...polling, ...(poll ? { pollStatus: poll } : {}) }
  const piniaUrl = new URL('../node_modules/pinia/dist/pinia.mjs', import.meta.url).href
  const vueUrl = new URL('../node_modules/vue/dist/vue.runtime.esm-bundler.js', import.meta.url).href
  const source = (await readFile(new URL('../src/stores/app.js', import.meta.url), 'utf8'))
    .replace("from 'pinia'", `from '${piniaUrl}'`)
    .replace("from 'vue'", `from '${vueUrl}'`)
    .replace("import * as api from '../api'", 'const api = globalThis.__taskFlowApi')
    .replace(/import \{[^}]+\} from '\.\.\/api\/polling\.js'/, 'const { pollStatus, retryRequest } = globalThis.__taskFlowPolling')
  const { useAppStore } = await import(`data:text/javascript;base64,${Buffer.from(source + `\n// test ${++harnessId}`).toString('base64')}`)
  setActivePinia(createPinia())
  const store = useAppStore()
  t.after(() => { store.clearFiles(); store.$dispose() })
  return store
}


test('clearing a prompt-only batch releases its known server tasks', async t => {
  const cancelled = []
  const store = await harness(t, {
    uploadFile: async file => ({ task_id: file.name, needs_options: true }),
    cancelTask: async id => { cancelled.push(id) },
  })
  store.addFiles(Array.from({ length: 10 }, (_, n) => ({ name: `${n}.jpg` })))
  await store.processAll()
  assert.equal(store.tasks.filter(task => task.status === 'needs_options').length, 8)
  await store.clearFiles()
  assert.equal(cancelled.length, 8)
  assert.equal(store.tasks.length, 0)
})


test('a cancelled server task can be uploaded again without restarting the old task', async t => {
  let retries = 0
  const store = await harness(t, {
    getTaskStatus: async () => ({ status: 'cancelled' }),
    retryTask: async () => { retries++; return {} },
  }, async () => { throw new Error('Connection lost') })
  store.addFiles([{ name: 'cancelled.jpg' }])
  await store.processAll()
  await tick()
  await store.retryTask(store.tasks[0])
  assert.equal(store.tasks[0].id, null)
  assert.equal(store.tasks[0].lastFailedStep, 'upload')
  assert.equal(retries, 0)
})

test('a batch and its retries retain their original settings', async t => {
  const first = deferred()
  const sent = []
  const store = await harness(t, { uploadFile: async (file, options) => {
    sent.push({ ...options })
    if (sent.length === 1) return first.promise
    return { task_id: file.name }
  } })
  store.addFiles([1, 2, 3, 4].map(n => ({ name: `${n}.jpg` })))
  const running = store.processAll()
  await tick()
  store.selectedStyle = 5
  store.imageQuality = 'low'
  store.burnAfterRead = true
  first.resolve({ task_id: '1.jpg' })
  await running
  assert.equal(sent.length, 4)
  assert.ok(sent.every(options => options.watermark_type === 1 && options.image_quality === 'high' && options.burn_after_read === '0'))
  assert.ok(store.tasks.every(task => task.options.watermark_type === 1))
})

test('uploads are serialized independently of background polling', async t => {
  let active = 0, maximum = 0
  const store = await harness(t, { uploadFile: async file => {
    maximum = Math.max(maximum, ++active)
    await tick()
    active--
    return { task_id: file.name }
  } })
  store.addFiles([1, 2, 3].map(n => ({ name: `${n}.jpg` })))
  await store.processAll()
  assert.equal(maximum, 1)
})

test('retrying an upload retains its settings and actual upload progress', async t => {
  const captured = []
  const store = await harness(t, { uploadFile: async (file, options, request) => {
    captured.push({ ...options })
    if (captured.length === 1) throw { code: 400, message: 'bad upload' }
    request.onUploadProgress({ loaded: 50, total: 100 })
    assert.equal(store.tasks[0].uploadProgress, 0.5)
    return { task_id: file.name }
  } })
  store.addFiles([{ name: 'retry.jpg' }])
  await store.processAll()
  store.selectedStyle = 5
  await store.retryTask(store.tasks[0])
  assert.equal(captured[1].watermark_type, 1)
})

test('resuming a still-running task polls it without resubmitting', async t => {
  let polls = 0, retries = 0
  const store = await harness(t, {
    getTaskStatus: async () => ({ status: 'processing', progress: 0.5 }),
    retryTask: async () => { retries++; return {} },
  }, async (fetch, onStatus) => {
    if (++polls === 1) throw new Error('Connection lost')
    onStatus({ status: 'succeeded', progress: 1, result: { preview_url: '/done' } })
  })
  store.addFiles([{ name: 'running.jpg' }])
  await store.processAll()
  await tick()
  await store.retryTask(store.tasks[0])
  await tick()
  assert.equal(store.tasks[0].status, 'succeeded')
  assert.equal(retries, 0)
})

test('confirmation advances to the next prompt without awaiting rendering', async t => {
  const pollGate = deferred()
  const store = await harness(t, { uploadFile: async file => ({ task_id: file.name, needs_options: true }) },
    async (_fetch, _onStatus, { signal } = {}) => {
      signal?.addEventListener('abort', () => pollGate.resolve(), { once: true })
      return pollGate.promise
    })
  store.addFiles([{ name: 'first.jpg' }, { name: 'second.jpg' }])
  await store.processAll()
  const confirmation = store.processPendingOptionsTask(store.tasks[0], { preserve_hdr: true, preserve_motion: false })
  await Promise.race([confirmation, new Promise((_, reject) => setTimeout(() => reject(new Error('confirmation waited for rendering')), 100))])
  assert.equal(store.currentPreview, store.tasks[1])
  assert.equal(store.tasks[0].status, 'processing')
})

test('polling loss is recoverable and a successful backend task is never retried', async t => {
  let retries = 0
  const store = await harness(t, { retryTask: async () => { retries++; throw new Error('must not retry success') } },
    async () => { throw new Error('Connection lost') })
  store.addFiles([{ name: 'photo.jpg' }])
  await store.processAll()
  await tick()
  assert.equal(store.tasks[0].status, 'unavailable')
  await store.retryTask(store.tasks[0])
  assert.equal(store.tasks[0].status, 'succeeded')
  assert.equal(retries, 0)
})

test('more than eight waiting prompts pause the remaining upload queue', async t => {
  let uploads = 0
  const store = await harness(t, { uploadFile: async file => {
    uploads++
    return { task_id: file.name, needs_options: true }
  } })
  store.addFiles(Array.from({ length: 10 }, (_, n) => ({ name: `${n}.jpg` })))
  await store.processAll()
  assert.equal(uploads, 8)
  assert.deepEqual(store.tasks.slice(8).map(task => task.status), ['pending', 'pending'])
  await store.processPendingOptionsTask(store.tasks[0], { preserve_hdr: false, preserve_motion: false })
  await tick()
  await tick()
  assert.equal(uploads, 9)
  assert.equal(store.tasks.filter(task => task.status === 'failed').length, 0)
})

test('apply all confirms waiting tasks and supplies choices to later uploads', async t => {
  const confirmed = []
  const sent = []
  const store = await harness(t, {
    uploadFile: async (file, options) => { sent.push(options); return { task_id: file.name, needs_options: true } },
    confirmOptions: async (id, options) => { confirmed.push({ id, options }); return {} },
  })
  store.addFiles(Array.from({ length: 10 }, (_, n) => ({ name: `${n}.jpg` })))
  await store.processAll()
  const options = { preserve_hdr: false, preserve_motion: false }
  await store.processPendingOptionsTask(store.tasks[0], options, { applyAll: true })
  await tick()
  assert.ok(confirmed.length >= 8)
  assert.ok(sent.slice(8).every(value => value.preserve_hdr === false && value.preserve_motion === false))
})

test('clearing files aborts frontend work and ignores late responses', async t => {
  const gate = deferred()
  let signal
  const store = await harness(t, { uploadFile: async (_file, _options, request = {}) => {
    signal = request.signal
    return gate.promise
  } })
  store.addFiles([{ name: 'old.jpg' }])
  const running = store.processAll()
  await tick()
  store.clearFiles()
  gate.resolve({ task_id: 'stale-response' })
  await running
  assert.equal(signal?.aborted, true)
  assert.equal(store.tasks.length, 0)
  assert.equal(store.currentPreview, null)
})

test('ZIP requests suppress duplicates and expose errors without unhandled rejection', async t => {
  const gate = deferred()
  let requests = 0
  const store = await harness(t, { downloadZip: async () => { requests++; return gate.promise } })
  store.tasks = [1, 2].map(n => ({ status: 'succeeded', result: { download_url: `/api/download/${n}.jpg?token=abc&expires=9999999999&burn=0` } }))
  const first = store.downloadZip()
  const second = store.downloadZip()
  assert.equal(store.isDownloadingZip, true)
  assert.equal(requests, 1)
  gate.reject(new Error('Storage full'))
  await Promise.all([first, second])
  assert.equal(store.isDownloadingZip, false)
  assert.equal(store.zipError, 'Storage full')
})

test('a lost confirmation response resumes the running task without a duplicate POST', async t => {
  let confirmations = 0
  const store = await harness(t, {
    uploadFile: async () => ({ task_id: 'confirmed', needs_options: true }),
    confirmOptions: async () => { confirmations++; throw new Error('response lost') },
    getTaskStatus: async () => ({ status: 'processing', progress: 0.5 }),
  }, async (_fetch, onStatus) => onStatus({ status: 'succeeded', result: { preview_url: '/done' } }))
  store.addFiles([{ name: 'hdr.jpg' }])
  await store.processAll()
  await store.processPendingOptionsTask(store.tasks[0], { preserve_hdr: true, preserve_motion: false })
  assert.equal(store.tasks[0].status, 'unavailable')
  await store.retryTask(store.tasks[0])
  await tick()
  assert.equal(store.tasks[0].status, 'succeeded')
  assert.equal(confirmations, 1)
})

test('a backend-confirmed failed task is retried once', async t => {
  let retries = 0
  const store = await harness(t, {
    getTaskStatus: async () => ({ status: 'failed', error: 'renderer failed' }),
    retryTask: async id => { retries++; return { task_id: id } },
  }, async (fetch, onStatus) => onStatus(await fetch(15000)))
  store.addFiles([{ name: 'failed.jpg' }])
  await store.processAll()
  await tick()
  assert.equal(store.tasks[0].status, 'failed')
  await store.retryTask(store.tasks[0])
  assert.equal(retries, 1)
})

test('ZIP download uses same-page attachment navigation and discards stale replies', async t => {
  const oldWindow = globalThis.window
  const navigated = []
  globalThis.window = { location: { assign: value => navigated.push(value) } }
  t.after(() => { globalThis.window = oldWindow })
  const gate = deferred()
  let calls = 0
  const store = await harness(t, { downloadZip: async () => ++calls === 1 ? { zip_url: '/first.zip' } : gate.promise })
  const succeeded = () => [1, 2].map(n => ({ status: 'succeeded', result: { download_url: `/api/download/${n}.jpg?token=abc&expires=9999999999&burn=0` } }))
  store.tasks = succeeded()
  await store.downloadZip()
  assert.deepEqual(navigated, ['/first.zip'])
  const stale = store.downloadZip()
  store.clearFiles()
  gate.resolve({ zip_url: '/stale.zip' })
  await stale
  assert.deepEqual(navigated, ['/first.zip'])
})

test('upload API has a separate timeout and passes progress, cancellation and media choices', async t => {
  const oldStorage = globalThis.localStorage
  globalThis.localStorage = { getItem: () => 'en' }
  t.after(() => { globalThis.localStorage = oldStorage })
  const requests = []
  globalThis.__taskFlowAxios = { create: () => ({
    interceptors: { response: { use() {} } },
    post: async (url, body, options) => { requests.push({ url, body, options }); return { data: { task_id: 'api-task' } } },
  }) }
  const source = (await readFile(new URL('../src/api/index.js', import.meta.url), 'utf8'))
    .replace("import axios from 'axios'", 'const axios = globalThis.__taskFlowAxios')
  const { uploadFile } = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`)
  const signal = new AbortController().signal
  const onUploadProgress = () => {}
  await uploadFile(new File(['photo'], 'photo.jpg'), {
    watermark_type: 1, image_quality: 'high', burn_after_read: '0', preserve_hdr: true, preserve_motion: false,
  }, { signal, onUploadProgress })
  assert.equal(requests[0].options.timeout, 180000)
  assert.equal(requests[0].options.signal, signal)
  assert.equal(requests[0].options.onUploadProgress, onUploadProgress)
  assert.equal(requests[0].body.get('preserve_motion'), 'false')
  assert.equal(requests[0].body.get('preserve_hdr'), 'true')
  assert.equal(requests[0].url, '/upload?lang=en')
})
