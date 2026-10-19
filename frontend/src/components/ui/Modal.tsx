import { X } from 'lucide-react'
import { useEffect, useRef } from 'react'
import type { ReactNode } from 'react'

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

interface ModalProps {
  open: boolean
  title: string
  /** Called for Esc, the close button and a backdrop click. */
  onClose: () => void
  children: ReactNode
  footer?: ReactNode
  bodyClassName?: string
  className?: string
}

/**
 * Modal dialog built on the app's existing `.modal` styles: focus trap, Esc to
 * close, focus returns to the element that opened it. Purely presentational —
 * the caller decides what a close request means (e.g. dirty-form handling).
 */
export function Modal({ open, title, onClose, children, footer, bodyClassName, className }: ModalProps) {
  const contentRef = useRef<HTMLDivElement>(null)
  const returnFocusRef = useRef<HTMLElement | null>(null)

  useEffect(() => {
    if (!open) return
    returnFocusRef.current = document.activeElement as HTMLElement | null
    const node = contentRef.current
    const first = node?.querySelector<HTMLElement>(FOCUSABLE)
    ;(first ?? node)?.focus()
    return () => {
      returnFocusRef.current?.focus()
    }
  }, [open])

  useEffect(() => {
    if (!open) return
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        onClose()
        return
      }
      if (event.key !== 'Tab') return
      const node = contentRef.current
      if (!node) return
      const focusable = [...node.querySelectorAll<HTMLElement>(FOCUSABLE)].filter(
        (el) => el.offsetParent !== null || el === document.activeElement,
      )
      if (focusable.length === 0) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }
    document.addEventListener('keydown', handleKey)
    return () => document.removeEventListener('keydown', handleKey)
  }, [open, onClose])

  if (!open) return null

  return (
    <div className={`modal modal--open ${className ?? ''}`}>
      <button type="button" className="modal__overlay" aria-label="Close dialog" onClick={onClose} />
      <div
        className="modal__content"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        ref={contentRef}
      >
        <div className="modal__header">
          <h3>{title}</h3>
          <button type="button" className="modal__close" onClick={onClose} aria-label="Close">
            <X size={16} />
          </button>
        </div>
        <div className={`modal__body ${bodyClassName ?? ''}`}>{children}</div>
        {footer && <div className="modal__footer">{footer}</div>}
      </div>
    </div>
  )
}