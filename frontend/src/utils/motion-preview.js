const MAX_TAIL_BYTES = 32 * 1024 * 1024

export async function extractMotionVideoBlob(file, maxTailBytes = MAX_TAIL_BYTES) {
  const offset = Math.max(0, file.size - maxTailBytes)
  const bytes = new Uint8Array(await file.slice(offset).arrayBuffer())
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength)
  for (let i = bytes.length - 8; i >= 4; i--) {
    if (bytes[i] === 0x66 && bytes[i + 1] === 0x74 && bytes[i + 2] === 0x79 && bytes[i + 3] === 0x70) {
      const start = i - 4
      const boxSize = view.getUint32(start)
      if (boxSize >= 8 && boxSize <= bytes.length - start) {
        return file.slice(offset + start, file.size, 'video/mp4')
      }
    }
  }
  return null
}
