import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { ThemeToggle } from '../components/layout/ThemeToggle';
import { Dumbbell, ArrowRight, BarChart2, BookOpen, Brain, Sparkles } from 'lucide-react';

export function LandingPage() {
  const { user, loading: authLoading } = useAuth();
  const navigate = useNavigate();

  if (authLoading) {
    return (
      <div className="landing-page loading">
        <div className="landing-page__spinner" />
      </div>
    );
  }

  if (user) {
    // If already authenticated, redirect to chat
    navigate('/chat', { replace: true });
    return null;
  }

  return (
    <div className="landing-page">
      <header className="landing-page__header">
        <div className="landing-page__nav">
          <Link to="/" className="landing-page__logo" aria-label="FitAI home">
            <Dumbbell size={24} />
            <span>FitAI</span>
          </Link>
          <nav className="landing-page__links" aria-label="Landing navigation">
            <Link to="#features" className="landing-page__link">Features</Link>
            <Link to="/login" className="landing-page__link">Sign in</Link>
          </nav>
          <ThemeToggle ariaLabel="Toggle theme" className="landing-page__theme-toggle" />
        </div>
      </header>

      <main className="landing-page__main">
        <section className="landing-page__hero" aria-labelledby="hero-title">
          <div className="landing-page__hero-content">
            <div className="landing-page__badge">Your AI Fitness Assistant</div>
            <h1 id="hero-title" className="landing-page__title">
              Your Fitness Assistant
            </h1>
            <p className="landing-page__tagline">
              Plan. Track. Improve. All in one place.
            </p>
            <p className="landing-page__description">
              FitAI combines personalized workout planning, progress tracking, conversational AI guidance,
              and a private knowledge library — so you can train smarter, not harder.
            </p>
            <div className="landing-page__actions">
              <Link to="/login" className="landing-page__btn landing-page__btn--primary">
                <span>Get started</span>
                <ArrowRight size={18} aria-hidden="true" />
              </Link>
              <Link to="/login" className="landing-page__btn landing-page__btn--secondary">
                Sign in
              </Link>
            </div>
            <p className="landing-page__trust">
              Private by default. Your data never trains AI models.
            </p>
          </div>
          <div className="landing-page__hero-visual" aria-hidden="true">
            <div className="landing-page__visual-card">
              <div className="landing-page__visual-header">
                <span className="landing-page__visual-title">Weekly Progress</span>
                <span className="landing-page__visual-date">This week</span>
              </div>
              <div className="landing-page__visual-chart" role="img" aria-label="Sample weight trend chart showing gradual progress over a week">
                <svg viewBox="0 0 300 160" preserveAspectRatio="none">
                  <defs>
                    <linearGradient id="landing-gradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.25" />
                      <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
                    </linearGradient>
                  </defs>
                  <path
                    d="M20,120 C60,110 100,90 140,85 C180,80 220,95 260,90"
                    stroke="var(--accent)"
                    strokeWidth="2.5"
                    fill="none"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                  <path
                    d="M20,120 C60,110 100,90 140,85 C180,80 220,95 260,90 V140 H20 Z"
                    fill="url(#landing-gradient)"
                  />
                  <g stroke="var(--divider)" strokeWidth="0.5">
                    <line x1="20" y1="40" x2="280" y2="40" />
                    <line x1="20" y1="70" x2="280" y2="70" />
                    <line x1="20" y1="100" x2="280" y2="100" />
                    <line x1="20" y1="130" x2="280" y2="130" />
                  </g>
                  <g fill="var(--accent)">
                    <circle cx="20" cy="120" r="4" />
                    <circle cx="60" cy="110" r="4" />
                    <circle cx="100" cy="90" r="4" />
                    <circle cx="140" cy="85" r="4" />
                    <circle cx="180" cy="80" r="4" />
                    <circle cx="220" cy="95" r="4" />
                    <circle cx="260" cy="90" r="4" />
                  </g>
                </svg>
              </div>
              <div className="landing-page__visual-stats">
                <div className="landing-page__visual-stat">
                  <span className="landing-page__visual-value">−2.3 kg</span>
                  <span className="landing-page__visual-label">Weight change</span>
                </div>
                <div className="landing-page__visual-stat">
                  <span className="landing-page__visual-value">5</span>
                  <span className="landing-page__visual-label">Sessions</span>
                </div>
                <div className="landing-page__visual-stat">
                  <span className="landing-page__visual-value">12</span>
                  <span className="landing-page__visual-label">Active days</span>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section id="features" className="landing-page__features" aria-labelledby="features-title">
          <h2 id="features-title" className="landing-page__section-title">
            Everything you need to progress
          </h2>
          <div className="landing-page__features-grid">
            <article className="landing-page__feature">
              <div className="landing-page__feature-icon">
                <Sparkles size={24} />
              </div>
              <h3 className="landing-page__feature-title">AI Guidance</h3>
              <p className="landing-page__feature-desc">
                Ask fitness questions, get personalized workout suggestions, and receive nutrition guidance
                grounded in your profile and history.
              </p>
            </article>
            <article className="landing-page__feature">
              <div className="landing-page__feature-icon">
                <BarChart2 size={24} />
              </div>
              <h3 className="landing-page__feature-title">Progress Analytics</h3>
              <p className="landing-page__feature-desc">
                Track weight, body composition, BMI, and training volume with beautiful charts.
                See trends, streaks, and personal records at a glance.
              </p>
            </article>
            <article className="landing-page__feature">
              <div className="landing-page__feature-icon">
                <BookOpen size={24} />
              </div>
              <h3 className="landing-page__feature-title">Knowledge Library</h3>
              <p className="landing-page__feature-desc">
                Upload PDFs, notes, and articles. FitAI retrieves relevant sections when you ask questions,
                so answers are grounded in your sources.
              </p>
            </article>
            <article className="landing-page__feature">
              <div className="landing-page__feature-icon">
                <Brain size={24} />
              </div>
              <h3 className="landing-page__feature-title">Persistent Memory</h3>
              <p className="landing-page__feature-desc">
                FitAI remembers your goals, preferences, and measurements across conversations.
                You stay in control — review, edit, or delete any memory at any time.
              </p>
            </article>
          </div>
        </section>

        <section className="landing-page__cta" aria-labelledby="cta-title">
          <h2 id="cta-title" className="landing-page__cta-title">Ready to train smarter?</h2>
          <p className="landing-page__cta-desc">Create your free account and start your first workout plan today.</p>
          <Link to="/login" className="landing-page__btn landing-page__btn--primary landing-page__btn--large">
            <span>Get started free</span>
            <ArrowRight size={18} aria-hidden="true" />
          </Link>
        </section>
      </main>

      <footer className="landing-page__footer">
        <p className="landing-page__copyright">FitAI — Your personal fitness assistant</p>
        <nav className="landing-page__footer-links" aria-label="Footer links">
          <Link to="/login" className="landing-page__footer-link">Sign in</Link>
          <span className="landing-page__footer-separator" aria-hidden="true">·</span>
          <Link to="/login" className="landing-page__footer-link">Create account</Link>
        </nav>
      </footer>
    </div>
  );
}