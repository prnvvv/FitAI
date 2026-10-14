import {
  AlertCircle,
  FileText,
  Loader2,
  Pencil,
  RefreshCw,
  Trash2,
  Upload,
  X,
} from 'lucide-react'
import { useCallback, useEffect, useState, type ChangeEvent, type DragEvent } from 'react'
import { api } from '../services/api'
import { toMessage } from '../services/api'
import type { Document } from '../types'

function formatStatus(status: string): string {
  if (status === 'indexed') return 'Ready'
  if (status === 'failed') return 'Failed'
  if (status === 'processing') return 'Reading'
  return 'Queued'
}

/** "Image · JPEG", "Document · DOCX" — a friendly type instead of a raw MIME string. */
export function friendlyType(contentType: string, filename: string): string {
  const ext = (filename.split('.').pop() ?? '').toUpperCase()
  const shortExt = ext === 'JPEG' || ext === 'JPG' ? 'JPEG' : ext
  if (contentType.startsWith('image/')) return `Image${shortExt ? ` · ${shortExt}` : ''}`
  if (contentType === 'application/pdf') return 'Document · PDF'
  if (contentType.includes('wordprocessingml')) return 'Document · DOCX'
  if (contentType === 'text/markdown') return 'Document · Markdown'
  if (contentType.startsWith('text/')) return `Document · TXT`
  return shortExt ? `Document · ${shortExt}` : 'Document'
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
  const [busyId, setBusyId] = useState<string | null>(null)
  const [dragOver, setDragOver] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const [renamingId, setRenamingId] = useState<string | null>(null)
  const [renameValue, setRenameValue] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const page = await api.listDocuments()
      setDocuments(page.items)
    } catch (err) {
      setError(toMessage(err, 'Your library could not be loaded.'))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const handleUpload = async (file: File) => {
    setUploading(true)
    setError(null)
    try {
      const { duplicate } = await api.uploadDocument(file)
      setNotice(duplicate ? `Already in your library: ${file.name}` : null)
      await load()
    } catch (err) {
      setError(toMessage(err, `“${file.name}” could not be uploaded. Try again.`))
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

  const startRename = (doc: Document) => {
    setRenamingId(doc.id)
    setRenameValue(doc.filename)
  }

  const submitRename = async (id: string) => {
    setBusyId(id)
    try {
      const updated = await api.renameDocument(id, renameValue)
      setDocuments((prev) => prev.map((doc) => (doc.id === id ? updated : doc)))
      setRenamingId(null)
    } catch (err) {
      setError(toMessage(err, 'That item could not be renamed.'))
    } finally {
      setBusyId(null)
    }
  }

  const handleRetry = async (id: string) => {
    setBusyId(id)
    setError(null)
    try {
      await api.retryDocument(id)
      await load()
    } catch (err) {
      setError(toMessage(err, 'That file could not be reprocessed.'))
    } finally {
      setBusyId(null)
    }
  }

  const handleDelete = async (id: string) => {
    if (!confirm('Delete this item?')) return
    setBusyId(id)
    try {
      await api.deleteDocument(id)
      setDocuments((prev) => prev.filter((d) => d.id !== id))
    } catch (err) {
      setError(toMessage(err, 'That item could not be deleted.'))
    } finally {
      setBusyId(null)
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
        <div className="page__alert page__alert--error" role="alert">
          <AlertCircle size={18} />
          <span>{error}</span>
          <button type="button" className="page__alert-action" onClick={load}>
            Retry
          </button>
          <button type="button" className="page__alert-close" onClick={() => setError(null)} aria-label="Dismiss">
            <X size={16} />
          </button>
        </div>
      )}

      {notice && (
        <div className="page__alert page__alert--info" role="status">
          <span>{notice}</span>
          <button type="button" className="page__alert-close" onClick={() => setNotice(null)} aria-label="Dismiss">
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
                {renamingId === doc.id ? (
                  <form
                    className="library__rename"
                    onSubmit={(event) => {
                      event.preventDefault()
                      void submitRename(doc.id)
                    }}
                  >
                    <input
                      className="library__rename-input"
                      aria-label={`Rename ${doc.filename}`}
                      value={renameValue}
                      onChange={(event) => setRenameValue(event.target.value)}
                      autoFocus
                    />
                    <button type="submit" className="library__action">
                      Save
                    </button>
                    <button type="button" className="plan__nav-btn" onClick={() => setRenamingId(null)} aria-label="Cancel rename">
                      <X size={14} />
                    </button>
                  </form>
                ) : (
                  <div className="library__name">{doc.filename}</div>
                )}
                <div className="library__meta">
                  {friendlyType(doc.content_type, doc.filename)} ·{' '}
                  {(doc.size_bytes / 1024).toFixed(1)} KB ·{' '}
                  {new Date(doc.created_at).toLocaleDateString()}
                </div>
                {doc.status === 'failed' && doc.failure_reason && (
                  <p className="library__reason">{doc.failure_reason}</p>
                )}
              </div>
              <span className={statusClass(doc.status)}>{formatStatus(doc.status)}</span>
              <button
                type="button"
                className="library__icon-action"
                onClick={() => startRename(doc)}
                aria-label={`Rename ${doc.filename}`}
                disabled={busyId === doc.id || renamingId === doc.id}
                hidden={renamingId === doc.id}
              >
                <Pencil size={16} />
              </button>
              {doc.status === 'failed' && (
                <>
                  <button
                    type="button"
                    className="library__action"
                    onClick={() => void handleRetry(doc.id)}
                    disabled={busyId === doc.id}
                  >
                    {busyId === doc.id ? (
                      <Loader2 className="page__spinner" size={16} />
                    ) : (
                      <RefreshCw size={16} />
                    )}
                    Retry
                  </button>
                  <button
                    type="button"
                    className="library__delete"
                    onClick={() => void handleDelete(doc.id)}
                    aria-label={`Delete ${doc.filename}`}
                    disabled={busyId === doc.id}
                  >
                    <Trash2 size={16} />
                  </button>
                </>
              )}
              {doc.status !== 'failed' && (
                <button
                  type="button"
                  className="library__delete"
                  onClick={() => void handleDelete(doc.id)}
                  aria-label={`Delete ${doc.filename}`}
                  disabled={busyId === doc.id}
                >
                  <Trash2 size={16} />
                </button>
              )}
            </li>

          ))}
        </ul>
      )}
    </div>
  )
}
