import test from 'node:test'
import assert from 'node:assert/strict'
import { createBlobUrlPool } from '../src/utils/blob-urls.js'

function urlApi() {
  let next = 0
  const revoked = []
  return { revoked, createObjectURL: () => `blob:${++next}`, revokeObjectURL: url => revoked.push(url) }
}

test('local thumbnails reuse a file URL until the file is removed', () => {
  const api = urlApi()
  const pool = createBlobUrlPool(api)
  const file = new Blob(['photo'])
  assert.equal(pool.get(file), pool.get(file))
  pool.retain([file])
  assert.deepEqual(api.revoked, [])
  pool.retain([])
  assert.deepEqual(api.revoked, ['blob:1'])
})

test('same-length replacement releases the previous file and retains shared files', () => {
  const api = urlApi()
  const pool = createBlobUrlPool(api)
  const first = new Blob(['first'])
  const shared = new Blob(['shared'])
  const replacement = new Blob(['replacement'])
  pool.get(first)
  pool.get(shared)
  pool.get(replacement)
  pool.retain([shared, replacement])
  assert.deepEqual(api.revoked, ['blob:1'])
  assert.equal(pool.get(shared), 'blob:2')
})

test('server-thumbnail replacement and unmount release every local URL exactly once', () => {
  const api = urlApi()
  const pool = createBlobUrlPool(api)
  pool.get(new Blob(['a']))
  pool.get(new Blob(['b']))
  pool.retain([])
  pool.clear()
  assert.deepEqual(api.revoked, ['blob:1', 'blob:2'])
})
