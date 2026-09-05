/** Triggers a browser download of an in-memory blob — the client-side half
 * of any "download a generated file" flow, independent of what the blob
 * actually contains. */
export function triggerBlobDownload(blob, filename) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}
