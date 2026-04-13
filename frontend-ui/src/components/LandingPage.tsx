import { useState } from 'react';
import { signup, signin, guestLogin, type AuthUser } from '../api';

interface LandingPageProps {
  onAuth: (user: AuthUser) => void;
}

export const LandingPage = ({ onAuth }: LandingPageProps) => {
  const [mode, setMode] = useState<'signin' | 'signup'>('signin');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [guestLoading, setGuestLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const user =
        mode === 'signup'
          ? await signup(email, password, displayName)
          : await signin(email, password);
      onAuth(user);
    } catch (err: any) {
      const msg =
        err?.response?.data?.detail || 'Something went wrong. Please try again.';
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  const handleGuest = async () => {
    setError('');
    setGuestLoading(true);
    try {
      const user = await guestLogin();
      onAuth(user);
    } catch {
      setError('Failed to create guest session.');
    } finally {
      setGuestLoading(false);
    }
  };

  return (
    <div className="landing-root">
      {/* Animated background grid */}
      <div className="landing-grid" />
      <div className="landing-glow landing-glow-1" />
      <div className="landing-glow landing-glow-2" />

      <div className="landing-content">
        {/* Hero section */}
        <div className="landing-hero animate-fade-in-up">
          <div className="landing-shield">
            <span
              className="material-symbols-outlined"
              style={{ fontSize: 48, fontVariationSettings: "'FILL' 1" }}
            >
              shield
            </span>
          </div>
          <h1 className="landing-title">
            Contract<span className="landing-title-accent">Guard</span>
          </h1>
          <p className="landing-subtitle">
            AI-powered contract analysis &amp; risk detection
          </p>
        </div>

        {/* Auth card */}
        <div className="landing-card animate-fade-in-up" style={{ animationDelay: '0.15s' }}>
          {/* Tab toggle */}
          <div className="landing-tabs">
            <button
              className={`landing-tab ${mode === 'signin' ? 'active' : ''}`}
              onClick={() => {
                setMode('signin');
                setError('');
              }}
            >
              Sign In
            </button>
            <button
              className={`landing-tab ${mode === 'signup' ? 'active' : ''}`}
              onClick={() => {
                setMode('signup');
                setError('');
              }}
            >
              Sign Up
            </button>
          </div>

          <form onSubmit={handleSubmit} className="landing-form">
            {mode === 'signup' && (
              <div className="landing-field animate-fade-in-up" style={{ animationDuration: '0.25s' }}>
                <label className="landing-label" htmlFor="auth-name">
                  Display Name
                </label>
                <div className="landing-input-wrap">
                  <span className="material-symbols-outlined landing-input-icon">person</span>
                  <input
                    id="auth-name"
                    type="text"
                    placeholder="Your name (optional)"
                    value={displayName}
                    onChange={(e) => setDisplayName(e.target.value)}
                    className="landing-input"
                    autoComplete="name"
                  />
                </div>
              </div>
            )}

            <div className="landing-field">
              <label className="landing-label" htmlFor="auth-email">
                Email Address
              </label>
              <div className="landing-input-wrap">
                <span className="material-symbols-outlined landing-input-icon">mail</span>
                <input
                  id="auth-email"
                  type="email"
                  placeholder="you@example.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="landing-input"
                  required
                  autoComplete="email"
                />
              </div>
            </div>

            <div className="landing-field">
              <label className="landing-label" htmlFor="auth-password">
                Password
              </label>
              <div className="landing-input-wrap">
                <span className="material-symbols-outlined landing-input-icon">lock</span>
                <input
                  id="auth-password"
                  type="password"
                  placeholder={mode === 'signup' ? 'Min 6 characters' : '••••••••'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="landing-input"
                  required
                  minLength={6}
                  autoComplete={mode === 'signup' ? 'new-password' : 'current-password'}
                />
              </div>
            </div>

            {error && (
              <div className="landing-error animate-fade-in-up" style={{ animationDuration: '0.2s' }}>
                <span className="material-symbols-outlined" style={{ fontSize: 16 }}>error</span>
                {error}
              </div>
            )}

            <button
              type="submit"
              className="landing-btn-primary"
              disabled={loading}
            >
              {loading ? (
                <span className="landing-spinner" />
              ) : mode === 'signin' ? (
                'Sign In'
              ) : (
                'Create Account'
              )}
            </button>
          </form>

          {/* Divider */}
          <div className="landing-divider">
            <span>or</span>
          </div>

          {/* Guest login */}
          <button
            className="landing-btn-guest"
            onClick={handleGuest}
            disabled={guestLoading}
          >
            {guestLoading ? (
              <span className="landing-spinner" />
            ) : (
              <>
                <span className="material-symbols-outlined" style={{ fontSize: 18 }}>
                  visibility_off
                </span>
                Continue as Guest
              </>
            )}
          </button>

          <p className="landing-footer-text">
            {mode === 'signin' ? (
              <>
                Don't have an account?{' '}
                <button className="landing-link" onClick={() => { setMode('signup'); setError(''); }}>
                  Sign up
                </button>
              </>
            ) : (
              <>
                Already have an account?{' '}
                <button className="landing-link" onClick={() => { setMode('signin'); setError(''); }}>
                  Sign in
                </button>
              </>
            )}
          </p>
        </div>

        {/* Bottom tagline */}
        <p className="landing-legal animate-fade-in-up" style={{ animationDelay: '0.3s' }}>
          Powered by Gemini 2.5 Pro · Built for Indian Legal Compliance
        </p>
      </div>
    </div>
  );
};
