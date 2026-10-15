import { ArrowRight, Dumbbell, Menu } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ThemeToggle } from '../components/layout/ThemeToggle'

const NAV_LINKS = [
  { label: 'Features', href: '#features' },
  { label: 'How it works', href: '#how' },
  { label: 'About', href: '#about' },
]

/**
 * Public marketing landing page shown before sign-in. Uses the shared design
 * tokens so it themes with the rest of the app.
 */
export function LandingPage() {
  const [menuOpen, setMenuOpen] = useState(false)

  return (
    <div className="landing checker-bg">
      <header className="landing__nav">
        <Link to="/welcome" className="landing__brand">
          <span className="landing__brand-mark" aria-hidden="true">
            <Dumbbell size={18} />
          </span>
          FitAI
        </Link>

        <nav className="landing__links" aria-label="Primary">
          {NAV_LINKS.map((link) => (
            <a key={link.label} href={link.href}>
              {link.label}
            </a>
          ))}
        </nav>

        <div className="landing__nav-actions">
          <ThemeToggle />
          <Link to="/login" className="landing__signin">
            Sign in
          </Link>
          <button
            type="button"
            className="landing__menu-btn"
            aria-label={menuOpen ? 'Close menu' : 'Open menu'}
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen((v) => !v)}
          >
            <Menu size={20} />
          </button>
        </div>
      </header>

      {menuOpen && (
        <nav className="landing__mobile-nav" aria-label="Primary mobile">
          {NAV_LINKS.map((link) => (
            <a key={link.label} href={link.href} onClick={() => setMenuOpen(false)}>
              {link.label}
            </a>
          ))}
          <Link to="/login" onClick={() => setMenuOpen(false)}>
            Sign in
          </Link>
        </nav>
      )}

      <main className="landing__hero">
        <div className="landing__copy">
          <h1 className="landing__title">
            Your <span className="landing__accent">Fitness</span> Assistant
          </h1>
          <p className="landing__lead">Plan. Track. Improve. All in one place.</p>
          <Link to="/login" className="landing__cta">
            Get started
            <ArrowRight size={16} />
          </Link>
        </div>

        <div className="landing__art-wrap">
          <svg
            className="landing__art"
            viewBox="0 0 520 360"
            role="img"
            aria-label="Illustration of a dumbbell"
          >
            <defs>
              <linearGradient id="landingCurve" x1="0" y1="1" x2="1" y2="0">
                <stop offset="0" stopColor="var(--accent)" stopOpacity="0" />
                <stop offset="0.5" stopColor="var(--accent)" stopOpacity="0.9" />
                <stop offset="1" stopColor="var(--accent)" stopOpacity="0.15" />
              </linearGradient>
              <linearGradient id="landingPlate" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0" stopColor="#3a4a72" />
                <stop offset="0.5" stopColor="#182036" />
                <stop offset="1" stopColor="#080b14" />
              </linearGradient>
              <linearGradient id="landingBar" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0" stopColor="#c7d3ea" />
                <stop offset="0.5" stopColor="#7f8da8" />
                <stop offset="1" stopColor="#39425a" />
              </linearGradient>
            </defs>

            <path
              d="M10 320 C 120 170, 210 240, 320 120 S 470 40, 516 70"
              fill="none"
              stroke="url(#landingCurve)"
              strokeWidth="3"
              strokeLinecap="round"
            />

            <g transform="rotate(-18 260 180)">
              <rect x="70" y="150" width="26" height="66" rx="10" fill="url(#landingPlate)" />
              <rect x="102" y="134" width="30" height="98" rx="12" fill="url(#landingPlate)" />
              <rect x="388" y="150" width="26" height="66" rx="10" fill="url(#landingPlate)" />
              <rect x="356" y="134" width="30" height="98" rx="12" fill="url(#landingPlate)" />
              <rect x="132" y="170" width="226" height="26" rx="13" fill="url(#landingBar)" />
              <rect x="132" y="170" width="226" height="9" rx="6" fill="#ffffff" opacity="0.28" />
            </g>
          </svg>
          <span className="landing__handwritten">Small Steps Stronger You</span>
        </div>
      </main>

      <footer className="landing__footer" id="about">
        <p>Plan. Track. Improve. All in one place.</p>
      </footer>
    </div>
  )
}
