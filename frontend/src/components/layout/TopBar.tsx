import { Menu } from 'lucide-react'
import { forwardRef } from 'react'

interface TopBarProps {
  onToggleSidebar: () => void
  title?: string
}

export const TopBar = forwardRef<HTMLButtonElement, TopBarProps>(
  function TopBar({ onToggleSidebar, title }, ref) {
    return (
      <header className="top-bar">
        <button
          ref={ref}
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
  },
)
