import { Dumbbell, Plus } from 'lucide-react'
import { useState } from 'react'

interface WorkoutSet {
  reps?: number
  weight_kg?: number
}

interface Exercise {
  name: string
  sets: WorkoutSet[]
}

export function WorkoutsPage() {
  const [exercises, setExercises] = useState<Exercise[]>([])
  const [name, setName] = useState('')

  const addExercise = () => {
    if (!name.trim()) return
    setExercises((prev) => [...prev, { name: name.trim(), sets: [{ reps: undefined, weight_kg: undefined }] }])
    setName('')
  }

  const updateSet = (exerciseIndex: number, setIndex: number, field: keyof WorkoutSet, value: number) => {
    setExercises((prev) =>
      prev.map((ex, ei) =>
        ei === exerciseIndex
          ? {
              ...ex,
              sets: ex.sets.map((set, si) => (si === setIndex ? { ...set, [field]: value } : set)),
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

  return (
    <div className="page page--workouts">
      <header className="page__header">
        <h1>Workouts</h1>
        <p>Log a session manually. Richer workout history is coming soon.</p>
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

      {exercises.length === 0 ? (
        <div className="page__empty">
          <Dumbbell size={48} />
          <p>No exercises logged yet.</p>
        </div>
      ) : (
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
      )}
    </div>
  )
}
