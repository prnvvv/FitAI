import { AlertCircle, FileText, Loader2, Trash2, Upload } from 'lucide-react'
import { useEffect, useState, type ChangeEvent } from 'react'
import { api } from '../services/api'
import { useConfirmAction } from '../components/ui/ConfirmDialog'
import { useToast } from '../components/ui/Toast'
import type { Document } from '../types'

function getStatusClass(status: string): string {
  const map: Record<string, string> = {
    pending: 'documents__status--pending',
    processing: 'documents__status--processing',
    indexed: 'documents__status--indexed',
    failed: 'documents__status--failed',
  }
  return `documents__status ${map[status] ?? ''}`
}

function formatStatus(status: string): string {
  if (status === 'indexed') return 'Ready'
  if (status === 'failed') return 'Failed'
  if (status === 'processing') return 'Processing'
  return 'Pending'
}

export function DocumentsPage() {
  const confirmAction = useConfirmAction()
  const toast = useToast()
  const [documents, setDocuments] = useState<Document[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const page = await api.listDocuments()
      setDocuments(page.items)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load documents')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const handleUpload = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    setError(null)
    try {
      await api.uploadDocument(file)
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed')
    } finally {
      setUploading(false)
      e.target.value = ''
    }
  }

  const handleDelete = (id: string) => {
    const name = documents.find((d) => d.id === id)?.filename
    confirmAction.request({
      title: 'Delete document?',
      description: `${name ? `"${name}"` : 'This document'} will be removed from your knowledge base. This cannot be undone.`,
      confirmLabel: 'Delete',
      onConfirm: async () => {
        await api.deleteDocument(id)
        setDocuments((prev) => prev.filter((d) => d.id !== id))
        toast.show('Document deleted', 'success')
      },
    })
  }

  return (
    <div className="page page--documents">
      <header className="page__header">
        <h1>Knowledge base</h1>
        <p>Upload PDF, TXT, or DOCX files to extend what FitAI knows about fitness and nutrition.</p>
      </header>

      {error && (
        <div className="page__alert page__alert--error">
          <AlertCircle size={18} />
          {error}
        </div>
      )}

      <div className="page__section">
        <label className={`documents__upload ${uploading ? 'documents__upload--busy' : ''}`}>
          {uploading ? <Loader2 className="page__spinner" size={20} /> : <Upload size={20} />}
          <span>{uploading ? 'Uploading…' : 'Upload document'}</span>
          <input type="file" accept=".pdf,.txt,.docx" onChange={handleUpload} disabled={uploading} />
        </label>
      </div>

      {loading ? (
        <div className="page__loading">
          <Loader2 className="page__spinner" size={24} />
        </div>
      ) : documents.length === 0 ? (
        <div className="page__empty">
          <FileText size={48} />
          <p>No documents uploaded yet.</p>
          <span>Your private docs stay yours and only appear in your searches.</span>
        </div>
      ) : (
        <ul className="documents__list">
          {documents.map((doc) => (
            <li key={doc.id} className="documents__item">
              <div className="documents__icon">
                <FileText size={24} />
              </div>
              <div className="documents__info">
                <div className="documents__name">{doc.filename}</div>
                <div className="documents__meta">
                  {doc.content_type} · {new Date(doc.created_at).toLocaleDateString()}
                </div>
              </div>
              <div className={getStatusClass(doc.status)}>{formatStatus(doc.status)}</div>
              <button
                type="button"
                className="documents__delete"
                onClick={() => handleDelete(doc.id)}
                aria-label={`Delete ${doc.filename}`}
              >
                <Trash2 size={18} />
              </button>
            </li>
          ))}
        </ul>
      )}
      {confirmAction.dialog}
    </div>
  )
}
