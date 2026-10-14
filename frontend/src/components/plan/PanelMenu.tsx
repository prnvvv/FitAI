import { useEffect, useRef, useState } from 'react'
import type { KeyboardEvent as ReactKeyboardEvent, ReactNode } from 'react'

export interface PanelMenuItem {
  label: string
  onSelect: () => void
  disabled?: boolean
}

interface PanelMenuProps {
  /** Accessible label for the trigger button, e.g. "Day options". */
  triggerLabel: string
  /** Icon rendered inside the trigger. */
  trigger: ReactNode
  items: PanelMenuItem[]
}

/**
 * Small ⋯ menu: role=menu, arrow-key navigation, Esc closes and returns
 * focus to the trigger, outside click closes. No data logic inside.
 */
export function PanelMenu({ triggerLabel, trigger, items }: PanelMenuProps) {
  const [open, setOpen] = useState(false)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)
  const itemRefs = useRef<Array<HTMLButtonElement | null>>([])
  const wasOpen = useRef(false)

  useEffect(() => {
    if (!open) return
    wasOpen.current = true
    itemRefs.current[0]?.focus()
    const handleClick = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [open])

  // Return focus to the trigger when the menu closes (not on first mount).
  useEffect(() => {
    if (!open && wasOpen.current) triggerRef.current?.focus()
  }, [open])

  const close = () => setOpen(false)

  const focusItem = (index: number) => {
    const count = items.length
    const next = (index + count) % count
    itemRefs.current[next]?.focus()
  }

  const activeIndex = () => itemRefs.current.findIndex((el) => el === document.activeElement)

  const handleMenuKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Escape') {
      event.preventDefault()
      close()
      return
    }
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      focusItem(activeIndex() + 1)
      return
    }
    if (event.key === 'ArrowUp') {
      event.preventDefault()
      focusItem(activeIndex() - 1)
      return
    }
    if (event.key === 'Home') {
      event.preventDefault()
      focusItem(0)
      return
    }
    if (event.key === 'End') {
      event.preventDefault()
      focusItem(items.length - 1)
      return
    }
    if (event.key === 'Tab') {
      close()
    }
  }

  return (
    <div className="plan__menu-wrap" ref={menuRef}>
      <button
        ref={triggerRef}
        type="button"
        className="plan__menu-trigger"
        aria-label={triggerLabel}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        {trigger}
      </button>
      {open && (
        <div role="menu" aria-label={triggerLabel} className="plan__menu" onKeyDown={handleMenuKeyDown}>
          {items.map((item, index) => (
            <button
              key={item.label}
              ref={(el) => {
                itemRefs.current[index] = el
              }}
              type="button"
              role="menuitem"
              className="plan__menu-item"
              disabled={item.disabled}
              onClick={() => {
                close()
                item.onSelect()
              }}
            >
              {item.label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
