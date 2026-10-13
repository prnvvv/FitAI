import { Dumbbell, Loader2, Plus, Save, Trash2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api } from '../services/api'
import type { WorkoutSession } from '../types'

interface DraftSet {
  reps?: number
  weight_kg?: number
}

interface DraftExercise {
  name: string
  sets: DraftSet[]
}

function formatDate(value: string): string {
  return new Date(value).toLocaleString([], {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function WorkoutsPage() {
  const [sessions, setSessions] = useState<WorkoutSession[]>([])
  const [exercises, setExercises] = useState<DraftExercise[]>([])
  const [name, setName] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    api
      .listWorkouts(50)
      .then((page) => setSessions(page.items))
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  const addExercise = () => {
    if (!name.trim()) return
    setExercises((prev) => [
      ...prev,
      { name: name.trim(), sets: [{ reps: undefined, weight_kg: undefined }] },
    ])
    setName('')
  }

  const updateSet = (
    exerciseIndex: number,
    setIndex: number,
    field: keyof DraftSet,
    value: number,
  ) => {
    setExercises((prev) =>
      prev.map((ex, ei) =>
        ei === exerciseIndex
          ? {
              ...ex,
              sets: ex.sets.map((set, si) =>
                si === setIndex ? { ...set, [field]: value } : set,
              ),
            }
          : ex,
      ),
    )
  }

  const addSet = (exerciseIndex: number) => {
    setExercises((prev) =>
      prev.map((ex, ei) => (ei === exerciseIndex ? { ...ex, sets: [...ex.sets, {}] } : ex)),
    )
  }

  const saveSession = async () => {
    setSaving(true)
    try {
      const sets = exercises.flatMap((exercise) =>
        exercise.sets.map((set) => ({
          exercise_name: exercise.name,
          reps: set.reps,
          weight: set.weight_kg,
          weight_unit: set.weight_kg !== undefined ? 'kg' : undefined,
        })),
      )
      await api.createWorkout({ performed_at: new Date().toISOString(), sets })
      const page = await api.listWorkouts(50)
      setSessions(page.items)
      setExercises([])
    } catch (err) {
      console.error(err)
      alert('Failed to save workout')
    } finally {
      setSaving(false)
    }
  }

  const deleteSession = async (id: string) => {
    if (!confirm('Delete this workout?')) return
    try {
      await api.deleteWorkout(id)
      setSessions((prev) => prev.filter((s) => s.id !== id))
    } catch (err) {
      console.error(err)
    }
  }

  return (
    <div className="page page--workouts">
      <header className="page__header">
        <h1>Workouts</h1>
        <p>Log and review your sessions.</p>
      </header>

      <div className="workouts__add">
        <input
          type="text"
          placeholder="Exercise name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && addExercise()}
        />
        <button type="button" onClick={addExercise}>
          <Plus size={18} />
          Add exercise
        </button>
      </div>

      {exercises.length > 0 && (
        <>
          <ul className="workouts__list">
            {exercises.map((exercise, ei) => (
              <li key={ei} className="workouts__exercise">
                <div className="workouts__exercise-name">{exercise.name}</div>
                <div className="workouts__sets">
                  {exercise.sets.map((set, si) => (
                    <div key={si} className="workouts__set">
                      <label>
                        <span>Reps</span>
                        <input
                          type="number"
                          min={0}
                          value={set.reps ?? ''}
                          onChange={(e) =>
                            updateSet(ei, si, 'reps', Number(e.target.value))
                          }
                        />
                      </label>
                      <label>
                        <span>Weight (kg)</span>
                        <input
                          type="number"
                          min={0}
                          value={set.weight_kg ?? ''}
                          onChange={(e) =>
                            updateSet(ei, si, 'weight_kg', Number(e.target.value))
                          }
                        />
                      </label>
                    </div>
                  ))}
                </div>
                <button type="button" className="workouts__add-set" onClick={() => addSet(ei)}>
                  + Add set
                </button>
              </li>
            ))}
          </ul>
          <button
            type="button"
            className="profile__save"
            onClick={saveSession}
            disabled={saving}
            style={{ marginTop: 16 }}
          >
            {saving ? <Loader2 className="page__spinner" size={18} /> : <Save size={18} />}
            Save session
          </button>
        </>
      )}

      {loading ? (
        <div className="page__loading">
          <Loader2 className="page__spinner" size={24} />
        </div>
      ) : sessions.length === 0 && exercises.length === 0 ? (
        <div className="page__empty">
          <Dumbbell size={48} />
          <p>No workouts logged yet.</p>
          <span>Add exercises above to record your first session.</span>
        </div>
      ) : sessions.length > 0 ? (
        <ul className="workouts__list">
          {sessions.map((session) => (
            <li key={session.id} className="workouts__exercise">
              <div className="workouts__exercise-name">
                {session.name ?? formatDate(session.performed_at)}
              </div>
              <div className="workouts__sets">
                {session.sets.map((set) => (
                  <div key={set.id} className="workouts__set">
                    <span>
                      {set.exercise_name} · {set.reps ?? '—'} reps
                      {set.weight != null ? ` @ ${set.weight} ${set.weight_unit ?? ''}` : ''}
                    </span>
                  </div>
                ))}
              </div>
              <button
                type="button"
                className="memory__delete"
                onClick={() => deleteSession(session.id)}
                aria-label={`Delete workout ${session.name ?? session.performed_at}`}
              >
                <Trash2 size={18} />
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}