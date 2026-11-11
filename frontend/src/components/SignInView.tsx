import React, { useState, useEffect } from 'react';
import {
  Scale,
  ShieldCheck,
  Lock,
  ArrowRight,
  UserCheck,
  CheckCircle2,
  AlertCircle,
  KeyRound,
} from 'lucide-react';
import type { AuthenticatedMerchant, DemoMerchantProfile } from '../types';

interface SignInViewProps {
  onSignInSuccess: (merchant: AuthenticatedMerchant) => void;
}

export const SignInView: React.FC<SignInViewProps> = ({ onSignInSuccess }) => {
  const [profiles, setProfiles] = useState<DemoMerchantProfile[]>([]);
  const [selectedProfileId, setSelectedProfileId] = useState<string>('merchant_ops_primary');
  const [authMode, setAuthMode] = useState<'demo' | 'credentials'>('demo');
  
  // Credentials form state
  const [email, setEmail] = useState<string>('ops@merchant.example.com');
  const [password, setPassword] = useState<string>('docket2026');
  
  // Interaction & status state
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch available profiles on mount
  useEffect(() => {
    const fetchProfiles = async () => {
      try {
        const res = await fetch('/api/auth/profiles');
        if (res.ok) {
          const data: DemoMerchantProfile[] = await res.json();
          setProfiles(data);
          if (data.length > 0 && !selectedProfileId) {
            setSelectedProfileId(data[0].merchant_user_id);
          }
        }
      } catch (err) {
        console.error('Failed to load auth profiles:', err);
      }
    };
    fetchProfiles();
  }, []);

  const handleDemoAccess = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch('/api/auth/demo-session', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ profile_id: selectedProfileId }),
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `Session issuance failed (${res.status})`);
      }

      const data = await res.json();
      onSignInSuccess(data.merchant);
    } catch (err: any) {
      console.error('Demo authentication error:', err);
      setError(err.message || 'Failed to initialize demo workspace session.');
    } finally {
      setLoading(false);
    }
  };

  const handleCredentialLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.trim() || !password.trim()) {
      setError('Please provide both merchant email and password.');
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email.trim(), password }),
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `Sign in failed (${res.status})`);
      }

      const data = await res.json();
      onSignInSuccess(data.merchant);
    } catch (err: any) {
      console.error('Credential login error:', err);
      setError(err.message || 'Invalid merchant credentials. Please check your inputs.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="signin-container">
      <div className="signin-card">
        {/* Top Sandbox Status Indicator */}
        <div className="signin-env-badge">
          <span className="signin-pulse-dot" />
          <span style={{ fontWeight: 600 }}>PayPal Sandbox (REST v1)</span>
          <span style={{ color: 'var(--text-tertiary)', margin: '0 4px' }}>·</span>
          <span>Read-Only Autonomous Mode</span>
        </div>

        {/* Brand & Product Header */}
        <div className="signin-header">
          <div className="signin-brand-icon">
            <Scale size={24} strokeWidth={2.2} />
          </div>
          <h1 className="signin-title">DOCKET</h1>
          <p className="signin-descriptor">
            Autonomous Dispute Operations & PayPal Seller Protection Enforcement
          </p>
          <p className="signin-subtext">
            Enterprise evidence reconciliation, deterministic invariant barriers, and controlled HMAC authorization.
          </p>
        </div>

        {/* Auth Mode Toggle */}
        <div className="signin-tabs">
          <button
            type="button"
            className={`signin-tab ${authMode === 'demo' ? 'active' : ''}`}
            onClick={() => {
              setAuthMode('demo');
              setError(null);
            }}
          >
            <UserCheck size={14} />
            <span>Judge & Evaluator Access</span>
          </button>
          <button
            type="button"
            className={`signin-tab ${authMode === 'credentials' ? 'active' : ''}`}
            onClick={() => {
              setAuthMode('credentials');
              setError(null);
            }}
          >
            <KeyRound size={14} />
            <span>Operator Sign In</span>
          </button>
        </div>

        {/* Error Notification Banner */}
        {error && (
          <div className="signin-error-banner">
            <AlertCircle size={15} style={{ flexShrink: 0, marginTop: '1px' }} />
            <div style={{ flex: 1, fontSize: '12px', lineHeight: 1.4 }}>
              <strong>Authentication Error:</strong> {error}
            </div>
          </div>
        )}

        {/* Tab 1: 1-Click Demo Persona Access */}
        {authMode === 'demo' && (
          <div className="signin-demo-section">
            <div className="signin-persona-intro">
              Select an authenticated merchant persona to immediately launch the Docket Command Desk with live evidence reconciliation:
            </div>

            <div className="signin-persona-list">
              {profiles.map((p) => {
                const isSelected = selectedProfileId === p.merchant_user_id || selectedProfileId === p.profile_id;
                return (
                  <div
                    key={p.merchant_user_id}
                    className={`signin-persona-card ${isSelected ? 'selected' : ''}`}
                    onClick={() => setSelectedProfileId(p.merchant_user_id)}
                  >
                    <div className="signin-persona-radio">
                      <div className={`radio-dot ${isSelected ? 'active' : ''}`} />
                    </div>
                    <div className="signin-persona-info">
                      <div className="signin-persona-header">
                        <span className="signin-persona-name">{p.display_name}</span>
                        <span className="signin-persona-badge">{p.role}</span>
                      </div>
                      <div className="signin-persona-desc">{p.description}</div>
                      <div className="signin-persona-email">{p.email}</div>
                    </div>
                  </div>
                );
              })}
            </div>

            <button
              type="button"
              className="btn btn-primary signin-submit-btn"
              onClick={handleDemoAccess}
              disabled={loading}
            >
              {loading ? (
                <span>Generating Cryptographic Session...</span>
              ) : (
                <>
                  <span>Continue to Demo Workspace</span>
                  <ArrowRight size={15} />
                </>
              )}
            </button>
          </div>
        )}

        {/* Tab 2: Operator Credentials Sign In */}
        {authMode === 'credentials' && (
          <form onSubmit={handleCredentialLogin} className="signin-form">
            <div className="form-group">
              <label className="form-label" htmlFor="merchant-email">
                Merchant Email Address
              </label>
              <input
                id="merchant-email"
                type="email"
                className="form-input"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="ops@merchant.example.com"
                required
              />
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="merchant-password">
                Password
              </label>
              <input
                id="merchant-password"
                type="password"
                className="form-input"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••••••"
                required
              />
            </div>

            <div className="signin-hint-box">
              <div style={{ fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '3px' }}>
                Evaluation Credentials:
              </div>
              <div><code>ops@merchant.example.com</code> / <code>docket2026</code> (Operations Lead)</div>
              <div><code>supervisor@merchant.example.com</code> / <code>docket2026</code> (Risk Supervisor)</div>
            </div>

            <button
              type="submit"
              className="btn btn-primary signin-submit-btn"
              disabled={loading}
            >
              {loading ? (
                <span>Authenticating Principal...</span>
              ) : (
                <>
                  <Lock size={14} />
                  <span>Sign In as Merchant Principal</span>
                </>
              )}
            </button>
          </form>
        )}

        {/* Cryptographic Assurance Footer */}
        <div className="signin-footer-assurances">
          <div className="assurance-item">
            <ShieldCheck size={12} style={{ color: 'var(--signal-blue)' }} />
            <span>HMAC-SHA256 Token Binding</span>
          </div>
          <div className="assurance-item">
            <CheckCircle2 size={12} style={{ color: '#059669' }} />
            <span>SHA-256 Tamper-Evident Ledger</span>
          </div>
          <div className="assurance-item">
            <Lock size={12} style={{ color: 'var(--text-secondary)' }} />
            <span>Strict Anti-Spoofing</span>
          </div>
        </div>
      </div>
    </div>
  );
};
