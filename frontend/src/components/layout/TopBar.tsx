import { Menu, PanelLeftOpen } from 'lucide-react'
import { forwardRef } from 'react'

interface TopBarProps {
  sidebarOpen: boolean
  onToggleSidebar: () => void
  title?: string
}

export const TopBar = forwardRef<HTMLButtonElement, TopBarProps>(
  function TopBar({ sidebarOpen, onToggleSidebar, title }, ref) {
    return (
      <header className="top-bar">
        <button
          ref={ref}
          type="button"
          className={`top-bar__toggle ${sidebarOpen ? 'top-bar__toggle--hidden-desktop' : ''}`}
          onClick={onToggleSidebar}
          aria-label={sidebarOpen ? 'Collapse sidebar' : 'Open sidebar'}
        >
          {sidebarOpen ? <PanelLeftOpen size={20} /> : <Menu size={20} />}
        </button>
        {title && <span className="top-bar__title">{title}</span>}
      </header>
    )
  },
)
