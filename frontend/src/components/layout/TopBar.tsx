import { PanelLeftClose, PanelRightOpen } from 'lucide-react'
import { ThemeToggle } from './ThemeToggle'

interface TopBarProps {
  onToggleSidebar: () => void
  sidebarOpen: boolean
  title?: string
}

export function TopBar({ onToggleSidebar, sidebarOpen, title }: TopBarProps) {
  return (
    <header className="top-bar">
      <button
        type="button"
        className="top-bar__sidebar-toggle"
        onClick={onToggleSidebar}
        aria-label={sidebarOpen ? 'Close sidebar' : 'Open sidebar'}
        aria-expanded={sidebarOpen}
        aria-controls="app-sidebar"
      >
        {sidebarOpen ? <PanelLeftClose size={20} /> : <PanelRightOpen size={20} />}
      </button>
      {title && <span className="top-bar__title">{title}</span>}
      <div className="top-bar__actions">
        <ThemeToggle ariaLabel="Toggle theme" />
      </div>
    </header>
  )
}