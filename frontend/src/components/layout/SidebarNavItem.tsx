import type { ReactNode } from 'react'

interface SidebarNavItemProps {
  icon: ReactNode
  label: string
  active?: boolean
  onClick?: () => void
  ariaLabel?: string
}

export function SidebarNavItem({ icon, label, active, onClick, ariaLabel }: SidebarNavItemProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={ariaLabel ?? label}
      className="sidebar-nav-item"
      data-active={active}
    >
      <span className="sidebar-nav-item__icon">{icon}</span>
      <span className="sidebar-nav-item__label">{label}</span>
    </button>
  )
}
