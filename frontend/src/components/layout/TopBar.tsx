import { Bell, ChevronDown } from 'lucide-react'
import { useState } from 'react'
import { useDisplayName } from '../../hooks/useDisplayName'
import { AccountMenu } from './AccountMenu'

interface TopBarProps {
  /** Conversation title on chat routes, destination label elsewhere. */
  title: string
  /**
   * Renders the title as the page heading. False when the page already renders
   * its own `<h1>`, so no route ends up with two competing headings.
   */
  asHeading?: boolean
}

export function TopBar({ title, asHeading = false }: TopBarProps) {
  const [accountOpen, setAccountOpen] = useState(false)
  const { firstName, initials } = useDisplayName()

  return (
    <header className="top-bar">
      {asHeading ? (
        <h1 className="top-bar__title">{title}</h1>
      ) : (
        <span className="top-bar__title">{title}</span>
      )}

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
