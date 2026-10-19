import { Plus, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import type { KeyboardEvent as ReactKeyboardEvent } from 'react'
import { Menu } from '../ui/Menu'
import { Modal } from '../ui/Modal'
import { parseHeightInput, toDateKey } from '../../utils/dates'
import { METRICS, METRIC_BY_KEY } from './metrics'
import type { LoggableMetricKey, MetricKey } from './metrics'

export interface DraftMetric {
  key: LoggableMetricKey
  value: string
  unit: string
}

export interface LogPayload {
  date: string
  note: string
  drafts: DraftMetric[]
}

interface LogDialogProps {
  open: boolean
  units: 'metric' | 'imperial'
  /** Row focused when the dialog opens ("Log height" from the BMI prompt). */
  focusMetric: MetricKey
  saving: boolean
  /** Form-level failure from the API, shown as an inline banner. */
  error: string | null
  onDismiss: () => void
  onSubmit: (payload: LogPayload) => void
}

const DEFAULT_KEYS: DraftMetric['key'][] = ['weight', 'height']

const initialDrafts = (units: 'metric' | 'imperial'): DraftMetric[] =>
  DEFAULT_KEYS.map((key) => ({ key, value: '', unit: defaultUnit(key, units) }))

function defaultUnit(key: DraftMetric['key'], units: 'metric' | 'imperial'): string {
  if (units !== 'imperial') return METRIC_BY_KEY[key].canonicalUnit
  return METRIC_BY_KEY[key].altUnit ?? METRIC_BY_KEY[key].canonicalUnit
}

/** Same options the native select offered, including imperial feet-and-inches. */
function unitOptions(key: DraftMetric['key'], units: 'metric' | 'imperial'): string[] {
  if (key === 'height') return units === 'imperial' ? ['in', 'ft_in', 'cm'] : ['cm', 'in']
  if (key === 'weight') return ['kg', 'lb']
  return [METRIC_BY_KEY[key].canonicalUnit]
}

/** Canonical (kg/cm) value for a draft row, or null when the input is unusable. */
export function canonicalValue(draft: DraftMetric): number | null {
  if (draft.key === 'height') return parseHeightInput(draft.value, draft.unit)
  const raw = Number(draft.value)
  if (!Number.isFinite(raw)) return null
  if (draft.key === 'weight' && draft.unit === 'lb') return raw / 2.2046226
  return raw
}

export function validateDrafts(drafts: DraftMetric[]): {
  ok: boolean
  entries: { type: string; value: number; unit: string }[]
  errors: Record<string, string>
} {
  const entries: { type: string; value: number; unit: string }[] = []
  const errors: Record<string, string> = {}
  for (const draft of drafts) {
    if (draft.value.trim() === '') continue
    const def = METRIC_BY_KEY[draft.key]
    const canonical = canonicalValue(draft)
    if (canonical === null) {
      errors[draft.key] = 'Enter a number.'
      continue
    }
    if (canonical < def.min || canonical > def.max) {
      errors[draft.key] = `${def.label} must be between ${def.min} and ${def.max} ${def.canonicalUnit}.`
      continue
    }
    entries.push({
      type: draft.key,
      value: canonical,
      unit: draft.key === 'height' ? 'cm' : def.canonicalUnit,
    })
  }
  if (entries.length === 0 && Object.keys(errors).length === 0) {
    errors.form = 'Enter at least one measurement.'
  }
  // Any invalid field blocks the whole save so nothing is silently dropped.
  return { ok: entries.length > 0 && Object.keys(errors).length === 0, entries, errors }
}

export function LogDialog({ open, units, focusMetric, saving, error, onDismiss, onSubmit }: LogDialogProps) {
  const [date, setDate] = useState(() => toDateKey(new Date()))
  const [note, setNote] = useState('')
  const [drafts, setDrafts] = useState<DraftMetric[]>(() => initialDrafts(units))
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [confirmDiscard, setConfirmDiscard] = useState(false)
  const inputRefs = useRef<Record<string, HTMLInputElement | null>>({})

  useEffect(() => {
    if (!open) return
    setDate(toDateKey(new Date()))
    setNote('')
    setDrafts(initialDrafts(units))
    setErrors({})
    setConfirmDiscard(false)
  }, [open, units])

  useEffect(() => {
    if (!open) return
    const key = focusMetric === 'bmi' ? 'weight' : focusMetric
    ;(inputRefs.current[key] ?? inputRefs.current.weight)?.focus()
  }, [open, focusMetric])

  const today = toDateKey(new Date())
  const dirty = note.trim() !== '' || date !== today || drafts.some((draft) => draft.value.trim() !== '')
  const remaining = METRICS.filter((def) => !drafts.some((draft) => draft.key === def.key))

  const requestClose = () => {
    if (dirty) {
      setConfirmDiscard(true)
      return
    }
    onDismiss()
  }

  const handleSubmit = () => {
    const { ok, errors: found } = validateDrafts(drafts)
    setErrors(found)
    if (!ok) {
      const firstKey = Object.keys(found).find((key) => key !== 'form')
      if (firstKey) inputRefs.current[firstKey]?.focus()
      return
    }
    onSubmit({ date, note, drafts })
  }

  const update = (key: DraftMetric['key'], patch: Partial<DraftMetric>) =>
    setDrafts((prev) => prev.map((item) => (item.key === key ? { ...item, ...patch } : item)))

  const onMenuKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Escape') setConfirmDiscard(false)
  }

  return (
    <Modal
      open={open}
      title="Log measurements"
      onClose={requestClose}
      className="modal--progress"
      bodyClassName="log__body"
      footer={
        <div className="log__footer" onKeyDown={onMenuKeyDown}>
          <button type="button" className="btn btn--ghost" onClick={requestClose} disabled={saving}>
            Cancel
          </button>
          <button type="button" className="profile__save" onClick={handleSubmit} disabled={saving}>
            Save
          </button>
        </div>
      }
    >
      {confirmDiscard && (
        <div className="log__discard" role="alertdialog" aria-label="Discard changes?">
          <span>Discard changes?</span>
          <button type="button" className="btn btn--ghost" onClick={() => setConfirmDiscard(false)}>
            Keep editing
          </button>
          <button type="button" className="btn btn--danger-ghost" onClick={onDismiss}>
            Discard
          </button>
        </div>
      )}

      {error && (
        <div className="log__banner" role="alert">
          <span>{error}</span>
          <button type="button" className="log__retry" onClick={handleSubmit} disabled={saving}>
            Retry
          </button>
        </div>
      )}

      <div className="log__row log__row--meta">
        <label className="field">
          <span className="field__label">Date</span>
          <input
            type="date"
            className="plan__input log__input"
            value={date}
            onChange={(event) => setDate(event.target.value)}
          />
        </label>
        <label className="field">
          <span className="field__label">Note (optional)</span>
          <input
            type="text"
            className="plan__input log__input"
            value={note}
            onChange={(event) => setNote(event.target.value)}
          />
        </label>
      </div>

      {drafts.map((draft) => {
        const def = METRIC_BY_KEY[draft.key]
        const options = unitOptions(draft.key, units)
        const fieldId = `log-${draft.key}`
        const errorId = `${fieldId}-error`
        return (
          <div key={draft.key} className="log__row log__row--metric">
            <label className="field log__field">
              <span className="field__label">{def.label}</span>
              <span className="log__input-wrap">
                <input
                  ref={(el) => {
                    inputRefs.current[draft.key] = el
                  }}
                  id={fieldId}
                  type="text"
                  inputMode="decimal"
                  autoFocus={draft.key === focusMetric}
                  className="plan__input log__input log__input--suffix"
                  aria-label={def.label}
                  aria-invalid={errors[draft.key] ? true : undefined}
                  aria-describedby={errors[draft.key] ? errorId : undefined}
                  value={draft.value}
                  onChange={(event) => update(draft.key, { value: event.target.value })}
                />
                <span className="log__suffix">{draft.unit === 'ft_in' ? 'ft/in' : draft.unit}</span>
              </span>
            </label>
            {options.length > 1 ? (
              <div className="segmented segmented--unit" role="group" aria-label={`${def.label} unit`}>
                {options.map((option) => (
                  <button
                    key={option}
                    type="button"
                    className={draft.unit === option ? 'segmented__item--active' : undefined}
                    aria-pressed={draft.unit === option}
                    onClick={() => update(draft.key, { unit: option })}
                  >
                    {option === 'ft_in' ? 'ft/in' : option}
                  </button>
                ))}
              </div>
            ) : null}
            {!DEFAULT_KEYS.includes(draft.key) && (
              <button
                type="button"
                className="log__remove"
                aria-label={`Remove ${def.label}`}
                onClick={() => setDrafts((prev) => prev.filter((item) => item.key !== draft.key))}
              >
                <X size={16} />
              </button>
            )}
            {errors[draft.key] && (
              <p className="field__error" id={errorId} role="alert">
                {errors[draft.key]}
              </p>
            )}
          </div>
        )
      })}

      {errors.form && (
        <p className="field__error" role="alert">
          {errors.form}
        </p>
      )}

      {remaining.length > 0 && (
        <Menu
          label="Add metric"
          align="left"
          triggerClassName="btn btn--ghost log__add"
          trigger={
            <>
              <Plus size={16} />
              Add metric
            </>
          }
          items={remaining.map((def) => ({
            label: def.label,
            onSelect: () =>
              setDrafts((prev) => [...prev.filter((item) => item.key !== def.key), { key: def.key, value: '', unit: def.canonicalUnit }]),
          }))}
        />
      )}
    </Modal>
  )
}