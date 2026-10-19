import { Bell, ChevronDown } from 'lucide-react'
import { useState } from 'react'
import { useDisplayName } from '../../hooks/useDisplayName'
import { AccountMenu } from './AccountMenu'

interface TopBarProps {
  /** Active conversation title, if one is open. */
  title?: string | null
}

export function TopBar({ title }: TopBarProps) {
  const [accountOpen, setAccountOpen] = useState(false)
  const { firstName, initials } = useDisplayName()

  return (
    <header className="top-bar">
      {title && <h1 className="top-bar__title">{title}</h1>}

      <div className="top-bar__actions">
        {/* No notification feed exists yet: the control stays visible but inert
            instead of opening a menu that would show invented content. */}
        <button
          type="button"
          className="top-bar__icon-btn"
          aria-label="Notifications"
          title="Notifications are not available yet"
          disabled
        >
          <Bell size={18} aria-hidden="true" />
        </button>

        <div className="top-bar__account-wrap">
          <button
            type="button"
            className="top-bar__account"
            onClick={() => setAccountOpen((v) => !v)}
            aria-expanded={accountOpen}
            aria-haspopup="menu"
            aria-label="Account menu"
          >
            <span className="top-bar__avatar" aria-hidden="true">
              {initials}
            </span>
            <span className="top-bar__name">{firstName}</span>
            <ChevronDown size={16} className="top-bar__chevron" aria-hidden="true" />
          </button>
          <AccountMenu open={accountOpen} onClose={() => setAccountOpen(false)} />
        </div>
      </div>
    </header>
  )
}
