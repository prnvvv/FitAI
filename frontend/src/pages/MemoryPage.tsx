import { Brain, Loader2, Trash2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api } from '../services/api'
import type { Memory } from '../types'

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return '-'
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  return JSON.stringify(value)
}

export function MemoryPage() {
  const [memories, setMemories] = useState<Memory[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api
      .listMemory()
      .then((page) => setMemories(page.items))
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  const handleDelete = async (id: string) => {
    if (!confirm('Forget this memory?')) return
    try {
      await api.deleteMemory(id)
      setMemories((prev) => prev.filter((m) => m.id !== id))
    } catch (err) {
      console.error(err)
    }
  }

  return (
    <div className="page page--memory">
      <header className="page__header">
        <h1>Memory</h1>
        <p>Facts FitAI remembers about you. Delete anything incorrect.</p>
      </header>

      {loading ? (
        <div className="page__loading">
          <Loader2 className="page__spinner" size={24} />
        </div>
      ) : memories.length === 0 ? (
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
              <button
                type="button"
                className="memory__delete"
                onClick={() => handleDelete(memory.id)}
                aria-label={`Delete ${memory.key}`}
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
