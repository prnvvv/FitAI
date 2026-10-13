import { FileText, Loader2, Trash2, Upload } from 'lucide-react'
import { useEffect, useState, type ChangeEvent } from 'react'
import { api } from '../services/api'
import type { Document } from '../types'

export function DocumentsPage() {
  const [documents, setDocuments] = useState<Document[]>([])
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)

  useEffect(() => {
    let cancelled = false
    api
      .listDocuments()
      .then((page) => {
        if (!cancelled) setDocuments(page.items)
      })
      .catch(console.error)
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const handleUpload = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    try {
      await api.uploadDocument(file)
      setLoading(true)
      const page = await api.listDocuments()
      setDocuments(page.items)
      setLoading(false)
    } catch (err) {
      console.error(err)
      alert('Upload failed')
    } finally {
      setUploading(false)
      e.target.value = ''
    }
  }

  const handleDelete = async (id: string) => {
    if (!confirm('Delete this document?')) return
    try {
      await api.deleteDocument(id)
      setDocuments((prev) => prev.filter((d) => d.id !== id))
    } catch (err) {
      console.error(err)
    }
  }

  return (
    <div className="page page--documents">
      <header className="page__header">
        <h1>Documents</h1>
        <p>Upload PDF, TXT, or DOCX files to extend FitAI's knowledge.</p>
      </header>

      <div className="page__section">
        <label className="documents__upload">
          <Upload size={20} />
          <span>{uploading ? 'Uploading…' : 'Upload document'}</span>
          <input type="file" accept=".pdf,.txt,.docx" onChange={handleUpload} disabled={uploading} />
        </label>
      </div>

      {loading ? (
        <div className="page__loading">
          <Loader2 className="page__spinner" size={24} />
        </div>
      ) : documents.length === 0 ? (
        <div className="page__empty">No documents uploaded yet.</div>
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
                  {doc.content_type} · {doc.status}
                </div>
              </div>
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
    </div>
  )
}
