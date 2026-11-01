export function createBlobUrlPool(urlApi = URL) {
  const urls = new Map()

  function retain(files) {
    const active = new Set(files)
    for (const [file, url] of urls) {
      if (!active.has(file)) {
        urlApi.revokeObjectURL(url)
        urls.delete(file)
      }
    }
  }

  return {
    get(file) {
      if (!urls.has(file)) urls.set(file, urlApi.createObjectURL(file))
      return urls.get(file)
    },
    retain,
    clear() { retain([]) },
  }
}
