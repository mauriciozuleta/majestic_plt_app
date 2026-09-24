import { API_BASE } from './apiBase'

// What the backend can turn into a knowledge-base index (mirrors
// INDEXABLE_EXTENSIONS in backend/knowledge_base/rag.py). Anything else can
// still be uploaded for people to download, just not indexed.
export const INDEXABLE_EXTENSIONS = ['.pdf', '.docx', '.xlsx', '.xlsm', '.txt', '.md', '.csv', '.json']

export function isIndexable(filename) {
  const dot = filename.lastIndexOf('.')
  return dot !== -1 && INDEXABLE_EXTENSIONS.includes(filename.slice(dot).toLowerCase())
}

async function readErrorDetail(response, fallbackMessage) {
  try {
    const payload = await response.json()
    if (payload?.detail) return payload.detail
  } catch {
    // Ignore parse errors and use fallback message.
  }
  return fallbackMessage
}

function readFileAsBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result).split(',')[1] ?? '')
    reader.onerror = () => reject(new Error('Could not read the selected file.'))
    reader.readAsDataURL(file)
  })
}

export async function fetchDocuments() {
  const response = await fetch(`${API_BASE}/documents`)
  if (!response.ok) throw new Error(await readErrorDetail(response, 'Failed to load documents'))
  return response.json()
}

export async function uploadDocument(file, addToKnowledgeBase) {
  const response = await fetch(`${API_BASE}/documents`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      filename: file.name,
      content_base64: await readFileAsBase64(file),
      add_to_knowledge_base: addToKnowledgeBase,
    }),
  })
  if (!response.ok) throw new Error(await readErrorDetail(response, 'Failed to upload the document'))
  return response.json()
}

export function documentDownloadUrl(documentId) {
  return `${API_BASE}/documents/${documentId}/download`
}

export async function addDocumentToKnowledgeBase(documentId) {
  const response = await fetch(`${API_BASE}/documents/${documentId}/add-to-knowledge-base`, { method: 'POST' })
  if (!response.ok) throw new Error(await readErrorDetail(response, 'Failed to add the document to the knowledge base'))
  return response.json()
}

export async function deleteDocument(documentId) {
  const response = await fetch(`${API_BASE}/documents/${documentId}`, { method: 'DELETE' })
  if (!response.ok) throw new Error(await readErrorDetail(response, 'Failed to delete the document'))
  return response.json()
}

export async function askKnowledgeBase(question) {
  const response = await fetch(`${API_BASE}/knowledge-base/ask`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question }),
  })
  if (!response.ok) throw new Error(await readErrorDetail(response, 'Failed to get an answer'))
  return response.json()
}
