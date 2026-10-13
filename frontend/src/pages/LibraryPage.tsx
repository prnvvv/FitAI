import { AlertCircle, FileText, Loader2, Trash2, Upload, X } from 'lucide-react'
import { useCallback, useEffect, useState, type ChangeEvent, type DragEvent } from 'react'
import { api } from '../services/api'
import { NetworkError } from '../services/api'
import type { Document } from '../types'

function formatStatus(status: string): string {
  if (status === 'indexed') return 'Ready'
  if (status === 'failed') return 'Failed'
  if (status === 'processing') return 'Reading'
  return 'Queued'
}

const POLL_INTERVAL_MS = 3000
const POLL_MAX_MS = 5 * 60 * 1000

function isUnsettled(status: string): boolean {
  return status === 'pending' || status === 'processing'
}

function statusClass(status: string): string {
  const map: Record<string, string> = {
    pending: 'library__status--pending',
    processing: 'library__status--reading',
    indexed: 'library__status--ready',
    failed: 'library__status--failed',
  }
  return `library__status ${map[status] ?? ''}`
}

export function LibraryPage() {
  const [documents, setDocuments] = useState<Document[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)
  const [dragOver, setDragOver] = useState(false)

  const load = useCallback(async (quiet = false) => {
    if (!quiet) {
      setLoading(true)
    }
    setError(null)
    try {
      const page = await api.listDocuments()
      setDocuments(page.items)
    } catch (err) {
      let message = err instanceof NetworkError
        ? 'The backend is unreachable. Check that the server is running, then retry.'
        : err instanceof Error
          ? err.message
          : 'Could not load library'
      try {
        if (err instanceof Error && !(err instanceof NetworkError)) {
          const m = err.message.match(/API error \d+:\s*(.+)/)
          if (m?.[1]) {
            message = m[1].replace(/^\{.*\}$/s, (raw) => {
              try {
                const parsed = JSON.parse(raw)
                return parsed?.error?.message || parsed?.message || raw
              } catch {
                return raw
              }
            })
          }
        }
      } catch {}
      setError(message)
    } finally {
      if (!quiet) {
        setLoading(false)
      }
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  // Indexing happens on the server after the upload response, so refresh while
  // any document is still settling instead of leaving it stuck on "Queued".
  const hasUnsettled = documents.some((d) => isUnsettled(d.status))
  useEffect(() => {
    if (!hasUnsettled) return
    let cancelled = false
    const startedAt = Date.now()
    let timer = 0

    const tick = async () => {
      if (cancelled) return
      if (Date.now() - startedAt > POLL_MAX_MS) return
      await load(true)
      if (cancelled) return
      timer = window.setTimeout(tick, POLL_INTERVAL_MS)
    }

    timer = window.setTimeout(tick, POLL_INTERVAL_MS)
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [hasUnsettled, load])

  const handleUpload = async (file: File) => {
    setUploading(true)
    setError(null)
    try {
      await api.uploadDocument(file)
      await load(true)
    } catch (err) {
      let message = err instanceof Error ? err.message : 'Upload failed'
      try {
        if (err instanceof Error) {
          const m = err.message.match(/API error \d+:\s*(.+)/)
          if (m?.[1]) {
            message = m[1].replace(/^\{.*\}$/s, (raw) => {
              try {
                const parsed = JSON.parse(raw)
                return parsed?.error?.message || parsed?.message || raw
              } catch {
                return raw
              }
            })
          }
        }
      } catch {}
      setError(message)
    } finally {
      setUploading(false)
    }
  }

  const handleFileInput = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    await handleUpload(file)
  }

  const handleDrop = async (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    setDragOver(false)
    const file = e.dataTransfer.files?.[0]
    if (!file) return
    await handleUpload(file)
  }

  const handleDelete = async (id: string) => {
    if (!confirm('Delete this item?')) return
    try {
      await api.deleteDocument(id)
      setDocuments((prev) => prev.filter((d) => d.id !== id))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not delete')
    }
  }

  return (
    <div className="page page--library">
      <header className="page__header page__header--row">
        <div>
          <h1>Library</h1>
          <p>Files and images FitAI can use when it answers you.</p>
        </div>
        <label className={`library__add-btn ${uploading ? 'library__add-btn--busy' : ''}`}>
          {uploading ? <Loader2 className="page__spinner" size={16} /> : <Upload size={16} />}
          <span>{uploading ? 'Adding…' : 'Add'}</span>
          <input type="file" accept=".pdf,.txt,.docx,.md,.png,.jpg,.jpeg,.webp" onChange={handleFileInput} disabled={uploading} />
        </label>
      </header>

      {error && (
        <div className="page__alert page__alert--error">
          <AlertCircle size={18} />
          <span>{error}</span>
          <button type="button" className="page__alert-action" onClick={() => load()}>
            Retry
          </button>
          <button type="button" className="page__alert-close" onClick={() => setError(null)} aria-label="Dismiss">
            <X size={16} />
          </button>
        </div>
      )}

      <div
        className={`library__drop ${dragOver ? 'library__drop--active' : ''}`}
        onDragOver={(e) => {
          e.preventDefault()
          setDragOver(true)
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
      >
        <Upload size={24} />
        <p>Drag and drop a file, or click Add.</p>
        <span>PDF, TXT, DOCX, MD, PNG, JPG, WEBP. Max 10 MB.</span>
      </div>

      {loading ? (
        <div className="page__loading">
          <Loader2 className="page__spinner" size={24} />
        </div>
      ) : documents.length === 0 ? (
        <div className="page__empty page__empty--compact">
          <FileText size={32} />
          <p>Nothing in your library yet.</p>
          <span>Add files or images and FitAI can reference them in chat.</span>
        </div>
      ) : (
        <ul className="library__list">
          {documents.map((doc) => (
            <li key={doc.id} className="library__item">
              <div className="library__icon">
                <FileText size={20} />
              </div>
              <div className="library__info">
                <div className="library__name">{doc.filename}</div>
                <div className="library__meta">
                  {doc.content_type} · {(doc.size_bytes / 1024).toFixed(1)} KB ·{' '}
                  {new Date(doc.created_at).toLocaleDateString()}
                </div>
              </div>
              <span className={statusClass(doc.status)}>{formatStatus(doc.status)}</span>
              <button
                type="button"
                className="library__delete"
                onClick={() => handleDelete(doc.id)}
                aria-label={`Delete ${doc.filename}`}
              >
                <Trash2 size={16} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
