import { LayoutTemplate, Loader2 } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { KeyboardEvent as ReactKeyboardEvent } from 'react'
import type { Template } from '../../types'

interface TemplatePopoverProps {
  open: boolean
  templates: Template[]
  templateKey: string
  templateDate: string
  applying: boolean
  /** Days inside the template window that already carry a plan. */
  plannedDays?: string[]
  onKeyChange: (value: string) => void
  onDateChange: (value: string) => void
  onApply: () => void
  onClose: () => void
}

interface TemplateStats {
  days: number
  exercises: number
}

const DAY_MS = 86_400_000

/** `Template.days` is loosely typed on the wire; these read it safely. */
const templateDays = (template: Template): Record<string, unknown>[] =>
  Array.isArray(template.days) ? template.days : []
const dayExercises = (day: Record<string, unknown>): unknown[] =>
  Array.isArray(day.exercises) ? day.exercises : []
const dayTitle = (day: Record<string, unknown>): string =>
  typeof day.title === 'string' && day.title ? day.title : 'Session'

/**
 * Template picker.
 *
 * The backend applies a template by *creating* one planned session per template
 * day starting at the chosen date (`PlanService.apply_template`); it never
 * touches the log editor and never replaces existing rows. The copy below
 * describes exactly that, and warns when the window already has plans.
 */
