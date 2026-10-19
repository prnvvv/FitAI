import { ArrowRight, Dumbbell, Leaf, BarChart3, Sparkle } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { Navigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import '../landing.css'

export function LandingPage() {
  const { user, loading } = useAuth()
  const navigate = useNavigate()

  const handleStartJourney = () => {
    navigate('/login?mode=signup')
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
    <div className="landing">
      {/* Hero — transparent, content only */}
      <section className="hero" aria-labelledby="hero-heading">
        {/* Content */}
        <div className="hero__content landing-fade-in">
          <p className="hero__eyebrow">
            DISCIPLINE <span className="hero__cross" aria-hidden="true">&times;</span> PROGRESS <span className="hero__cross" aria-hidden="true">&times;</span> LONGEVITY
          </p>
          <h1 id="hero-heading" className="hero__heading">
            <span className="hero__heading-line">Train with</span>
            <span className="hero__heading-line hero__heading-line--gold">Intelligence.</span>
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
      <section className="features landing-fade-in-delayed" aria-label="Features">
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