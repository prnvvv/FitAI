import { Brain, LogOut, User } from 'lucide-react'
import { useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext'

interface AccountMenuProps {
  open: boolean
  onClose: () => void
}

export function AccountMenu({ open, onClose }: AccountMenuProps) {
  const { user, signOut } = useAuth()
  const navigate = useNavigate()
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    const handleClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose()
    }
    document.addEventListener('keydown', handleKey)
    document.addEventListener('mousedown', handleClick)
    return () => {
      document.removeEventListener('keydown', handleKey)
      document.removeEventListener('mousedown', handleClick)
    }
  }, [open, onClose])

  if (!open || !user) return null

  const initials = (user.displayName ?? user.email ?? 'U').slice(0, 2).toUpperCase()

  const handleLogout = async () => {
    await signOut()
    onClose()
    navigate('/login')
  }

  return (
    <div ref={ref} className="account-menu" role="menu">
      <div className="account-menu__header" role="menuitem">
        <div className="account-menu__avatar">{initials}</div>
        <div className="account-menu__info">
          <div className="account-menu__name">{user.displayName ?? 'User'}</div>
          <div className="account-menu__email">{user.email}</div>
        </div>
      </div>
      <div className="account-menu__divider" />
      <button
        type="button"
        className="account-menu__item"
        role="menuitem"
        onClick={() => {
          onClose()
          navigate('/chat/profile')
        }}
      >
        <User size={20} />
        <span>Profile</span>
      </button>
      <button
        type="button"
        className="account-menu__item"
        role="menuitem"
        onClick={() => {
          onClose()
          navigate('/chat/memory')
        }}
      >
        <Brain size={20} />
        <span>Memory</span>
      </button>
      <div className="account-menu__divider" />
      <button
        type="button"
        className="account-menu__item account-menu__item--danger"
        role="menuitem"
        onClick={handleLogout}
      >
        <LogOut size={20} />
        <span>Log out</span>
      </button>
    </div>
  )
}