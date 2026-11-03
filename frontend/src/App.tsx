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
import type { DisputeSummary } from './types';

export const App: React.FC = () => {
  const [activeSection, setActiveSection] = useState<NavSection>('overview');
  const [sidebarCollapsed, setSidebarCollapsed] = useState<boolean>(false);
  const [disputes, setDisputes] = useState<DisputeSummary[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedDisputeId, setSelectedDisputeId] = useState<string | null>(null);

  // Filters for Dispute Workspace
  const [scopeFilter, setScopeFilter] = useState<'ALL' | 'REAL' | 'BENCHMARK'>('ALL');
  const [decisionFilter, setDecisionFilter] = useState<'ALL' | 'READY' | 'REVIEW' | 'BLOCKED' | 'THREATS'>('ALL');
  const [searchQuery, setSearchQuery] = useState<string>('');

  const fetchDisputes = useCallback(async () => {
    try {
      setLoading(true);
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
      setError(err.message || 'Failed to fetch disputes');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchDisputes();
  }, [fetchDisputes]);

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
          onRefresh={fetchDisputes}
          loading={loading}
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
              {/* Disputes Toolbar */}
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '8px 20px',
                  backgroundColor: 'var(--bg-canvas)',
                  borderBottom: '1px solid var(--border-subtle)',
                  gap: '12px',
                  flexShrink: 0,
                }}
              >
                {/* Dataset Scope Toggle */}
                <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <button
                    className={`btn ${scopeFilter === 'ALL' ? 'btn-primary' : 'btn-secondary'}`}
                    style={{ padding: '3px 8px', fontSize: '11px', height: '26px' }}
                    onClick={() => setScopeFilter('ALL')}
                  >
                    All Records ({disputes.length})
                  </button>
                  <button
                    className={`btn ${scopeFilter === 'REAL' ? 'btn-primary' : 'btn-secondary'}`}
                    style={{ padding: '3px 8px', fontSize: '11px', height: '26px' }}
                    onClick={() => setScopeFilter('REAL')}
                  >
                    <span style={{ width: '5px', height: '5px', borderRadius: '50%', backgroundColor: '#059669', marginRight: '4px' }} />
                    Live Sandbox ({metrics.realCount})
                  </button>
                  <button
                    className={`btn ${scopeFilter === 'BENCHMARK' ? 'btn-primary' : 'btn-secondary'}`}
                    style={{ padding: '3px 8px', fontSize: '11px', height: '26px' }}
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
                    backgroundColor: 'var(--bg-surface)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: '5px',
                    padding: '4px 8px',
                    width: '200px',
                  }}
                >
                  <Search size={12} style={{ color: 'var(--text-muted)' }} />
                  <input
                    type="text"
                    placeholder="Search ID, Order, Carrier..."
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
                </div>

                {/* Policy Decision Filter Chips */}
                <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <button
                    className="btn btn-secondary"
                    style={{
                      padding: '3px 8px',
                      fontSize: '11px',
                      height: '26px',
                      backgroundColor: decisionFilter === 'ALL' ? 'var(--bg-subtle)' : 'var(--bg-surface)',
                      fontWeight: decisionFilter === 'ALL' ? 600 : 500,
                    }}
                    onClick={() => setDecisionFilter('ALL')}
                  >
                    All Decisions
                  </button>
                  <button
                    className="btn btn-secondary"
                    style={{
                      padding: '3px 8px',
                      fontSize: '11px',
                      height: '26px',
                      backgroundColor: decisionFilter === 'READY' ? 'var(--status-allow-bg)' : 'var(--bg-surface)',
                      color: decisionFilter === 'READY' ? 'var(--status-allow-text)' : 'inherit',
                      fontWeight: decisionFilter === 'READY' ? 600 : 500,
                    }}
                    onClick={() => setDecisionFilter('READY')}
                  >
                    Ready ({metrics.readyCount})
                  </button>
                  <button
                    className="btn btn-secondary"
                    style={{
                      padding: '3px 8px',
                      fontSize: '11px',
                      height: '26px',
                      backgroundColor: decisionFilter === 'REVIEW' ? 'var(--status-review-bg)' : 'var(--bg-surface)',
                      color: decisionFilter === 'REVIEW' ? 'var(--status-review-text)' : 'inherit',
                      fontWeight: decisionFilter === 'REVIEW' ? 600 : 500,
                    }}
                    onClick={() => setDecisionFilter('REVIEW')}
                  >
                    Review ({metrics.reviewCount})
                  </button>
                  <button
                    className="btn btn-secondary"
                    style={{
                      padding: '3px 8px',
                      fontSize: '11px',
                      height: '26px',
                      backgroundColor: decisionFilter === 'BLOCKED' ? 'var(--status-block-bg)' : 'var(--bg-surface)',
                      color: decisionFilter === 'BLOCKED' ? 'var(--status-block-text)' : 'inherit',
                      fontWeight: decisionFilter === 'BLOCKED' ? 600 : 500,
                    }}
                    onClick={() => setDecisionFilter('BLOCKED')}
                  >
                    Blocked ({metrics.blockedCount})
                  </button>
                  <button
                    className="btn btn-secondary"
                    style={{
                      padding: '3px 8px',
                      fontSize: '11px',
                      height: '26px',
                      backgroundColor: decisionFilter === 'THREATS' ? 'var(--status-threat-bg)' : 'var(--bg-surface)',
                      color: decisionFilter === 'THREATS' ? 'var(--status-threat-text)' : 'inherit',
                      fontWeight: decisionFilter === 'THREATS' ? 600 : 500,
                    }}
                    onClick={() => setDecisionFilter('THREATS')}
                  >
                    Threats ({metrics.threatsCount})
                  </button>
                </div>
              </div>

              {/* Split Workspace: AG Grid on Left, Evidence-First Drawer on Right */}
              <div className="disputes-workspace-split">
                <div className="disputes-grid-wrapper">
                  {error ? (
                    <div className="empty-state">
                      <AlertTriangle size={32} style={{ color: 'var(--status-block-dot)' }} />
                      <p style={{ marginTop: '12px', fontWeight: 600 }}>Failed to load disputes</p>
                      <p style={{ fontSize: '12px', color: 'var(--text-muted)' }}>{error}</p>
                      <button className="btn btn-secondary" onClick={fetchDisputes} style={{ marginTop: '12px' }}>
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

                <DisputeDetailPanel
                  disputeId={selectedDisputeId}
                  onRefresh={fetchDisputes}
                />
              </div>
            </div>
          )}

          {activeSection === 'audit' && <AuditTrailView />}

          {activeSection === 'benchmark' && <EvalScorecardView />}
        </div>
      </div>
    </div>
  );
};

export default App;