export function TemplatePopover({
  open,
  templates,
  templateKey,
  templateDate,
  applying,
  plannedDays = [],
  onKeyChange,
  onDateChange,
  onApply,
  onClose,
}: TemplatePopoverProps) {
  const panelRef = useRef<HTMLDivElement>(null)
  const itemRefs = useRef<Array<HTMLButtonElement | null>>([])
  const [confirming, setConfirming] = useState(false)

  const stats = useMemo(() => {
    const map: Record<string, TemplateStats> = {}
    for (const template of templates) {
      const days = templateDays(template)
      map[template.key] = {
        days: days.length,
        exercises: days.reduce((total, day) => total + dayExercises(day).length, 0),
      }
    }
    return map
  }, [templates])

  const selected = templates.find((template) => template.key === templateKey) ?? null

  const windowDates = useMemo(() => {
    if (!selected) return []
    const start = new Date(`${templateDate}T12:00:00`)
    if (Number.isNaN(start.getTime())) return []
    return Array.from({ length: templateDays(selected).length }, (_, index) => {
      const date = new Date(start.getTime() + index * DAY_MS)
      return date.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' })
    })
  }, [selected, templateDate])

  const clashes = useMemo(() => {
    if (!selected || !templateDate) return []
    const start = new Date(`${templateDate}T12:00:00`)
    if (Number.isNaN(start.getTime())) return []
    const days = templateDays(selected).length
    const wanted = new Set<string>()
    for (let index = 0; index < days; index += 1) {
      const date = new Date(start.getTime() + index * DAY_MS)
      wanted.add(
        `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`,
      )
    }
    return plannedDays.filter((day) => wanted.has(day))
  }, [plannedDays, selected, templateDate])

  // Resetting on close (not on open) keeps this out of the open effect.
  const close = useCallback(() => {
    setConfirming(false)
    onClose()
  }, [onClose])

  useEffect(() => {
    if (!open) return
    const first = panelRef.current?.querySelector<HTMLElement>('[role="radio"], input, button')
    first?.focus()
    const handleClick = (event: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(event.target as Node)) close()
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [open, close])

  if (!open) return null

  const focusItem = (index: number) => {
    const count = templates.length
    if (count === 0) return
    itemRefs.current[((index % count) + count) % count]?.focus()
  }

  const handleKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Escape') {
      event.preventDefault()
      event.stopPropagation()
      close()
      return
    }
    const current = templates.findIndex((template) => template.key === templateKey)
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      focusItem(current + 1)
      return
    }
    if (event.key === 'ArrowUp') {
      event.preventDefault()
      focusItem(current - 1)
      return
    }
    if (event.key === 'Home') {
      event.preventDefault()
      focusItem(0)
      return
    }
    if (event.key === 'End') {
      event.preventDefault()
      focusItem(templates.length - 1)
    }
  }

  return (
    <div
      ref={panelRef}
      role="dialog"
      aria-modal="false"
      aria-label="Start from a template"
      className="templates"
      onKeyDown={handleKeyDown}
    >
      <div className="templates__head">
        <LayoutTemplate size={16} />
        <span className="templates__title">Start from a template</span>
      </div>

      <div className="templates__list" role="radiogroup" aria-label="Template">
        {templates.length === 0 && <p className="plan__hint">No templates available.</p>}
        {templates.map((template, index) => {
          const stat = stats[template.key]
          const active = template.key === templateKey
          return (
            <button
              key={template.key}
              ref={(el) => {
                itemRefs.current[index] = el
              }}
              type="button"
              role="radio"
              aria-checked={active}
              className={`templates__row${active ? ' templates__row--active' : ''}`}
              onClick={() => onKeyChange(template.key)}
            >
              <span className="templates__name">{template.name.replace(/_/g, ' ')}</span>
              <span className="templates__meta">
                {stat.days} {stat.days === 1 ? 'day' : 'days'} · {stat.exercises}{' '}
                {stat.exercises === 1 ? 'exercise' : 'exercises'}
              </span>
            </button>
          )
        })}
      </div>

      {selected && (
        <div className="templates__preview">
          <span className="templates__preview-label">Adds these days</span>
          <ul className="templates__days">
            {templateDays(selected).map((day, index) => (
              <li key={`${dayTitle(day)}-${index}`}>
                <span className="templates__day-name">{dayTitle(day)}</span>
                <span className="templates__day-date">{windowDates[index] ?? ''}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <label className="field">
        <span className="field__label">Start date</span>
        <input
          type="date"
          className="plan__input templates__date"
          aria-label="Template start date"
          value={templateDate}
          onChange={(event) => onDateChange(event.target.value)}
        />
      </label>

      {selected && clashes.length > 0 && (
        <p className="templates__warn" role="status">
          {clashes.length} {clashes.length === 1 ? 'day' : 'days'} in this window already{' '}
          {clashes.length === 1 ? 'has' : 'have'} a plan. Existing plans are kept — the template adds new
          sessions on top.
        </p>
      )}

      <p className="templates__note">
        {selected
          ? `Adds one planned session per template day, starting on ${templateDate}. Nothing already logged is changed.`
          : 'Choose a template to add its days to your plan.'}
      </p>

      {confirming && selected ? (
        <div className="templates__confirm" role="alertdialog" aria-label="Confirm template">
          <span>
            {clashes.length > 0
              ? `Add ${stats[selected.key]?.days ?? 0} planned sessions starting ${templateDate}?`
              : `Add this template starting ${templateDate}?`}
          </span>
          <div className="templates__confirm-actions">
            <button type="button" className="plan__text-btn" onClick={() => setConfirming(false)}>
              Cancel
            </button>
            <button
              type="button"
              className="profile__save"
              onClick={() => {
                setConfirming(false)
                onApply()
              }}
              disabled={applying}
            >
              {applying ? <Loader2 className="page__spinner" size={16} /> : 'Apply'}
            </button>
          </div>
        </div>
      ) : (
        <div className="templates__actions">
          <button type="button" className="plan__text-btn" onClick={close}>
            Close
          </button>
          <button
            type="button"
            className="profile__save"
            disabled={applying || !templateKey}
            onClick={() => {
              // Existing plans are kept, so this is a UI confirmation only: it
              // calls the same handler and issues exactly the same request.
              if (clashes.length > 0) setConfirming(true)
              else onApply()
            }}
          >
            {applying ? <Loader2 className="page__spinner" size={16} /> : 'Apply template'}
          </button>
        </div>
      )}
    </div>
  )
}