import { Menu } from 'lucide-react'

interface TopBarProps {
  onToggleSidebar: () => void
  title?: string
}

export function TopBar({ onToggleSidebar, title }: TopBarProps) {
  return (
    <header className="top-bar">
      <button
        type="button"
        className="top-bar__toggle"
        onClick={onToggleSidebar}
        aria-label="Toggle sidebar"
      >
        <Menu size={20} />
      </button>
      {title && <span className="top-bar__title">{title}</span>}
    </header>
  )
}
