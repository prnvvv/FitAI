import { useEffect, useRef, useState } from 'react'
import type { KeyboardEvent as ReactKeyboardEvent, ReactNode } from 'react'

export interface MenuItem {
  label: string
  onSelect: () => void
}

interface MenuProps {
  /** Accessible label for the trigger and the menu. */
  label: string
  trigger: ReactNode
  triggerClassName?: string
  items: MenuItem[]
  align?: 'left' | 'right'
}

/** Small menu: role=menu, arrow-key navigation, Esc closes and refocuses the trigger. */
export function Menu({ label, trigger, triggerClassName, items, align = 'left' }: MenuProps) {
  const [open, setOpen] = useState(false)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const wrapRef = useRef<HTMLDivElement>(null)
  const itemRefs = useRef<Array<HTMLButtonElement | null>>([])
  const wasOpen = useRef(false)

  useEffect(() => {
    if (!open) return
    wasOpen.current = true
    itemRefs.current[0]?.focus()
    const handleClick = (event: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [open])

  useEffect(() => {
    if (!open && wasOpen.current) triggerRef.current?.focus()
  }, [open])

  const focusItem = (index: number) => {
    const count = items.length
    itemRefs.current[((index % count) + count) % count]?.focus()
  }

  const activeIndex = () => itemRefs.current.findIndex((el) => el === document.activeElement)

  const handleKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Escape') {
      event.preventDefault()
      event.stopPropagation()
      setOpen(false)
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
    }
  }

  return (
    <div className="plan__menu-wrap menu" ref={wrapRef}>
      <button
        ref={triggerRef}
        type="button"
        className={triggerClassName ?? 'plan__menu-trigger'}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        {trigger}
      </button>
      {open && (
        <div
          role="menu"
          aria-label={label}
          className={align === 'right' ? 'plan__menu plan__menu--right' : 'plan__menu'}
          onKeyDown={handleKeyDown}
        >
          {items.map((item, index) => (
            <button
              key={item.label}
              ref={(el) => {
                itemRefs.current[index] = el
              }}
              type="button"
              role="menuitem"
              className="plan__menu-item"
              onClick={() => {
                setOpen(false)
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