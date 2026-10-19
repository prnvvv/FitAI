import { ArrowRight, Eye, EyeOff, Loader2, Lock, Mail } from 'lucide-react'
import { useState, type FormEvent, type MouseEvent } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import '../login.css'

// Google "G" logo inline SVG
const GoogleIcon = () => (
  <svg
    viewBox="0 0 24 24"
    width="20"
    height="20"
    aria-hidden="true"
    className="login-page__google-icon"
  >
    <path
      fill="#4285F4"
      d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
    />
    <path
      fill="#34A853"
      d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
    />
    <path
      fill="#FBBC05"
      d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
    />
    <path
      fill="#EA4335"
      d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
    />
  </svg>
)

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

          {/* Divider — OR */}
          <div className="login-page__divider" role="separator" aria-label="or">
            <div className="login-page__divider-line" aria-hidden="true" />
            <span className="login-page__divider-text">OR</span>
            <div className="login-page__divider-line" aria-hidden="true" />
          </div>

          {/* Google Button */}
          <button
            type="button"
            className="login-page__google"
            onClick={() => { /* Google OAuth handler would go here */ }}
            disabled={submitting}
          >
            <GoogleIcon />
            <span>Continue with Google</span>
          </button>

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