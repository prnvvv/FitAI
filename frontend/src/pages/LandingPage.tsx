import { ArrowRight, LogIn, Dumbbell, Leaf, BarChart2, Sparkles } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { Navigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import './LandingPage.css'

export function LandingPage() {
  const { user, loading } = useAuth()
  const navigate = useNavigate()

  const handleGetStarted = () => {
    navigate('/login?mode=signup')
  }

  const handleStartJourney = () => {
    navigate('/login?mode=signup')
  }

  const handleLogIn = () => {
    navigate('/login')
  }

  if (loading) {
    return (
      <div className="landing-loading">
        <div className="landing-loading__spinner" />
      </div>
    )
  }

  if (user) {
    return <Navigate to="/" replace />
  }

  return (
    <div className="landing-page">
      {/* Header placeholder for fixed nav */}
      <div className="landing-header-placeholder" aria-hidden="true" />
      {/* Navigation */}
      <header className="landing-nav" role="banner">
        <nav aria-label="Main navigation">
          <div className="landing-nav__brand">
            <span className="landing-nav__logo" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M3 3v18" />
                <path d="M7 3v14" />
                <path d="M11 3v10" />
                <path d="M15 3v6" />
                <path d="M19 3v2" />
              </svg>
            </span>
            <span className="landing-nav__wordmark">FitAI</span>
          </div>
          <div className="landing-nav__actions">
            <button className="landing-nav__login" onClick={handleLogIn} type="button">
              <LogIn size={16} aria-hidden="true" />
              <span>Log in</span>
            </button>
            <button className="landing-nav__cta" onClick={handleGetStarted} type="button">
              <span>Get started</span>
              <ArrowRight size={16} aria-hidden="true" />
            </button>
          </div>
        </nav>
      </header>

      {/* Hero Section */}
      <main className="landing-hero" role="main">
        <div className="landing-hero__content">
          <p className="landing-hero__eyebrow">DISCIPLINE × PROGRESS × LONGEVITY</p>
          <h1 className="landing-hero__heading">
            <span className="landing-hero__heading-line">Train with</span>
            <span className="landing-hero__heading-line landing-hero__heading--gold">intelligence.</span>
          </h1>
          <p className="landing-hero__copy">
            Personalized fitness plans, nutrition guidance<br />
            and progress insights — powered by AI.
          </p>
          <div className="landing-hero__cta-group">
            <button className="landing-hero__cta" onClick={handleStartJourney} type="button">
              <span>Start your journey</span>
              <ArrowRight size={18} aria-hidden="true" />
            </button>
            <div className="landing-hero__scroll-cue" aria-hidden="true">
              <div className="landing-hero__scroll-line">
                <span className="landing-hero__scroll-dot" />
              </div>
              <div className="landing-hero__scroll-label">
                <span>SCROLL</span>
                <span>TO EXPLORE</span>
              </div>
            </div>
          </div>
        </div>
        <div className="landing-hero__visual" aria-hidden="true">
          <img
            src="/images/fitai-roman-pillar.png"
            alt=""
            className="landing-hero__pillar"
          />
          <div className="landing-hero__amber-arc" aria-hidden="true" />
        </div>
      </main>

      {/* Feature Strip */}
      <section className="landing-features" aria-label="Features">
        <div className="landing-features__item">
          <div className="landing-features__icon" aria-hidden="true">
            <Dumbbell size={22} />
          </div>
          <div className="landing-features__text">
            <span>Personalized</span>
            <span>Training Plans</span>
          </div>
        </div>
        <div className="landing-features__divider" aria-hidden="true" />
        <div className="landing-features__item">
          <div className="landing-features__icon" aria-hidden="true">
            <Leaf size={22} />
          </div>
          <div className="landing-features__text">
            <span>Nutrition</span>
            <span>Guidance</span>
          </div>
        </div>
        <div className="landing-features__divider" aria-hidden="true" />
        <div className="landing-features__item">
          <div className="landing-features__icon" aria-hidden="true">
            <BarChart2 size={22} />
          </div>
          <div className="landing-features__text">
            <span>Progress</span>
            <span>Tracking</span>
          </div>
        </div>
        <div className="landing-features__divider" aria-hidden="true" />
        <div className="landing-features__item">
          <div className="landing-features__icon" aria-hidden="true">
            <Sparkles size={22} />
          </div>
          <div className="landing-features__text">
            <span>Adaptive</span>
            <span>Insights</span>
          </div>
        </div>
      </section>
    </div>
  )
}
