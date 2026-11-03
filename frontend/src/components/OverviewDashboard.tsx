import React, { useMemo } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  XCircle,
  ArrowRight,
  PieChart,
  BarChart,
  Activity,
  ShieldAlert,
} from 'lucide-react';
import type { DisputeSummary } from '../types';

interface OverviewDashboardProps {
  disputes: DisputeSummary[];
  onNavigateToDisputes: (disputeId?: string) => void;
}

export const OverviewDashboard: React.FC<OverviewDashboardProps> = ({
  disputes,
  onNavigateToDisputes,
}) => {
  // 1. Operational KPI calculations
  const kpis = useMemo(() => {
    const total = disputes.length;
    const realDisputes = disputes.filter(
      (d) => d.dispute_id === 'PP-R-NKI-10193390' || (d.scenario_id && d.scenario_id.includes('REAL_SANDBOX'))
    );
    const benchmarkCount = total - realDisputes.length;

    const waitingSellerAction = disputes.filter(
      (d) => d.status === 'WAITING_FOR_SELLER_RESPONSE'
    ).length;

    const reviewRequired = disputes.filter(
      (d) => d.overall_decision === 'REVIEW'
    ).length;

    const policyBlocked = disputes.filter(
      (d) => d.overall_decision === 'BLOCK'
    ).length;

    const readyToSubmit = disputes.filter(
      (d) => d.is_ready_for_submission
    ).length;

    return {
      total,
      realCount: realDisputes.length,
      benchmarkCount,
      waitingSellerAction,
      reviewRequired,
      policyBlocked,
      readyToSubmit,
    };
  }, [disputes]);

  // 2. Chart Data: Dispute Statuses
  const statusDistribution = useMemo(() => {
    const map: Record<string, number> = {};
    disputes.forEach((d) => {
      const s = d.status || 'UNKNOWN';
      map[s] = (map[s] || 0) + 1;
    });
    return Object.entries(map).map(([status, count]) => ({
      status: status.replace(/_/g, ' ').toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase()),
      rawStatus: status,
      count,
      pct: ((count / disputes.length) * 100).toFixed(1),
    }));
  }, [disputes]);

  // 3. Chart Data: Policy Decisions
  const decisionDistribution = useMemo(() => {
    const allowCount = disputes.filter((d) => d.overall_decision === 'ALLOW').length;
    const reviewCount = disputes.filter((d) => d.overall_decision === 'REVIEW').length;
    const blockCount = disputes.filter((d) => d.overall_decision === 'BLOCK').length;
    const total = disputes.length || 1;

    return [
      {
        decision: 'ALLOW',
        label: 'Approved by Invariants',
        count: allowCount,
        pct: ((allowCount / total) * 100).toFixed(0),
        color: 'var(--status-allow-dot)',
        bg: 'var(--status-allow-bg)',
        border: 'var(--status-allow-border)',
        text: 'var(--status-allow-text)',
      },
      {
        decision: 'REVIEW',
        label: 'Merchant Review Needed',
        count: reviewCount,
        pct: ((reviewCount / total) * 100).toFixed(0),
        color: 'var(--status-review-dot)',
        bg: 'var(--status-review-bg)',
        border: 'var(--status-review-border)',
        text: 'var(--status-review-text)',
      },
      {
        decision: 'BLOCK',
        label: 'Policy Blocked / Refused',
        count: blockCount,
        pct: ((blockCount / total) * 100).toFixed(0),
        color: 'var(--status-block-dot)',
        bg: 'var(--status-block-bg)',
        border: 'var(--status-block-border)',
        text: 'var(--status-block-text)',
      },
    ];
  }, [disputes]);

  // 4. Chart Data: Dispute Reasons
  const reasonDistribution = useMemo(() => {
    const map: Record<string, number> = {};
    disputes.forEach((d) => {
      const r = d.reason || 'OTHER';
      map[r] = (map[r] || 0) + 1;
    });
    return Object.entries(map)
      .map(([reason, count]) => ({
        reason: reason.replace(/_/g, ' ').toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase()),
        rawReason: reason,
        count,
        pct: ((count / disputes.length) * 100).toFixed(0),
      }))
      .sort((a, b) => b.count - a.count);
  }, [disputes]);

  // 5. Recent Disputes (First 6 items)
  const recentDisputes = useMemo(() => {
    return disputes.slice(0, 6);
  }, [disputes]);

  return (
    <div className="page-scrollable">
      {/* Section A: Page Introduction */}
      <div>
        <h2 style={{ fontSize: '18px', fontWeight: 700, color: 'var(--text-primary)', letterSpacing: '-0.02em' }}>
          Overview
        </h2>
        <div style={{ fontSize: '13px', color: 'var(--text-muted)', marginTop: '2px' }}>
          Monitor dispute volume, review evidence reconciliation health, and track deterministic policy enforcement across active cases.
        </div>
      </div>

      {/* Section B: Operational KPI Strip */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(4, 1fr)',
          gap: '14px',
        }}
      >
        <div className="card" style={{ padding: '14px 18px' }}>
          <div style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em', fontWeight: 600 }}>
            Total Disputes Tracked
          </div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '6px', marginTop: '4px' }}>
            <span className="font-mono" style={{ fontSize: '26px', fontWeight: 700, color: 'var(--text-primary)' }}>
              {kpis.total}
            </span>
          </div>
          <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '4px', display: 'flex', alignItems: 'center', gap: '4px' }}>
            <span style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: '#059669' }} />
            <span>{kpis.realCount} Live Sandbox · {kpis.benchmarkCount} Benchmarks</span>
          </div>
        </div>

        <div className="card" style={{ padding: '14px 18px' }}>
          <div style={{ fontSize: '11px', color: 'var(--signal-blue)', textTransform: 'uppercase', letterSpacing: '0.04em', fontWeight: 600 }}>
            Awaiting Seller Action
          </div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '6px', marginTop: '4px' }}>
            <span className="font-mono" style={{ fontSize: '26px', fontWeight: 700, color: 'var(--signal-blue)' }}>
              {kpis.waitingSellerAction}
            </span>
          </div>
          <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '4px' }}>
            Active PayPal response windows
          </div>
        </div>

        <div className="card" style={{ padding: '14px 18px' }}>
          <div style={{ fontSize: '11px', color: 'var(--status-review-text)', textTransform: 'uppercase', letterSpacing: '0.04em', fontWeight: 600 }}>
            Evidence Review Required
          </div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '6px', marginTop: '4px' }}>
            <span className="font-mono" style={{ fontSize: '26px', fontWeight: 700, color: 'var(--status-review-text)' }}>
              {kpis.reviewRequired}
            </span>
          </div>
          <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '4px' }}>
            High-value or signature advisory cases
          </div>
        </div>

        <div className="card" style={{ padding: '14px 18px' }}>
          <div style={{ fontSize: '11px', color: 'var(--status-block-text)', textTransform: 'uppercase', letterSpacing: '0.04em', fontWeight: 600 }}>
            Policy-Blocked Claims
          </div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '6px', marginTop: '4px' }}>
            <span className="font-mono" style={{ fontSize: '26px', fontWeight: 700, color: 'var(--status-block-text)' }}>
              {kpis.policyBlocked}
            </span>
          </div>
          <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '4px' }}>
            Label-created & delivery gaps refused
          </div>
        </div>
      </div>

      {/* Section C: Financial Data Visualizations & Charts Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr', gap: '16px' }}>
        {/* Chart 1: Policy Decision Distribution (Visual Breakdown) */}
        <div className="card">
          <div className="card-header">
            <span className="card-title">
              <Activity size={13} color="var(--accent-slate)" />
              Docket Policy Engine Outcomes
            </span>
            <span className="badge badge-neutral">Deterministic Enforcement</span>
          </div>
          <div className="card-body">
            <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              {/* Stacked Proportional Bar */}
              <div style={{ display: 'flex', height: '14px', borderRadius: '4px', overflow: 'hidden', backgroundColor: 'var(--bg-subtle)' }}>
                {decisionDistribution.map((item) => (
                  <div
                    key={item.decision}
                    style={{
                      width: `${item.pct}%`,
                      backgroundColor: item.color,
                      transition: 'width 200ms ease',
                    }}
                    title={`${item.decision}: ${item.count} cases (${item.pct}%)`}
                  />
                ))}
              </div>

              {/* Legend & Details */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '10px' }}>
                {decisionDistribution.map((item) => (
                  <div
                    key={item.decision}
                    style={{
                      padding: '10px 12px',
                      borderRadius: '6px',
                      backgroundColor: item.bg,
                      border: `1px solid ${item.border}`,
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '5px', fontSize: '11px', fontWeight: 600, color: item.text }}>
                      <span style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: item.color }} />
                      <span>{item.decision}</span>
                    </div>
                    <div style={{ fontSize: '18px', fontWeight: 700, color: item.text, marginTop: '2px', fontFamily: 'var(--font-mono)' }}>
                      {item.count} <span style={{ fontSize: '11px', fontWeight: 500 }}>({item.pct}%)</span>
                    </div>
                    <div style={{ fontSize: '10.5px', color: 'var(--text-secondary)', marginTop: '2px' }}>
                      {item.label}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* Chart 2: PayPal Dispute Status Distribution */}
        <div className="card">
          <div className="card-header">
            <span className="card-title">
              <PieChart size={13} color="var(--accent-slate)" />
              PayPal Dispute Status Distribution
            </span>
            <span className="badge badge-neutral">PayPal API Lifecycle</span>
          </div>
          <div className="card-body">
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              {statusDistribution.map((st) => (
                <div key={st.rawStatus} style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11.5px' }}>
                    <span style={{ fontWeight: 500, color: 'var(--text-primary)' }}>{st.status}</span>
                    <span className="font-mono" style={{ color: 'var(--text-muted)' }}>
                      <strong>{st.count}</strong> ({st.pct}%)
                    </span>
                  </div>
                  <div style={{ height: '6px', borderRadius: '3px', backgroundColor: 'var(--bg-subtle)', overflow: 'hidden' }}>
                    <div
                      style={{
                        height: '100%',
                        width: `${st.pct}%`,
                        backgroundColor:
                          st.rawStatus === 'WAITING_FOR_SELLER_RESPONSE'
                            ? 'var(--signal-blue)'
                            : st.rawStatus === 'RESOLVED'
                            ? '#64748B'
                            : '#0F172A',
                      }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Chart 3: Dispute Reason Breakdown */}
      <div className="card">
        <div className="card-header">
          <span className="card-title">
            <BarChart size={13} color="var(--accent-slate)" />
            Dispute Categories & Fraud Vectors
          </span>
          <span className="badge badge-neutral">{reasonDistribution.length} Categories Classified</span>
        </div>
        <div className="card-body">
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '14px' }}>
            {reasonDistribution.map((item) => (
              <div
                key={item.rawReason}
                style={{
                  padding: '10px 14px',
                  backgroundColor: '#fafbfc',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: '6px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                }}
              >
                <div>
                  <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-primary)' }}>
                    {item.reason}
                  </div>
                  <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                    {item.rawReason}
                  </div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <span className="font-mono" style={{ fontSize: '16px', fontWeight: 700, color: 'var(--accent-slate)' }}>
                    {item.count}
                  </span>
                  <div style={{ fontSize: '10.5px', color: 'var(--text-muted)' }}>
                    {item.pct}% of total
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Section D: Recent Disputes Table */}
      <div className="card">
        <div className="card-header">
          <span className="card-title">
            Recent Dispute Records
          </span>
          <button
            onClick={() => onNavigateToDisputes()}
            className="btn btn-secondary"
            style={{ padding: '3px 8px', fontSize: '11px' }}
          >
            <span>Open Dispute Workspace</span>
            <ArrowRight size={12} />
          </button>
        </div>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border-subtle)', backgroundColor: 'var(--bg-header)', color: 'var(--text-muted)' }}>
                <th style={{ padding: '9px 16px', textAlign: 'left', fontWeight: 600 }}>Dispute Reference</th>
                <th style={{ padding: '9px 16px', textAlign: 'left', fontWeight: 600 }}>Origin</th>
                <th style={{ padding: '9px 16px', textAlign: 'left', fontWeight: 600 }}>Dispute Reason</th>
                <th style={{ padding: '9px 16px', textAlign: 'right', fontWeight: 600 }}>Amount</th>
                <th style={{ padding: '9px 16px', textAlign: 'left', fontWeight: 600 }}>PayPal Status</th>
                <th style={{ padding: '9px 16px', textAlign: 'center', fontWeight: 600 }}>Docket Decision</th>
                <th style={{ padding: '9px 16px', textAlign: 'right', fontWeight: 600 }}>Action</th>
              </tr>
            </thead>
            <tbody>
              {recentDisputes.map((d) => {
                const isReal = d.dispute_id === 'PP-R-NKI-10193390' || (d.scenario_id && d.scenario_id.includes('REAL_SANDBOX'));
                const reasonReadable = (d.reason || '')
                  .replace(/_/g, ' ')
                  .toLowerCase()
                  .replace(/\b\w/g, (c) => c.toUpperCase());

                return (
                  <tr
                    key={d.dispute_id}
                    onClick={() => onNavigateToDisputes(d.dispute_id)}
                    style={{
                      borderBottom: '1px solid var(--border-subtle)',
                      cursor: 'pointer',
                      transition: 'background-color 100ms ease',
                    }}
                    onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = 'var(--bg-hover)')}
                    onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = 'transparent')}
                  >
                    <td style={{ padding: '10px 16px', fontFamily: 'var(--font-mono)', fontWeight: 600, color: 'var(--text-primary)' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                        {d.has_prompt_threat && (
                          <span title="Adversarial threat quarantined">
                            <ShieldAlert size={12} color="#dc2626" />
                          </span>
                        )}
                        <span>{d.dispute_id}</span>
                      </div>
                    </td>
                    <td style={{ padding: '10px 16px' }}>
                      {isReal ? (
                        <span
                          style={{
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '4px',
                            padding: '2px 7px',
                            borderRadius: '4px',
                            fontSize: '10.5px',
                            fontWeight: 600,
                            backgroundColor: '#ecfdf5',
                            color: '#065f46',
                            border: '1px solid #a7f3d0',
                          }}
                        >
                          <span style={{ width: '5px', height: '5px', borderRadius: '50%', backgroundColor: '#059669' }} />
                          Live Sandbox
                        </span>
                      ) : (
                        <span className="badge badge-neutral">Benchmark</span>
                      )}
                    </td>
                    <td style={{ padding: '10px 16px', color: 'var(--text-secondary)' }}>
                      {reasonReadable}
                    </td>
                    <td style={{ padding: '10px 16px', textAlign: 'right', fontFamily: 'var(--font-mono)', fontWeight: 600 }}>
                      ${d.amount} <span style={{ fontSize: '10px', color: 'var(--text-muted)' }}>{d.currency}</span>
                    </td>
                    <td style={{ padding: '10px 16px' }}>
                      <span
                        style={{
                          fontSize: '11px',
                          fontWeight: 500,
                          color: d.status === 'WAITING_FOR_SELLER_RESPONSE' ? 'var(--signal-blue)' : 'var(--text-secondary)',
                        }}
                      >
                        {d.status === 'WAITING_FOR_SELLER_RESPONSE' ? 'Waiting Response' : d.status}
                      </span>
                    </td>
                    <td style={{ padding: '10px 16px', textAlign: 'center' }}>
                      <span
                        className={`badge ${
                          d.overall_decision === 'ALLOW'
                            ? 'badge-allow'
                            : d.overall_decision === 'BLOCK'
                            ? 'badge-block'
                            : 'badge-review'
                        }`}
                      >
                        {d.overall_decision === 'ALLOW' && <CheckCircle2 size={11} />}
                        {d.overall_decision === 'BLOCK' && <XCircle size={11} />}
                        {d.overall_decision === 'REVIEW' && <AlertTriangle size={11} />}
                        {d.overall_decision}
                      </span>
                    </td>
                    <td style={{ padding: '10px 16px', textAlign: 'right' }}>
                      <button
                        className="btn btn-secondary"
                        style={{ padding: '2px 6px', fontSize: '10.5px', height: '22px' }}
                      >
                        Inspect
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
