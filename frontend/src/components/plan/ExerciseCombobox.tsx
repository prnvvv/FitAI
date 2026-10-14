import { Check, Plus, Search } from 'lucide-react'
import { useEffect, useId, useMemo, useRef, useState } from 'react'
import { api, toMessage } from '../../services/api'
import type { Exercise } from '../../types'

interface ExerciseComboboxProps {
  value: string
  onChange: (value: string, exercise: Exercise | null) => void
  library: Exercise[]
  recent: Exercise[]
  placeholder?: string
  onLibraryChange?: (exercise: Exercise) => void
  error?: string | null
}

const MAX_RESULTS = 8

/**
 * Accessible exercise picker: searches the library by name and muscle group,
 * offers recently used entries, and allows creating a private custom exercise.
 * Free text is always accepted.
 */
export function ExerciseCombobox({
  value,
  onChange,
  library,
  recent,
  placeholder = 'Search exercises',
  onLibraryChange,
  error,
}: ExerciseComboboxProps) {
  const listId = useId()
  const [open, setOpen] = useState(false)
  const [activeIndex, setActiveIndex] = useState(-1)
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function onClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', onClickOutside)
    return () => document.removeEventListener('mousedown', onClickOutside)
  }, [])

  const matches = useMemo(() => {
    const term = value.trim().toLowerCase()
    const pool = term ? library : recent.length ? recent : library
    return pool
      .filter((exercise) => {
        if (!term) return true
        return (
          exercise.name.toLowerCase().includes(term) ||
          (exercise.primary_muscle_group ?? '').toLowerCase().includes(term)
        )
      })
      .slice(0, term ? MAX_RESULTS : 5)
  }, [library, recent, value])

  const exactMatch = library.some(
    (exercise) => exercise.name.toLowerCase() === value.trim().toLowerCase(),
  )
  const canCreate = value.trim().length > 1 && !exactMatch && !creating

  const select = (exercise: Exercise) => {
    onChange(exercise.name, exercise)
    onLibraryChange?.(exercise)
    setOpen(false)
    setActiveIndex(-1)
  }

  const createCustom = async () => {
    setCreating(true)
    setCreateError(null)
    try {
      const created = await api.createExercise({ name: value.trim() })
      onLibraryChange?.(created)
      onChange(created.name, created)
      setOpen(false)
    } catch (err) {
      setCreateError(toMessage(err, 'That exercise could not be created.'))
    } finally {
      setCreating(false)
    }
  }

  const handleKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setOpen(true)
      setActiveIndex((index) => Math.min(index + 1, matches.length - 1))
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      setActiveIndex((index) => Math.max(index - 1, -1))
    } else if (event.key === 'Enter') {
      const option = matches[activeIndex]
      if (open && option) {
        event.preventDefault()
        select(option)
      }
    } else if (event.key === 'Escape') {
      setOpen(false)
    }
  }

  return (
    <div className="combobox" ref={containerRef}>
      <div className="combobox__field">
        <Search size={14} aria-hidden className="combobox__icon" />
        <input
          type="text"
          className="plan__input"
          role="combobox"
          aria-expanded={open}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-label="Exercise"
          placeholder={placeholder}
          value={value}
          onChange={(event) => {
            onChange(event.target.value, null)
            setOpen(true)
            setActiveIndex(-1)
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={handleKeyDown}
        />
        {value.trim() && (
          <Check size={14} className="combobox__check" aria-hidden />
        )}
      </div>

      {open && (
        <ul className="combobox__list" id={listId} role="listbox" aria-label="Exercise suggestions">
          {!value.trim() && recent.length > 0 && (
            <li className="combobox__group" role="presentation">
              Recent
            </li>
          )}
          {matches.map((exercise, index) => (
            <li key={exercise.id} role="none">
              <button
                type="button"
                role="option"
                aria-selected={index === activeIndex}
                className={`combobox__option ${index === activeIndex ? 'combobox__option--active' : ''}`}
                onMouseEnter={() => setActiveIndex(index)}
                onClick={() => select(exercise)}
              >
                <span className="combobox__option-name">{exercise.name}</span>
                <span className="combobox__tags">
                  {exercise.primary_muscle_group && (
                    <span className="combobox__tag">{exercise.primary_muscle_group}</span>
                  )}
                  {exercise.equipment && (
                    <span className="combobox__tag combobox__tag--muted">{exercise.equipment}</span>
                  )}
                </span>
              </button>
            </li>
          ))}
          {matches.length === 0 && !canCreate && (
            <li className="combobox__empty" role="presentation">
              No matches yet — keep typing to create your own.
            </li>
          )}
          {canCreate && (
            <li role="none">
              <button type="button" className="combobox__option" onClick={createCustom} disabled={creating}>
                <span className="combobox__option-name">
                  <Plus size={14} aria-hidden /> {creating ? 'Creating…' : `Create “${value.trim()}”`}
                </span>
              </button>
            </li>
          )}
          {createError && (
            <li className="combobox__error" role="alert">
              {createError}
            </li>
          )}
        </ul>
      )}
      {error && (
        <p className="field__error" role="alert">
          {error}
        </p>
      )}
    </div>
  )
}
