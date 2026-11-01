export function retryAfterMs(value, now = Date.now()) {
  if (value == null || String(value).trim() === '') return null
  const seconds = Number(value)
  if (Number.isFinite(seconds)) return seconds >= 0 ? seconds * 1000 : null
  const timestamp = Date.parse(value)
  return Number.isFinite(timestamp) ? Math.max(0, timestamp - now) : null
}

export function waitFor(ms, signal) {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(signal.reason)
    const abort = () => {
      clearTimeout(timer)
      reject(signal.reason)
    }
    const timer = setTimeout(() => {
      signal?.removeEventListener('abort', abort)
      resolve()
    }, ms)
    signal?.addEventListener('abort', abort, { once: true })
  })
}

export async function retryRequest(operation, {
  signal,
  onWait = () => {},
  maxAttempts = 6,
  maxDuration = 120000,
  now = Date.now,
  sleep = waitFor,
} = {}) {
  const deadline = now() + maxDuration
  for (let attempt = 0; ; attempt++) {
    signal?.throwIfAborted()
    try {
      return await operation()
    } catch (error) {
      signal?.throwIfAborted()
      const status = Number(error.response?.status ?? error.code)
      if (![429, 503].includes(status) || attempt + 1 >= maxAttempts || now() >= deadline) throw error
      const delay = Math.max(
        Math.min(30000, 2000 * 2 ** attempt),
        retryAfterMs(error.response?.headers?.['retry-after'], now()) ?? 0,
      )
      onWait(delay, status)
      await sleep(Math.min(delay, deadline - now()), signal)
      // Never retry earlier than Retry-After just because our own budget ended.
      if (now() >= deadline) throw error
    }
  }
}

export async function pollStatus(fetchStatus, onStatus, {
  interval = 2000,
  maxDuration = 300000,
  now = Date.now,
  sleep = waitFor,
  signal,
} = {}) {
  const deadline = now() + maxDuration
  let failures = 0
  while (now() < deadline) {
    signal?.throwIfAborted()
    let delay = interval
    let data
    try {
      data = await fetchStatus(Math.max(1, Math.min(15000, deadline - now())))
      failures = 0
    } catch (error) {
      signal?.throwIfAborted()
      if (error.response?.status === 404 || error.code === 404) throw error
      if (error.response?.status === 429 || error.code === 429) {
        failures = 0
        // Rate limiting is temporary; it does not indicate a failed task or connection.
        delay = Math.max(interval, retryAfterMs(error.response?.headers?.['retry-after'], now()) ?? 5000)
      } else {
        if (++failures >= 3) throw new Error('Connection lost')
        delay = interval * 2 ** (failures - 1)
      }
    }
    signal?.throwIfAborted()
    if (now() >= deadline) break
    if (data && onStatus(data)) return
    await sleep(Math.min(delay, Math.max(0, deadline - now())), signal)
  }
  throw new Error('Processing timeout')
}
