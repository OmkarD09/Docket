import React, { useState, useEffect, useMemo, useCallback } from 'react';
import {
  Search,
  AlertTriangle,
} from 'lucide-react';
import { Sidebar } from './components/Sidebar';
import type { NavSection } from './components/Sidebar';
import { TopHeader } from './components/TopHeader';
import { OverviewDashboard } from './components/OverviewDashboard';
import { DisputeTable } from './components/DisputeTable';
import { DisputeDetailPanel } from './components/DisputeDetailPanel';
import { AuditTrailView } from './components/AuditTrailView';
import { EvalScorecardView } from './components/EvalScorecardView';
import { SignInView } from './components/SignInView';
import type { DisputeSummary, AuthenticatedMerchant, SyncStatusData, AuditStatusData } from './types';

export const App: React.FC = () => {
  // Merchant Authentication State
  const [currentUser, setCurrentUser] = useState<AuthenticatedMerchant | null>(null);
  const [authChecking, setAuthChecking] = useState<boolean>(true);

  // Automated Synchronization & Continuous Audit Integrity Telemetry
  const [syncStatus, setSyncStatus] = useState<SyncStatusData | null>(null);
  const [auditStatus, setAuditStatus] = useState<AuditStatusData | null>(null);

  const [activeSection, setActiveSection] = useState<NavSection>('overview');
  const [sidebarCollapsed, setSidebarCollapsed] = useState<boolean>(false);
  const [disputes, setDisputes] = useState<DisputeSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [selectedDisputeId, setSelectedDisputeId] = useState<string | null>(null);

  // Filters for Dispute Workspace
  const [scopeFilter, setScopeFilter] = useState<'ALL' | 'REAL' | 'BENCHMARK'>('ALL');
  const [decisionFilter, setDecisionFilter] = useState<'ALL' | 'READY' | 'REVIEW' | 'BLOCKED' | 'THREATS'>('ALL');
  const [searchQuery, setSearchQuery] = useState<string>('');

  const fetchDisputes = useCallback(async (silent = false) => {
    try {
      setError(null);
      const res = await fetch('/api/disputes');
      if (!res.ok) {
        throw new Error(`HTTP error ${res.status}: ${res.statusText}`);
      }
      const data: DisputeSummary[] = await res.json();
      setDisputes(data);

      // Default select the real sandbox dispute if available, else first dispute
      if (data.length > 0) {
        setSelectedDisputeId((prev) => {
          if (prev && data.some((d) => d.dispute_id === prev)) {
            return prev;
          }
          const realSandbox = data.find((d) => d.dispute_id === 'PP-R-NKI-10193390');
          return realSandbox ? realSandbox.dispute_id : data[0].dispute_id;
        });
      }
    } catch (err: any) {
      console.error('Failed to fetch disputes:', err);
      if (!silent) setError(err.message || 'Failed to fetch disputes');
    }
  }, []);

  // Fetch continuous synchronisation and audit integrity telemetry
  const fetchTelemetry = useCallback(async () => {
    try {
      const [syncRes, auditRes] = await Promise.all([
        fetch('/api/sync/status'),
        fetch('/api/audit-trail/status'),
      ]);
      if (syncRes.ok) {
        const syncData: SyncStatusData = await syncRes.json();
        setSyncStatus(syncData);
      }
      if (auditRes.ok) {
        const auditData: AuditStatusData = await auditRes.json();
        setAuditStatus(auditData);
      }
    } catch (err) {
      // Conservative error handling: preserve last known state on transient network blip
      console.warn('Telemetry polling error (preserving last known status):', err);
    }
  }, []);

  // Merchant Session Verification
  const checkAuth = useCallback(async () => {
    try {
      setAuthChecking(true);
      const res = await fetch('/api/auth/me');
      if (res.ok) {
        const user: AuthenticatedMerchant = await res.json();
        setCurrentUser(user);
      } else {
        setCurrentUser(null);
      }
    } catch (err) {
      console.error('Session verification failed:', err);
      setCurrentUser(null);
    } finally {
      setAuthChecking(false);
    }
  }, []);

  const handleSignOut = async () => {
    try {
      await fetch('/api/auth/logout', { method: 'POST' });
    } catch (err) {
      console.error('Sign out error:', err);
    } finally {
      setCurrentUser(null);
    }
  };

  useEffect(() => {
    checkAuth();
  }, [checkAuth]);

  useEffect(() => {
    if (currentUser) {
      fetchDisputes();
      fetchTelemetry();

      // Conservative background status polling (every 8 seconds)
      const timer = setInterval(() => {
        fetchTelemetry();
        fetchDisputes(true);
      }, 8000);

      return () => clearInterval(timer);
    }
  }, [currentUser, fetchDisputes, fetchTelemetry]);

  // Global Keyboard Shortcuts (1: Overview, 2: Disputes, 3: Audit, 4: Benchmark)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const activeEl = document.activeElement;
      if (
        activeEl &&
        (activeEl.tagName === 'INPUT' ||
          activeEl.tagName === 'TEXTAREA' ||
          activeEl.tagName === 'SELECT' ||
          (activeEl as HTMLElement).isContentEditable)
      ) {
        return;
      }
      if (e.key === '1') setActiveSection('overview');
      if (e.key === '2') setActiveSection('disputes');
      if (e.key === '3') setActiveSection('audit');
      if (e.key === '4') setActiveSection('benchmark');
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  const handleNavigateToDisputes = (disputeId?: string) => {
    if (disputeId) {
      setSelectedDisputeId(disputeId);
    }
    setActiveSection('disputes');
  };

  // Operational metrics separated into Real Sandbox vs Benchmarks
  const metrics = useMemo(() => {
    const realDisputes = disputes.filter(
      (d) => d.dispute_id === 'PP-R-NKI-10193390' || (d.scenario_id && d.scenario_id.includes('REAL_SANDBOX'))
    );
    const benchmarkCount = disputes.length - realDisputes.length;

    const readyCount = disputes.filter((d) => d.is_ready_for_submission).length;
    const reviewCount = disputes.filter((d) => d.overall_decision === 'REVIEW').length;
    const blockedCount = disputes.filter((d) => d.overall_decision === 'BLOCK').length;
    const threatsCount = disputes.filter((d) => d.has_prompt_threat).length;

    return {
      total: disputes.length,
      realCount: realDisputes.length,
      benchmarkCount,
      readyCount,
      reviewCount,
      blockedCount,
      threatsCount,
    };
  }, [disputes]);

  // Filtered Disputes
  const filteredDisputes = useMemo(() => {
    return disputes.filter((d) => {
      // 1. Scope filter
      const isReal = d.dispute_id === 'PP-R-NKI-10193390' || (d.scenario_id && d.scenario_id.includes('REAL_SANDBOX'));
      if (scopeFilter === 'REAL' && !isReal) return false;
      if (scopeFilter === 'BENCHMARK' && isReal) return false;

      // 2. Search query
      const q = searchQuery.toLowerCase();
      const matchesSearch =
        d.dispute_id.toLowerCase().includes(q) ||
        (d.matched_order_id && d.matched_order_id.toLowerCase().includes(q)) ||
        (d.tracking_number && d.tracking_number.toLowerCase().includes(q)) ||
        d.reason.toLowerCase().includes(q);

      if (!matchesSearch) return false;

      // 3. Decision filter
      if (decisionFilter === 'READY') return d.is_ready_for_submission;
      if (decisionFilter === 'REVIEW') return d.overall_decision === 'REVIEW';
      if (decisionFilter === 'BLOCKED') return d.overall_decision === 'BLOCK';
      if (decisionFilter === 'THREATS') return d.has_prompt_threat;
      return true;
    });
  }, [disputes, scopeFilter, searchQuery, decisionFilter]);

  if (authChecking) {
    return (
      <div
        style={{
          minHeight: '100vh',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          backgroundColor: 'var(--bg-canvas)',
          gap: '12px',
        }}
      >
        <div
          style={{
            width: '28px',
            height: '28px',
            border: '2.5px solid var(--border-subtle)',
            borderTopColor: 'var(--signal-blue)',
            borderRadius: '50%',
            animation: 'spin 0.8s linear infinite',
          }}
        />
        <div style={{ fontSize: '12px', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
          Verifying merchant authentication session...
        </div>
      </div>
    );
  }

  if (!currentUser) {
    return (
      <SignInView
        onSignInSuccess={(user) => {
          setCurrentUser(user);
        }}
      />
    );
  }

  return (
    <div className="app-shell">
      {/* 1. Persistent Left Sidebar Navigation */}
      <Sidebar
        activeSection={activeSection}
        onSelectSection={setActiveSection}
        collapsed={sidebarCollapsed}
        onToggleCollapse={() => setSidebarCollapsed(!sidebarCollapsed)}
        disputeCount={disputes.length}
      />

      {/* 2. Main Application Content Area */}
      <div className="main-wrapper">
        <TopHeader
          activeSection={activeSection}
          selectedDisputeId={selectedDisputeId}
          currentUser={currentUser}
          onSignOut={handleSignOut}
          syncStatus={syncStatus}
          auditStatus={auditStatus}
        />

        {/* 3. Section Router */}
        <div className="content-area">
          {activeSection === 'overview' && (
            <OverviewDashboard
              disputes={disputes}
              onNavigateToDisputes={handleNavigateToDisputes}
            />
          )}

          {activeSection === 'disputes' && (
            <div className="disputes-workspace-container">
              {/* Disputes Professional Toolbar */}
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '8px 18px',
                  backgroundColor: 'var(--bg-surface)',
                  borderBottom: '1px solid var(--border-subtle)',
                  gap: '12px',
                  flexShrink: 0,
                }}
              >
                {/* Segmented Dataset Scope Control */}
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    backgroundColor: 'var(--bg-subtle)',
                    padding: '2px',
                    borderRadius: '6px',
                    border: '1px solid var(--border-light)',
                    gap: '2px',
                  }}
                >
                  <button
                    className="btn"
                    style={{
                      padding: '3px 9px',
                      fontSize: '11px',
                      height: '24px',
                      backgroundColor: scopeFilter === 'ALL' ? '#FFFFFF' : 'transparent',
                      color: scopeFilter === 'ALL' ? 'var(--text-primary)' : 'var(--text-secondary)',
                      boxShadow: scopeFilter === 'ALL' ? 'var(--shadow-xs)' : 'none',
                      fontWeight: scopeFilter === 'ALL' ? 600 : 500,
                      borderRadius: '4px',
                    }}
                    onClick={() => setScopeFilter('ALL')}
                  >
                    All Records ({disputes.length})
                  </button>
                  <button
                    className="btn"
                    style={{
                      padding: '3px 9px',
                      fontSize: '11px',
                      height: '24px',
                      backgroundColor: scopeFilter === 'REAL' ? '#FFFFFF' : 'transparent',
                      color: scopeFilter === 'REAL' ? 'var(--text-primary)' : 'var(--text-secondary)',
                      boxShadow: scopeFilter === 'REAL' ? 'var(--shadow-xs)' : 'none',
                      fontWeight: scopeFilter === 'REAL' ? 600 : 500,
                      borderRadius: '4px',
                    }}
                    onClick={() => setScopeFilter('REAL')}
                  >
                    <span style={{ width: '5px', height: '5px', borderRadius: '50%', backgroundColor: '#059669', marginRight: '5px' }} />
                    Live Sandbox ({metrics.realCount})
                  </button>
                  <button
                    className="btn"
                    style={{
                      padding: '3px 9px',
                      fontSize: '11px',
                      height: '24px',
                      backgroundColor: scopeFilter === 'BENCHMARK' ? '#FFFFFF' : 'transparent',
                      color: scopeFilter === 'BENCHMARK' ? 'var(--text-primary)' : 'var(--text-secondary)',
                      boxShadow: scopeFilter === 'BENCHMARK' ? 'var(--shadow-xs)' : 'none',
                      fontWeight: scopeFilter === 'BENCHMARK' ? 600 : 500,
                      borderRadius: '4px',
                    }}
                    onClick={() => setScopeFilter('BENCHMARK')}
                  >
                    Benchmarks ({metrics.benchmarkCount})
                  </button>
                </div>

                {/* Search Box */}
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px',
                    backgroundColor: 'var(--bg-canvas)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: '5px',
                    padding: '3px 8px',
                    width: '220px',
                    transition: 'border-color var(--transition-fast)',
                  }}
                >
                  <Search size={12} style={{ color: 'var(--text-muted)' }} />
                  <input
                    type="text"
                    placeholder="Filter ID, Order, Carrier..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    style={{
                      border: 'none',
                      background: 'transparent',
                      outline: 'none',
                      fontSize: '11.5px',
                      color: 'var(--text-primary)',
                      width: '100%',
                    }}
                  />
                  {searchQuery && (
                    <button
                      onClick={() => setSearchQuery('')}
                      style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', display: 'flex', alignItems: 'center' }}
                      title="Clear search"
                    >
                      ×
                    </button>
                  )}
                </div>

                {/* Policy Decision Filter Chips */}
                <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <button
                    className="btn"
                    style={{
                      padding: '3px 8px',
                      fontSize: '11px',
                      height: '26px',
                      backgroundColor: decisionFilter === 'ALL' ? 'var(--bg-subtle)' : 'var(--bg-surface)',
                      border: '1px solid var(--border-subtle)',
                      fontWeight: decisionFilter === 'ALL' ? 600 : 500,
                      color: decisionFilter === 'ALL' ? 'var(--text-primary)' : 'var(--text-secondary)',
                    }}
                    onClick={() => setDecisionFilter('ALL')}
                  >
                    All
                  </button>
                  <button
                    className="btn"
                    style={{
                      padding: '3px 8px',
                      fontSize: '11px',
                      height: '26px',
                      backgroundColor: decisionFilter === 'READY' ? 'var(--status-allow-bg)' : 'var(--bg-surface)',
                      color: decisionFilter === 'READY' ? 'var(--status-allow-text)' : 'var(--text-secondary)',
                      border: `1px solid ${decisionFilter === 'READY' ? 'var(--status-allow-border)' : 'var(--border-subtle)'}`,
                      fontWeight: decisionFilter === 'READY' ? 600 : 500,
                    }}
                    onClick={() => setDecisionFilter('READY')}
                  >
                    Ready ({metrics.readyCount})
                  </button>
                  <button
                    className="btn"
                    style={{
                      padding: '3px 8px',
                      fontSize: '11px',
                      height: '26px',
                      backgroundColor: decisionFilter === 'REVIEW' ? 'var(--status-review-bg)' : 'var(--bg-surface)',
                      color: decisionFilter === 'REVIEW' ? 'var(--status-review-text)' : 'var(--text-secondary)',
                      border: `1px solid ${decisionFilter === 'REVIEW' ? 'var(--status-review-border)' : 'var(--border-subtle)'}`,
                      fontWeight: decisionFilter === 'REVIEW' ? 600 : 500,
                    }}
                    onClick={() => setDecisionFilter('REVIEW')}
                  >
                    Review ({metrics.reviewCount})
                  </button>
                  <button
                    className="btn"
                    style={{
                      padding: '3px 8px',
                      fontSize: '11px',
                      height: '26px',
                      backgroundColor: decisionFilter === 'BLOCKED' ? 'var(--status-block-bg)' : 'var(--bg-surface)',
                      color: decisionFilter === 'BLOCKED' ? 'var(--status-block-text)' : 'var(--text-secondary)',
                      border: `1px solid ${decisionFilter === 'BLOCKED' ? 'var(--status-block-border)' : 'var(--border-subtle)'}`,
                      fontWeight: decisionFilter === 'BLOCKED' ? 600 : 500,
                    }}
                    onClick={() => setDecisionFilter('BLOCKED')}
                  >
                    Blocked ({metrics.blockedCount})
                  </button>
                  <button
                    className="btn"
                    style={{
                      padding: '3px 8px',
                      fontSize: '11px',
                      height: '26px',
                      backgroundColor: decisionFilter === 'THREATS' ? 'var(--status-threat-bg)' : 'var(--bg-surface)',
                      color: decisionFilter === 'THREATS' ? 'var(--status-threat-text)' : 'var(--text-secondary)',
                      border: `1px solid ${decisionFilter === 'THREATS' ? 'var(--status-threat-border)' : 'var(--border-subtle)'}`,
                      fontWeight: decisionFilter === 'THREATS' ? 600 : 500,
                    }}
                    onClick={() => setDecisionFilter('THREATS')}
                  >
                    Threats ({metrics.threatsCount})
                  </button>
                </div>
              </div>

              {/* Split Workspace: AG Grid on Left, Evidence-First Drawer on Right */}
              <div className={`disputes-workspace-split ${!selectedDisputeId ? 'full-width' : ''}`}>
                <div className="disputes-grid-wrapper">
                  {error ? (
                    <div className="empty-state">
                      <AlertTriangle size={32} style={{ color: 'var(--status-block-dot)' }} />
                      <p style={{ marginTop: '12px', fontWeight: 600 }}>Failed to load disputes</p>
                      <p style={{ fontSize: '12px', color: 'var(--text-muted)' }}>{error}</p>
                      <button className="btn btn-secondary" onClick={() => fetchDisputes(false)} style={{ marginTop: '12px' }}>
                        Retry
                      </button>
                    </div>
                  ) : (
                    <DisputeTable
                      disputes={filteredDisputes}
                      selectedDisputeId={selectedDisputeId}
                      onSelectDispute={(id) => setSelectedDisputeId(id)}
                    />
                  )}
                </div>

                {selectedDisputeId && (
                  <DisputeDetailPanel
                    disputeId={selectedDisputeId}
                    onRefresh={fetchDisputes}
                    onClose={() => setSelectedDisputeId(null)}
                  />
                )}
              </div>
            </div>
          )}

          {activeSection === 'audit' && (
            <AuditTrailView onNavigateToDispute={handleNavigateToDisputes} />
          )}

          {activeSection === 'benchmark' && <EvalScorecardView />}
        </div>
      </div>
    </div>
  );
};

export default App;
