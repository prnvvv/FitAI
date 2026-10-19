import type { ReactNode } from 'react'

interface SidebarNavItemProps {
  icon: ReactNode
  label: string
  active?: boolean
  onClick?: () => void
  ariaLabel?: string
  /**
   * Icon-only variant used by the collapsed rail. The label stays as the
   * accessible name; no text node is rendered.
   */
  compact?: boolean
}

export function SidebarNavItem({
  icon,
  label,
  active,
  onClick,
  ariaLabel,
  compact,
}: SidebarNavItemProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={ariaLabel ?? label}
      className={`sidebar-nav-item${compact ? ' sidebar-nav-item--compact' : ''}`}
      data-active={active}
    >
      <span className="sidebar-nav-item__icon">{icon}</span>
      {!compact && <span className="sidebar-nav-item__label">{label}</span>}
    </button>
  )
}
