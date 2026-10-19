import { useLocation } from 'react-router-dom'
import { ArrowRight, LogIn } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useEffect, useState } from 'react'
import './PersistentHeader.css'

export function PersistentHeader() {
  const location = useLocation()
  const navigate = useNavigate()
  const [scrolled, setScrolled] = useState(false)

  const isLanding = location.pathname === '/'
  const isAuth = location.pathname.startsWith('/login')

  const handleGetStarted = () => {
    navigate('/login?mode=signup')
  }

  const handleLogIn = () => {
    navigate('/login')
  }

  useEffect(() => {
    const onScroll = () => {
      setScrolled(window.scrollY > 24)
    }
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  return (
    <header className={`persistent-header ${isLanding ? 'is-landing' : ''} ${isAuth ? 'is-auth' : ''} ${scrolled ? 'is-scrolled' : ''}`} role="banner">
      <div className="persistent-header__inner">
        {/* Logo: waveform + wordmark — persists, wordmark transitions */}
        <div className="persistent-header__logo" aria-label="FitAI home">
          <div className="persistent-header__waveform" aria-hidden="true">
            <div className="persistent-header__bar" />
            <div className="persistent-header__bar" />
            <div className="persistent-header__bar" />
            <div className="persistent-header__bar" />
            <div className="persistent-header__bar" />
          </div>
          <span className="persistent-header__wordmark">FitAI</span>
        </div>

        {/* Right Actions — only on landing */}
        <div className="persistent-header__actions">
          {isLanding && (
            <>
              <button className="persistent-header__login" onClick={handleLogIn} type="button">
                <LogIn size={16} aria-hidden="true" />
                <span>Log in</span>
              </button>
              <a className="persistent-header__cta" href="/login?mode=signup" onClick={handleGetStarted}>
                <span>Get started</span>
                <ArrowRight size={18} aria-hidden="true" />
              </a>
            </>
          )}
        </div>
      </div>
    </header>
  )
}