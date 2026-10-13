import { Brain, Check, Loader2, Trash2, X } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { api } from '../services/api'
import type { Memory, PendingMemoryUpdate } from '../types'

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return '-'
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  return JSON.stringify(value)
}

export function MemoryPage() {
  const [memories, setMemories] = useState<Memory[]>([])
  const [pending, setPending] = useState<PendingMemoryUpdate[]>([])
  const [loading, setLoading] = useState(true)

  const load = useCallback(() => {
    Promise.all([api.listMemory(), api.listPendingMemory(50)])
      .then(([memoryPage, pendingPage]) => {
        setMemories(memoryPage.items)
        setPending(pendingPage.items.filter((p) => p.status === 'pending'))
      })
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const handleDelete = async (id: string) => {
    if (!confirm('Forget this memory?')) return
    try {
      await api.deleteMemory(id)
      setMemories((prev) => prev.filter((m) => m.id !== id))
    } catch (err) {
      console.error(err)
    }
  }

  const handleConfirm = async (id: string) => {
    if (!confirm('Apply this proposed memory update?')) return
    try {
      await api.confirmMemoryUpdate(id)
      load()
    } catch (err) {
      console.error(err)
      alert('Could not confirm the update.')
    }
  }

  const handleReject = async (id: string) => {
    try {
      await api.rejectMemoryUpdate(id)
      load()
    } catch (err) {
      console.error(err)
      alert('Could not reject the update.')
    }
  }

  return (
    <div className="page page--memory">
      <header className="page__header">
        <h1>Memory</h1>
        <p>Facts FitAI remembers about you. Confirm proposals, correct or delete anything wrong.</p>
      </header>

      {loading ? (
        <div className="page__loading">
          <Loader2 className="page__spinner" size={24} />
        </div>
      ) : (
        <>
          {pending.length > 0 && (
            <>
              <h2 className="memory__section-title">Proposed updates</h2>
              <ul className="memory__list">
                {pending.map((p) => (
                  <li key={p.id} className="memory__item">
                    <div className="memory__content">
                      <div className="memory__key">{p.key}</div>
                      <div className="memory__value">{formatValue(p.proposed_value)}</div>
                      {p.previous_value !== null && p.previous_value !== undefined && (
                        <div className="memory__meta">was {formatValue(p.previous_value)}</div>
                      )}
                      {p.reason && <div className="memory__meta">Reason: {p.reason}</div>}
                      <div className="memory__meta">confidence {p.confidence ?? '—'}</div>
                    </div>
                    <div className="memory__actions">
                      <button
                        type="button"
                        className="memory__approve"
                        onClick={() => handleConfirm(p.id)}
                        aria-label={`Confirm ${p.key}`}
                      >
                        <Check size={18} />
                      </button>
                      <button
                        type="button"
                        className="memory__delete"
                        onClick={() => handleReject(p.id)}
                        aria-label={`Reject ${p.key}`}
                      >
                        <X size={18} />
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            </>
          )}

          <h2 className="memory__section-title">Saved memories</h2>
          {memories.length === 0 ? (
            <div className="page__empty">
              <Brain size={48} />
              <p>No memories stored yet.</p>
              <span>Tell FitAI about your goals, preferences, and measurements.</span>
            </div>
          ) : (
            <ul className="memory__list">
              {memories.map((memory) => (
                <li key={memory.id} className="memory__item">
                  <div className="memory__content">
                    <div className="memory__key">{memory.key}</div>
                    <div className="memory__value">{formatValue(memory.value)}</div>
                    <div className="memory__meta">
                      {memory.status} · confidence {memory.confidence ?? '—'}
                    </div>
                  </div>
                  <div className="memory__actions">
                    <button
                      type="button"
                      className="memory__delete"
                      onClick={() => handleDelete(memory.id)}
                      aria-label={`Delete ${memory.key}`}
                    >
                      <Trash2 size={18} />
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  )
}