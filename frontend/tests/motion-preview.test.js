import test from 'node:test'
import assert from 'node:assert/strict'
import { extractMotionVideoBlob } from '../src/utils/motion-preview.js'

const mp4 = new Uint8Array([0, 0, 0, 16, 102, 116, 121, 112, 105, 115, 111, 109, 0, 0, 0, 0])

test('motion extraction reads only the bounded tail and returns the original blob slice', async () => {
  const file = new Blob([new Uint8Array(1024), mp4])
  const reads = []
  const source = {
    size: file.size,
    arrayBuffer() { assert.fail('the whole photo must not be read') },
    slice(start, end, type) {
      reads.push({ start, end, type })
      return file.slice(start, end, type)
    },
  }
  const result = await extractMotionVideoBlob(source, 32)
  assert.equal(reads[0].start, file.size - 32)
  assert.equal(reads[1].start, 1024)
  assert.equal(result.type, 'video/mp4')
  assert.deepEqual(new Uint8Array(await result.arrayBuffer()), mp4)
})

test('invalid box sizes and ordinary photos do not produce a video blob', async () => {
  const invalid = mp4.slice()
  invalid[3] = 255
  assert.equal(await extractMotionVideoBlob(new Blob([invalid])), null)
  assert.equal(await extractMotionVideoBlob(new Blob(['normal photo'])), null)
})
