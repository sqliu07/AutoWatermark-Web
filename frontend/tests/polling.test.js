import test from 'node:test'
import assert from 'node:assert/strict'
import { pollStatus, retryAfterMs, retryRequest, waitFor } from '../src/api/polling.js'

function clock() {
  let time = 0
  const delays = []
  return { now: () => time, delays, sleep: async ms => { delays.push(ms); time += ms } }
}

test('successful polls retain their full interval', async () => {
  const c = clock()
  let calls = 0
  await pollStatus(async () => ({ status: ++calls === 3 ? 'succeeded' : 'processing' }),
    data => data.status === 'succeeded', { ...c, interval: 2000 })
  assert.deepEqual(c.delays, [2000, 2000])
})

test('repeated rate limits respect Retry-After without connection failure', async () => {
  const c = clock()
  let calls = 0
  await pollStatus(async () => {
    if (++calls < 5) throw { response: { status: 429, headers: { 'retry-after': '2' } } }
    return { status: 'succeeded' }
  }, () => true, { ...c, interval: 1000 })
  assert.deepEqual(c.delays, [2000, 2000, 2000, 2000])
})

test('rate limit wait and request timeout are capped by deadline', async () => {
  const c = clock()
  await assert.rejects(pollStatus(async timeout => {
    assert.equal(timeout, 5000)
    throw { response: { status: 429, headers: { 'retry-after': '3600' } } }
  }, () => false, { ...c, maxDuration: 5000 }), /Processing timeout/)
  assert.deepEqual(c.delays, [5000])
})

test('three transport failures are a connection error', async () => {
  const c = clock()
  await assert.rejects(pollStatus(async () => { throw new Error('network') },
    () => false, { ...c, interval: 1000 }), /Connection lost/)
  assert.deepEqual(c.delays, [1000, 2000])
})

test('Retry-After supports HTTP dates and rejects invalid values', () => {
  assert.equal(retryAfterMs('Sun, 13 Sep 2026 12:00:02 GMT', Date.parse('2026-09-13T12:00:00Z')), 2000)
  assert.equal(retryAfterMs('invalid', 0), null)
  assert.equal(retryAfterMs('-1', 0), null)
})

test('admission retries respect Retry-After and are bounded', async () => {
  const c = clock()
  let calls = 0
  const error = { response: { status: 503, headers: { 'retry-after': '5' } } }
  await assert.rejects(retryRequest(async () => { calls++; throw error },
    { ...c, maxAttempts: 3 }), value => value === error)
  assert.equal(calls, 3)
  assert.deepEqual(c.delays, [5000, 5000])
})

test('a Retry-After beyond the deadline never triggers an early retry', async () => {
  const c = clock()
  let calls = 0
  const error = { response: { status: 429, headers: { 'retry-after': '3600' } } }
  await assert.rejects(retryRequest(async () => { calls++; throw error },
    { ...c, maxDuration: 5000 }), value => value === error)
  assert.equal(calls, 1)
  assert.deepEqual(c.delays, [5000])
})

test('ordinary client errors are never automatically retried', async () => {
  let calls = 0
  await assert.rejects(retryRequest(async () => { calls++; throw { code: 400 } }), value => value.code === 400)
  assert.equal(calls, 1)
})

test('aborting a poll releases its interval timer promptly', async () => {
  const controller = new AbortController()
  const running = pollStatus(async () => ({ status: 'processing' }), () => false,
    { signal: controller.signal, interval: 60000 })
  await new Promise(resolve => setImmediate(resolve))
  controller.abort()
  await assert.rejects(running, error => error.name === 'AbortError')
  await assert.rejects(waitFor(60000, controller.signal), error => error.name === 'AbortError')
})
