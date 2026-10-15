import { ArrowLeft, Dumbbell, Eye, EyeOff, Loader2 } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Link, Navigate } from 'react-router-dom'
import { ThemeToggle } from '../components/layout/ThemeToggle'
import { useAuth } from '../context/AuthContext'

export function LoginPage() {
  const { user, loading, signIn, signUp } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [isSignUp, setIsSignUp] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (loading) {
    return (
      <div className="login-page login-page--loading">
        <Loader2 className="login-page__spinner" size={32} />
      </div>
    )
  }

  if (user) {
    return <Navigate to="/" replace />
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      if (isSignUp) {
        await signUp(email, password)
        setError('Check your email to confirm your account.')
      } else {
        await signIn(email, password)
      }
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="login-page checker-bg">
      <aside className="login-page__aside">
        <Link to="/welcome" className="login-page__brand-lg">
          <span className="login-page__brand-mark" aria-hidden="true">
            <Dumbbell size={18} />
          </span>
          FitAI
        </Link>
        <h2 className="login-page__aside-title">Plan. Track. Improve.</h2>
        <p className="login-page__aside-copy">
          Your personal fitness assistant that remembers your goals, tracks your progress and
          answers with real numbers.
        </p>
        <ul className="login-page__points">
          <li>Personalised workout planning</li>
          <li>Progress tracking that stays yours</li>
          <li>Answers grounded in your own data</li>
        </ul>
      </aside>

      <div className="login-page__panel">
        <div className="login-page__panel-top">
          <Link to="/welcome" className="login-page__back">
            <ArrowLeft size={15} />
            Back to home
          </Link>
          <ThemeToggle />
        </div>

        <div className="login-page__card">
          <div className="login-page__brand">
            <span className="login-page__logo" aria-hidden="true">
              <Dumbbell size={18} />
            </span>
            <span className="login-page__brand-name">FitAI</span>
          </div>
          <h1 className="login-page__heading">{isSignUp ? 'Create your account' : 'Welcome back'}</h1>
          <p className="login-page__sub">
            {isSignUp
              ? 'Start your fitness journey with FitAI.'
              : 'Sign in to continue your fitness journey.'}
          </p>

          <form onSubmit={handleSubmit} className="login-page__form">
            <label className="login-page__field">
              <span>Email</span>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                required
                autoFocus
              />
            </label>

            <label className="login-page__field">
              <span>Password</span>
              <div className="login-page__password">
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  required
                  minLength={8}
                />
                <button
                  type="button"
                  className="login-page__toggle-password"
                  onClick={() => setShowPassword((v) => !v)}
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                >
                  {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>
            </label>

            {error && <div className="login-page__error">{error}</div>}

            <button
              type="submit"
              className="login-page__submit"
              disabled={submitting || !email || !password}
            >
              {submitting ? (
                <Loader2 className="login-page__spinner" size={18} />
              ) : isSignUp ? (
                'Create account'
              ) : (
                'Sign in'
              )}
            </button>
          </form>

          <div className="login-page__toggle">
            {isSignUp ? 'Already have an account?' : "Don't have an account?"}{' '}
            <button type="button" onClick={() => setIsSignUp((v) => !v)}>
              {isSignUp ? 'Sign in' : 'Sign up'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
