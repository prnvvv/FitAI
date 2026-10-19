import { ArrowRight, Dumbbell, Leaf, BarChart3, Sparkle } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { Navigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { useEffect, useState } from 'react'
import '../landing.css'

export function LandingPage() {
  const { user, loading } = useAuth()
  const navigate = useNavigate()
  const [scrolled, setScrolled] = useState(false)

  const handleStartJourney = () => {
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
    <div className="landing">
      {/* Header / Nav */}
      <header className={`nav ${scrolled ? 'is-scrolled' : ''}`} role="banner">
        <div className="nav__inner">
          {/* Logo: waveform + wordmark */}
          <div className="nav__logo" aria-label="FitAI home">
            <div className="nav__waveform" aria-hidden="true">
              <div className="nav__bar" />
              <div className="nav__bar" />
              <div className="nav__bar" />
              <div className="nav__bar" />
              <div className="nav__bar" />
            </div>
            <span className="nav__wordmark">FitAI</span>
          </div>

          {/* Centered Links */}
          <nav className="nav__links" aria-label="Main navigation">
            <a className="nav__link" href="#product">Product</a>
            <a className="nav__link" href="#how-it-works">How it works</a>
            <a className="nav__link" href="#science">Science</a>
            <a className="nav__link" href="#pricing">Pricing</a>
          </nav>

          {/* Right Actions */}
          <div className="nav__actions">
            <button className="nav__login" onClick={handleLogIn} type="button">
              Log in
            </button>
            <a className="nav__cta" href="/login?mode=signup">
              <span>Get started</span>
              <ArrowRight size={18} aria-hidden="true" />
            </a>
          </div>
        </div>
      </header>

      {/* Hero */}
      <section className="hero" aria-labelledby="hero-heading">
        {/* Media layer: image + overlays + arc */}
        <div className="hero__media" aria-hidden="true">
          <div className="hero__img-wrapper">
            <img
              src="/images/fitai-roman-pillar.png"
              alt=""
              className="hero__img"
            />
          </div>
          <div className="hero__overlay hero__overlay--left" />
          <div className="hero__overlay hero__overlay--top" />
          <div className="hero__overlay hero__overlay--bottom" />
          <div className="hero__arc" />
        </div>

        {/* Content */}
        <div className="hero__content">
          <p className="hero__eyebrow">
            DISCIPLINE <span className="hero__cross" aria-hidden="true">&times;</span> PROGRESS <span className="hero__cross" aria-hidden="true">&times;</span> LONGEVITY
          </p>
          <h1 id="hero-heading" className="hero__heading">
            <span className="hero__heading-line">Train with</span>
            <span className="hero__heading-line hero__heading-line--gold">intelligence.</span>
          </h1>
          <p className="hero__copy">
            Personalized fitness plans, nutrition guidance and progress insights — powered by AI.
          </p>
          <div className="hero__cta">
            <button className="hero__btn" onClick={handleStartJourney} type="button">
              <span>Start your journey</span>
              <ArrowRight size={20} aria-hidden="true" />
            </button>
            <div className="hero__divider" aria-hidden="true" />
          </div>
        </div>
      </section>

      {/* Feature Strip */}
      <section className="features" aria-label="Features">
        <div className="feature">
          <div className="feature__icon" aria-hidden="true">
            <Dumbbell size={40} strokeWidth={1.25} />
          </div>
          <div className="feature__text">
            <span className="feature__title">Personalized</span>
            <span className="feature__subtitle">Training Plans</span>
          </div>
        </div>
        <div className="feature">
          <div className="feature__icon" aria-hidden="true">
            <Leaf size={40} strokeWidth={1.25} />
          </div>
          <div className="feature__text">
            <span className="feature__title">Nutrition</span>
            <span className="feature__subtitle">Guidance</span>
          </div>
        </div>
        <div className="feature">
          <div className="feature__icon" aria-hidden="true">
            <BarChart3 size={40} strokeWidth={1.25} />
          </div>
          <div className="feature__text">
            <span className="feature__title">Progress</span>
            <span className="feature__subtitle">Tracking</span>
          </div>
        </div>
        <div className="feature">
          <div className="feature__icon" aria-hidden="true">
            <Sparkle size={40} strokeWidth={1.25} />
          </div>
          <div className="feature__text">
            <span className="feature__title">Adaptive</span>
            <span className="feature__subtitle">Insights</span>
          </div>
        </div>
      </section>
    </div>
  )
}