import { ArrowRight, Eye, EyeOff, Loader2, Lock, Mail } from 'lucide-react'
import { useState, type FormEvent, type MouseEvent } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import '../login.css'

export function LoginPage() {
  const { user, loading, signIn } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (loading) {
    return (
      <div className="login-page login-page--loading">
        <div className="login-page__spinner" />
      </div>
    )
  }

  if (user) {
    return <Navigate to="/" replace />
  }

  // Client-side navigation for in-page links: a plain href would reload the
  // whole document and skip the route transition.
  const handleNavTo = (event: MouseEvent<HTMLAnchorElement>, to: string) => {
    if (event.defaultPrevented || event.button !== 0) return
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return

    event.preventDefault()
    navigate(to)
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await signIn(email, password)
      navigate('/')
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="login-page">
      {/* Card — centered */}
      <div className="login-page__card login-fade-in">
        <div className="login-page__inner">
          {/* Eyebrow */}
          <p className="login-page__eyebrow">
            DISCIPLINE <span className="cross" aria-hidden="true">&times;</span> PROGRESS <span className="cross" aria-hidden="true">&times;</span> LONGEVITY
          </p>

          {/* Heading — "Welcome back." with gradient on "back." */}
          <h1 className="login-page__heading">
            Welcome <span className="back">back.</span>
          </h1>

          {/* Subtitle */}
          <p className="login-page__subtitle">
            Continue your fitness journey with AI.
          </p>

          {/* Form */}
          <form onSubmit={handleSubmit} className="login-page__form" noValidate>
            {/* Email */}
            <div className="login-page__field">
              <label htmlFor="email" className="login-page__label">Email</label>
              <div className="login-page__input-wrapper">
                <Mail className="login-page__input-icon" aria-hidden="true" />
                <input
                  id="email"
                  type="email"
                  className="login-page__input"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                  required
                  autoComplete="email"
                  autoFocus
                  disabled={submitting}
                />
              </div>
            </div>

            {/* Password */}
            <div className="login-page__field">
              <label htmlFor="password" className="login-page__label">Password</label>
              <div className="login-page__input-wrapper">
                <Lock className="login-page__input-icon" aria-hidden="true" />
                <input
                  id="password"
                  type={showPassword ? 'text' : 'password'}
                  className="login-page__input login-page__input--password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Your password"
                  required
                  minLength={8}
                  autoComplete="current-password"
                  disabled={submitting}
                />
                <button
                  type="button"
                  className="login-page__toggle-password"
                  onClick={() => setShowPassword((v) => !v)}
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                  disabled={submitting}
                >
                  {showPassword ? <EyeOff size={20} /> : <Eye size={20} />}
                </button>
              </div>
            </div>

            {/* Error */}
            {error && <div className="login-page__error" role="alert">{error}</div>}

            {/* Forgot Password */}
            <a
              href="/forgot-password"
              className="login-page__forgot"
              onClick={(event) => handleNavTo(event, '/forgot-password')}
            >
              Forgot password?
            </a>

            {/* Submit Button */}
            <button
              type="submit"
              className="login-page__submit"
              disabled={submitting || !email || !password}
            >
              {submitting ? (
                <Loader2 className="login-page__spinner" size={18} aria-hidden="true" />
              ) : (
                <>
                  <span>Log in</span>
                  <ArrowRight size={16} aria-hidden="true" />
                </>
              )}
            </button>
          </form>

          {/* Footer — Sign up link */}
          <p className="login-page__footer">
            Don&apos;t have an account?{' '}
            <a
              href="/login?mode=signup"
              className="login-page__signup-link"
              onClick={(event) => handleNavTo(event, '/login?mode=signup')}
            >
              Sign up
            </a>
          </p>
        </div>
      </div>
    </div>
  )
}