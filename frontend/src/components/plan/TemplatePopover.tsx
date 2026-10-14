import { Loader2 } from 'lucide-react'
import { useEffect, useRef } from 'react'
import type { KeyboardEvent as ReactKeyboardEvent } from 'react'
import type { Template } from '../../types'

interface TemplatePopoverProps {
  open: boolean
  templates: Template[]
  templateKey: string
  templateDate: string
  applying: boolean
  onKeyChange: (value: string) => void
  onDateChange: (value: string) => void
  onApply: () => void
  onClose: () => void
}

/**
 * Compact "Start from a template" popover. Controlled by the parent: it only
 * renders when open and reports every change through the same state and
 * handlers the inline form used, so request behavior is unchanged.
 */
export function TemplatePopover({
  open,
  templates,
  templateKey,
  templateDate,
  applying,
  onKeyChange,
  onDateChange,
  onApply,
  onClose,
}: TemplatePopoverProps) {
  const panelRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    if (!panelRef.current?.contains(document.activeElement)) {
      panelRef.current?.querySelector<HTMLElement>('select, input, button')?.focus()
    }
    const handleClick = (event: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(event.target as Node)) onClose()
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [open, onClose])

  if (!open) return null

  const handleKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Escape') {
      event.preventDefault()
      onClose()
    }
  }

  return (
    <div
      ref={panelRef}
      role="dialog"
      aria-label="Start from a template"
      className="plan__popover"
      onKeyDown={handleKeyDown}
    >
      <div className="plan__popover-title">Start from a template</div>
      <label className="plan__field">
        <span className="plan__field-label">Template</span>
        <select
          className="plan__input plan__input--select"
          aria-label="Template"
          value={templateKey}
          onChange={(event) => onKeyChange(event.target.value)}
        >
          <option value="">Choose a template</option>
          {templates.map((template) => (
            <option key={template.key} value={template.key}>
              {template.name.replace(/_/g, ' ')}
            </option>
          ))}
        </select>
      </label>
      <label className="plan__field">
        <span className="plan__field-label">Start date</span>
        <input
          type="date"
          className="plan__input plan__input--date"
          aria-label="Template start date"
          value={templateDate}
          onChange={(event) => onDateChange(event.target.value)}
        />
      </label>
      <button
        type="button"
        className="profile__save plan__popover-apply"
        onClick={onApply}
        disabled={applying || !templateKey}
      >
        {applying ? <Loader2 className="page__spinner" size={16} /> : 'Apply'}
      </button>
    </div>
  )
}
