import { AlertCircle, Brain, Check, Loader2, Pencil, Trash2, X } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { useConfirmAction } from '../components/ui/ConfirmDialog'
import { useToast } from '../components/ui/Toast'
import { api } from '../services/api'
import type { Memory, PendingMemoryUpdate } from '../types'

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return '-'
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  if (Array.isArray(value)) return value.join(', ') || '-'
  return JSON.stringify(value)
}

function isNumberValue(value: unknown): boolean {
  return typeof value === 'number'
}

export function MemoryPage() {
  const confirmAction = useConfirmAction()
  const toast = useToast()
  const [memories, setMemories] = useState<Memory[]>([])
  const [pending, setPending] = useState<PendingMemoryUpdate[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editValue, setEditValue] = useState('')
  const [savingId, setSavingId] = useState<string | null>(null)

  const load = useCallback(() => {
    setLoading(true)
    setError(null)
    Promise.all([api.listMemory(), api.listPendingMemory(50)])
      .then(([memoryPage, pendingPage]) => {
        setMemories(memoryPage.items)
        setPending(pendingPage.items.filter((p) => p.status === 'pending'))
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : 'Could not load memory')
      })
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const handleDelete = (id: string) => {
    const key = memories.find((m) => m.id === id)?.key
    confirmAction.request({
      title: 'Forget this memory?',
      description: `FitAI will no longer remember${key ? ` “${key}”` : ' this'}. This cannot be undone.`,
      confirmLabel: 'Forget',
      onConfirm: async () => {
        await api.deleteMemory(id)
        toast.show('Memory forgotten', 'success')
        load()
      },
    })
  }

  const handleConfirm = async (id: string) => {
    try {
      await api.confirmMemoryUpdate(id)
      load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not confirm the update')
    }
  }

  const handleReject = async (id: string) => {
    try {
      await api.rejectMemoryUpdate(id)
      load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not reject the update')
    }
  }

  const startEdit = (memory: Memory) => {
    setEditingId(memory.id)
    setEditValue(formatValue(memory.value))
  }

  const cancelEdit = () => {
    setEditingId(null)
    setEditValue('')
  }

  const saveEdit = async (memory: Memory) => {
    let value: unknown = editValue.trim()
    if (value === '') {
      value = null
    } else if (isNumberValue(memory.value)) {
      const parsed = Number(value)
      if (Number.isNaN(parsed)) {
        setError('Please enter a valid number')
        return
      }
      value = parsed
    }

    setSavingId(memory.id)
    try {
      await api.correctMemory(memory.id, value)
      setEditingId(null)
      load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not update memory')
    } finally {
      setSavingId(null)
    }
  }

  return (
    <div className="page page--memory">
      <header className="page__header">
        <h1>Memory</h1>
        <p>Facts FitAI remembers about you. Confirm proposals, correct or delete anything wrong.</p>
      </header>

      {error && (
        <div className="page__alert page__alert--error">
          <AlertCircle size={18} />
          {error}
        </div>
      )}

      {loading ? (
        <div className="page__loading">
          <Loader2 className="page__spinner" size={24} />
        </div>
      ) : (
        <>
          {pending.length > 0 && (
            <section className="memory__section">
              <h2 className="memory__section-title">Proposed updates</h2>
              <ul className="memory__list">
                {pending.map((p) => (
                  <li key={p.id} className="memory__item memory__item--pending">
                    <div className="memory__content">
                      <div className="memory__key">{p.key}</div>
                      <div className="memory__value">{formatValue(p.proposed_value)}</div>
                      {p.previous_value !== null && p.previous_value !== undefined && (
                        <div className="memory__meta">was {formatValue(p.previous_value)}</div>
                      )}
                      {p.reason && <div className="memory__meta">{p.reason}</div>}
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
            </section>
          )}

          <section className="memory__section">
            <h2 className="memory__section-title">Saved memories</h2>
            {memories.length === 0 ? (
              <div className="page__empty">
                <Brain size={48} />
                <p>No memories stored yet.</p>
                <span>Tell FitAI about your goals, preferences, and measurements in chat.</span>
              </div>
            ) : (
              <ul className="memory__list">
                {memories.map((memory) => {
                  const isEditing = editingId === memory.id
                  return (
                    <li key={memory.id} className="memory__item">
                      <div className="memory__content">
                        <div className="memory__key">{memory.key}</div>
                        {isEditing ? (
                          <div className="memory__edit">
                            <input
                              type={isNumberValue(memory.value) ? 'number' : 'text'}
                              value={editValue}
                              onChange={(e) => setEditValue(e.target.value)}
                              onKeyDown={(e) => {
                                if (e.key === 'Enter') saveEdit(memory)
                                if (e.key === 'Escape') cancelEdit()
                              }}
                              disabled={savingId === memory.id}
                              autoFocus
                            />
                            <div className="memory__edit-actions">
                              <button
                                type="button"
                                className="memory__approve"
                                onClick={() => saveEdit(memory)}
                                disabled={savingId === memory.id}
                                aria-label="Save"
                              >
                                {savingId === memory.id ? (
                                  <Loader2 className="page__spinner" size={16} />
                                ) : (
                                  <Check size={16} />
                                )}
                              </button>
                              <button
                                type="button"
                                className="memory__delete"
                                onClick={cancelEdit}
                                disabled={savingId === memory.id}
                                aria-label="Cancel"
                              >
                                <X size={16} />
                              </button>
                            </div>
                          </div>
                        ) : (
                          <div className="memory__value">{formatValue(memory.value)}</div>
                        )}
                        {!isEditing && (
                          <div className="memory__meta">
                            confidence {memory.confidence ?? '—'} · updated{' '}
                            {new Date(memory.updated_at).toLocaleDateString()}
                          </div>
                        )}
                      </div>
                      {!isEditing && (
                        <div className="memory__actions">
                          <button
                            type="button"
                            className="memory__edit-btn"
                            onClick={() => startEdit(memory)}
                            aria-label={`Edit ${memory.key}`}
                          >
                            <Pencil size={18} />
                          </button>
                          <button
                            type="button"
                            className="memory__delete"
                            onClick={() => handleDelete(memory.id)}
                            aria-label={`Delete ${memory.key}`}
                          >
                            <Trash2 size={18} />
                          </button>
                        </div>
                      )}
                    </li>
                  )
                })}
              </ul>
            )}
          </section>
        </>
      )}
      {confirmAction.dialog}
    </div>
  )
}
