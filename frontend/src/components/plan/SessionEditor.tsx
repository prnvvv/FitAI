import { Minus, Plus, Trash2 } from 'lucide-react'
import type { Dispatch, SetStateAction } from 'react'
import type { Exercise } from '../../types'
import { ExerciseCombobox } from './ExerciseCombobox'
import { SegmentedControl } from './SegmentedControl'

export interface LoggedSet {
  exercise_name: string
  reps: number | ''
  weight: number | ''
  weight_unit: 'kg' | 'lb'
}

export function emptyLoggedSet(): LoggedSet {
  return { exercise_name: '', reps: '', weight: '', weight_unit: 'kg' }
}

interface SessionEditorProps {
  loggedName: string
  onLoggedName: (value: string) => void
  loggedSets: LoggedSet[]
  setLoggedSets: Dispatch<SetStateAction<LoggedSet[]>>
  library: Exercise[]
  recent: Exercise[]
  onLibraryExercise: (exercise: Exercise) => void
  /** Mutation error from the log request, or form validation. */
  error: string | null
}

const firstEmptyIndex = (sets: LoggedSet[]) => sets.findIndex((set) => !set.exercise_name.trim())

/**
 * Logged-session editor.
 *
 * Every row is a two-line CSS grid whose tracks are all `minmax(0, …)`, so a long
 * exercise name or a narrow container can never push the card into a horizontal
 * scroll: the combobox takes line 1 at full width and the numeric controls take
 * line 2 in a wrapping auto-fit grid.
 */
export function SessionEditor({
  loggedName,
  onLoggedName,
  loggedSets,
  setLoggedSets,
  library,
  recent,
  onLibraryExercise,
  error,
}: SessionEditorProps) {
  const emptyIndex = firstEmptyIndex(loggedSets)

  const update = (index: number, patch: Partial<LoggedSet>) =>
    setLoggedSets((prev) => prev.map((item, i) => (i === index ? { ...item, ...patch } : item)))

  return (
    <div className="editor">
      <label className="field editor__name">
        <span className="field__label">Session name</span>
        <input
          type="text"
          className="plan__input"
          placeholder="Optional"
          aria-label="Logged session name"
          value={loggedName}
          onChange={(event) => onLoggedName(event.target.value)}
        />
      </label>

      <div className="editor__rows">
        {loggedSets.map((set, index) => (
          <div key={index} className="editor__row">
            <div className="editor__row-head">
              <ExerciseCombobox
                value={set.exercise_name}
                library={library}
                recent={recent}
                onLibraryChange={onLibraryExercise}
                onChange={(value) => update(index, { exercise_name: value })}
              />
              <button
                type="button"
                className="editor__remove"
                aria-label="Remove set"
                onClick={() => setLoggedSets((prev) => prev.filter((_, i) => i !== index))}
              >
                <Trash2 size={16} />
              </button>
            </div>

            <div className="editor__fields">
              <div className="editor__field">
                <span className="editor__field-label">Reps</span>
                <Stepper
                  label="Reps"
                  value={set.reps}
                  onChange={(value) => update(index, { reps: value })}
                />
              </div>
              <div className="editor__field">
                <span className="editor__field-label">Weight</span>
                <Stepper
                  label="Weight"
                  value={set.weight}
                  step={2.5}
                  onChange={(value) => update(index, { weight: value })}
                />
              </div>
              <div className="editor__field">
                <span className="editor__field-label">Unit</span>
                <SegmentedControl
                  label="Weight unit"
                  name={`weight-unit-${index}`}
                  options={[
                    { value: 'kg', label: 'kg' },
                    { value: 'lb', label: 'lb' },
                  ]}
                  value={set.weight_unit}
                  onChange={(value) => update(index, { weight_unit: value as 'kg' | 'lb' })}
                />
              </div>
            </div>

            {/* Reserved line: the message appears without moving the rows. */}
            <p className="editor__error" role={index === emptyIndex ? 'alert' : undefined}>
              {index === emptyIndex ? error : null}
            </p>
          </div>
        ))}
      </div>

      <button
        type="button"
        className="editor__add"
        onClick={() => setLoggedSets((prev) => [...prev, emptyLoggedSet()])}
      >
        <Plus size={16} />
        Add exercise
      </button>
    </div>
  )
}

export function Stepper({
  label,
  value,
  step = 1,
  onChange,
}: {
  label: string
  value: number | ''
  step?: number
  onChange: (value: number | '') => void
}) {
  const decrement = () => {
    const current = value === '' ? 0 : Number(value)
    onChange(Math.max(0, current - step))
  }
  const increment = () => onChange((value === '' ? 0 : Number(value)) + step)
  return (
    <div className="stepper">
      <span className="stepper__label">{label}</span>
      <button type="button" className="stepper__btn" onClick={decrement} aria-label={`Decrease ${label}`}>
        <Minus size={14} />
      </button>
      <input
        type="number"
        className="stepper__input"
        aria-label={label}
        value={value}
        min={0}
        step={step}
        onChange={(event) =>
          onChange(event.target.value === '' ? '' : Number(event.target.value))
        }
      />
      <button type="button" className="stepper__btn" onClick={increment} aria-label={`Increase ${label}`}>
        <Plus size={14} />
      </button>
    </div>
  )
}