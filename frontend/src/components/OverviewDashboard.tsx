import React, { useMemo, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  XCircle,
  ArrowRight,
  PieChart,
  BarChart,
  Activity,
  ShieldAlert,
  Filter,
} from 'lucide-react';
import type { DisputeSummary } from '../types';

export type DataScope = 'ALL' | 'REAL_SANDBOX' | 'SYNTHETIC_BENCHMARK';

interface OverviewDashboardProps {
  disputes: DisputeSummary[];
  onNavigateToDisputes: (disputeId?: string) => void;
}

export const OverviewDashboard: React.FC<OverviewDashboardProps> = ({
  disputes,
  onNavigateToDisputes,
}) => {
  const [dataScope, setDataScope] = useState<DataScope>('ALL');

  // Filter disputes according to active data scope
  const filteredDisputes = useMemo(() => {
    if (dataScope === 'REAL_SANDBOX') {
      return disputes.filter(
        (d) => d.dispute_id === 'PP-R-NKI-10193390' || (d.scenario_id && d.scenario_id.includes('REAL_SANDBOX'))
      );
    }
    if (dataScope === 'SYNTHETIC_BENCHMARK') {
      return disputes.filter(
        (d) => d.dispute_id !== 'PP-R-NKI-10193390' && (!d.scenario_id || !d.scenario_id.includes('REAL_SANDBOX'))
      );
    }
    return disputes;
  }, [disputes, dataScope]);

  // 1. Operational KPI calculations
  const kpis = useMemo(() => {
    const total = disputes.length;
    const realDisputes = disputes.filter(
      (d) => d.dispute_id === 'PP-R-NKI-10193390' || (d.scenario_id && d.scenario_id.includes('REAL_SANDBOX'))
    );
    const benchmarkCount = total - realDisputes.length;

    const scopedTotal = filteredDisputes.length;
    const waitingSellerAction = filteredDisputes.filter(
      (d) => d.status === 'WAITING_FOR_SELLER_RESPONSE'
    ).length;

    const reviewRequired = filteredDisputes.filter(
      (d) => d.overall_decision === 'REVIEW'
    ).length;

    const policyBlocked = filteredDisputes.filter(
      (d) => d.overall_decision === 'BLOCK'
    ).length;

    const readyToSubmit = filteredDisputes.filter(
      (d) => d.is_ready_for_submission
    ).length;

    return {
      total,
      realCount: realDisputes.length,
      benchmarkCount,
      scopedTotal,
      waitingSellerAction,
      reviewRequired,
      policyBlocked,
      readyToSubmit,
    };
  }, [disputes, filteredDisputes]);

  // 2. Chart Data: Dispute Statuses
  const statusDistribution = useMemo(() => {
    const map: Record<string, number> = {};
    filteredDisputes.forEach((d) => {
      const s = d.status || 'UNKNOWN';
      map[s] = (map[s] || 0) + 1;
    });
    return Object.entries(map).map(([status, count]) => ({
      status: status.replace(/_/g, ' ').toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase()),
      rawStatus: status,
      count,
      pct: ((count / (filteredDisputes.length || 1)) * 100).toFixed(1),
    }));
  }, [filteredDisputes]);

  // 3. Chart Data: Policy Decisions
  const decisionDistribution = useMemo(() => {
    const allowCount = filteredDisputes.filter((d) => d.overall_decision === 'ALLOW').length;
    const reviewCount = filteredDisputes.filter((d) => d.overall_decision === 'REVIEW').length;
    const blockCount = filteredDisputes.filter((d) => d.overall_decision === 'BLOCK').length;
    const total = filteredDisputes.length || 1;

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
  }, [filteredDisputes]);

  // 4. Chart Data: Dispute Reasons
  const reasonDistribution = useMemo(() => {
    const map: Record<string, number> = {};
    filteredDisputes.forEach((d) => {
      const r = d.reason || 'OTHER';
      map[r] = (map[r] || 0) + 1;
    });
    return Object.entries(map)
      .map(([reason, count]) => ({
        reason: reason.replace(/_/g, ' ').toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase()),
        rawReason: reason,
        count,
        pct: ((count / (filteredDisputes.length || 1)) * 100).toFixed(0),
      }))
      .sort((a, b) => b.count - a.count);
  }, [filteredDisputes]);

  // 5. Recent Disputes (First 6 items of scoped set)
  const recentDisputes = useMemo(() => {
    return filteredDisputes.slice(0, 6);
  }, [filteredDisputes]);

  return (
    <div className="page-scrollable">
      {/* Section A: Operational Context Bar */}
      <div className="operational-header">
        <div>
          <div className="operational-title">
            Dispute Operations & Telemetry
          </div>
          <div className="operational-subtitle">
            Cross-source evidence reconciliation, deterministic policy enforcement, and live PayPal dispute settlement tracking.
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <button
            onClick={() => onNavigateToDisputes('PP-R-NKI-10193390')}
            className="btn btn-secondary"
            style={{ height: '30px', padding: '4px 10px', fontSize: '11.5px', gap: '6px' }}
            title="Inspect active Live Sandbox dispute"
          >
            <span style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: '#059669' }} />
            <span>Open Live Sandbox Case</span>
            <ArrowRight size={12} />
          </button>
        </div>
      </div>

      {/* Scope Selector Control (Priority 4) */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: '14px',
          padding: '8px 12px',
          backgroundColor: 'var(--bg-subtle)',
          borderRadius: '6px',
          border: '1px solid var(--border-subtle)',
          flexWrap: 'wrap',
          gap: '8px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em', display: 'flex', alignItems: 'center', gap: '4px' }}>
            <Filter size={11} /> Data Scope:
          </span>
          <div style={{ display: 'flex', gap: '4px' }}>
            <button
              onClick={() => setDataScope('ALL')}
              className={`btn ${dataScope === 'ALL' ? 'btn-primary' : 'btn-secondary'}`}
              style={{ padding: '3px 9px', fontSize: '11px', height: '26px' }}
            >
              All Records ({kpis.total})
            </button>
            <button
              onClick={() => setDataScope('REAL_SANDBOX')}
              className={`btn ${dataScope === 'REAL_SANDBOX' ? 'btn-primary' : 'btn-secondary'}`}
              style={{ padding: '3px 9px', fontSize: '11px', height: '26px', display: 'flex', alignItems: 'center', gap: '5px' }}
            >
              <span style={{ width: '5px', height: '5px', borderRadius: '50%', backgroundColor: dataScope === 'REAL_SANDBOX' ? '#fff' : '#059669' }} />
              Live Sandbox ({kpis.realCount})
            </button>
            <button
              onClick={() => setDataScope('SYNTHETIC_BENCHMARK')}
              className={`btn ${dataScope === 'SYNTHETIC_BENCHMARK' ? 'btn-primary' : 'btn-secondary'}`}
              style={{ padding: '3px 9px', fontSize: '11px', height: '26px' }}
            >
              Synthetic Benchmarks ({kpis.benchmarkCount})
            </button>
          </div>
        </div>
        <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
          {dataScope === 'ALL' && 'Scope: 1 live sandbox dispute + 19 synthetic test benchmark fixtures.'}
          {dataScope === 'REAL_SANDBOX' && 'Scope: 1 authentic dispute from PayPal Sandbox API (PP-R-NKI-10193390).'}
          {dataScope === 'SYNTHETIC_BENCHMARK' && 'Scope: 19 offline benchmark test fixtures. Synthetic cases are not actual merchant action items.'}
        </div>
      </div>

      {/* Section B: Operational KPI Strip */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(4, 1fr)',
          gap: '12px',
        }}
      >
        <div className="card" style={{ padding: '12px 16px', display: 'flex', flexDirection: 'column', gap: '2px' }}>
          <div style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em', fontWeight: 600 }}>
            {dataScope === 'REAL_SANDBOX' ? 'Live Disputes' : dataScope === 'SYNTHETIC_BENCHMARK' ? 'Benchmark Cases' : 'Total Records Tracked'}
          </div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '6px', marginTop: '2px' }}>
            <span className="font-mono" style={{ fontSize: '24px', fontWeight: 700, color: 'var(--text-primary)', letterSpacing: '-0.02em' }}>
              {kpis.scopedTotal}
            </span>
          </div>
          <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '2px', display: 'flex', alignItems: 'center', gap: '5px' }}>
            {dataScope === 'ALL' ? (
              <>
                <span style={{ width: '5px', height: '5px', borderRadius: '50%', backgroundColor: '#059669' }} />
                <span>{kpis.realCount} Live Sandbox · {kpis.benchmarkCount} Benchmarks</span>
              </>
            ) : dataScope === 'REAL_SANDBOX' ? (
              <span>Genuine PayPal Sandbox record</span>
            ) : (
              <span>Offline evaluation benchmark fixtures</span>
            )}
          </div>
        </div>

        <div className="card" style={{ padding: '12px 16px', display: 'flex', flexDirection: 'column', gap: '2px' }}>
          <div style={{ fontSize: '11px', color: 'var(--signal-blue)', textTransform: 'uppercase', letterSpacing: '0.04em', fontWeight: 600 }}>
            {dataScope === 'SYNTHETIC_BENCHMARK' ? 'Benchmark Inquiries' : 'Awaiting Seller Action'}
          </div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '6px', marginTop: '2px' }}>
            <span className="font-mono" style={{ fontSize: '24px', fontWeight: 700, color: 'var(--signal-blue)', letterSpacing: '-0.02em' }}>
              {kpis.waitingSellerAction}
            </span>
          </div>
          <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '2px' }}>
            {dataScope === 'ALL' ? '1 Live Sandbox (Overdue) · 17 Benchmarks' : dataScope === 'REAL_SANDBOX' ? 'Response deadline lapsed (Nov 07, 2026)' : 'Simulated inquiry cases awaiting test action'}
          </div>
        </div>

        <div className="card" style={{ padding: '12px 16px', display: 'flex', flexDirection: 'column', gap: '2px' }}>
          <div style={{ fontSize: '11px', color: 'var(--status-review-text)', textTransform: 'uppercase', letterSpacing: '0.04em', fontWeight: 600 }}>
            {dataScope === 'SYNTHETIC_BENCHMARK' ? 'Benchmark Reviews' : 'Evidence Review Required'}
          </div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '6px', marginTop: '2px' }}>
            <span className="font-mono" style={{ fontSize: '24px', fontWeight: 700, color: 'var(--status-review-text)', letterSpacing: '-0.02em' }}>
              {kpis.reviewRequired}
            </span>
          </div>
          <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '2px' }}>
            {dataScope === 'REAL_SANDBOX' ? '0 live disputes require manual review' : 'High-value or signature threshold cases'}
          </div>
        </div>

        <div className="card" style={{ padding: '12px 16px', display: 'flex', flexDirection: 'column', gap: '2px' }}>
          <div style={{ fontSize: '11px', color: 'var(--status-block-text)', textTransform: 'uppercase', letterSpacing: '0.04em', fontWeight: 600 }}>
            {dataScope === 'SYNTHETIC_BENCHMARK' ? 'Benchmark Refusals' : 'Policy-Blocked Claims'}
          </div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '6px', marginTop: '2px' }}>
            <span className="font-mono" style={{ fontSize: '24px', fontWeight: 700, color: 'var(--status-block-text)', letterSpacing: '-0.02em' }}>
              {kpis.policyBlocked}
            </span>
          </div>
          <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '2px' }}>
            {dataScope === 'REAL_SANDBOX' ? '0 live disputes blocked by invariants' : 'Label-created & delivery gaps refused'}
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
                      backgroundColor: 'var(--bg-surface)',
                      border: '1px solid var(--border-subtle)',
                      boxShadow: 'var(--shadow-xs)',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '5px', fontSize: '11px', fontWeight: 600, color: 'var(--text-primary)' }}>
                        <span style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: item.color }} />
                        <span>{item.decision}</span>
                      </div>
                      <span
                        style={{
                          fontSize: '10px',
                          fontWeight: 600,
                          padding: '1px 5px',
                          borderRadius: '3px',
                          backgroundColor: item.bg,
                          color: item.text,
                          border: `1px solid ${item.border}`,
                          fontFamily: 'var(--font-mono)',
                        }}
                      >
                        {item.pct}%
                      </span>
                    </div>
                    <div style={{ fontSize: '18px', fontWeight: 700, color: 'var(--text-primary)', marginTop: '4px', fontFamily: 'var(--font-mono)', letterSpacing: '-0.02em' }}>
                      {item.count} <span style={{ fontSize: '11px', fontWeight: 500, color: 'var(--text-muted)' }}>cases</span>
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
              <tr style={{ borderBottom: '1px solid var(--border-subtle)', backgroundColor: 'var(--bg-header)', color: 'var(--text-secondary)' }}>
                <th style={{ padding: '8px 14px', textAlign: 'left', fontWeight: 600, fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.04em' }}>Dispute Reference</th>
                <th style={{ padding: '8px 14px', textAlign: 'left', fontWeight: 600, fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.04em' }}>Origin</th>
                <th style={{ padding: '8px 14px', textAlign: 'left', fontWeight: 600, fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.04em' }}>Dispute Reason</th>
                <th style={{ padding: '8px 14px', textAlign: 'right', fontWeight: 600, fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.04em' }}>Amount</th>
                <th style={{ padding: '8px 14px', textAlign: 'left', fontWeight: 600, fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.04em' }}>PayPal Status</th>
                <th style={{ padding: '8px 14px', textAlign: 'center', fontWeight: 600, fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.04em' }}>Docket Decision</th>
                <th style={{ padding: '8px 14px', textAlign: 'right', fontWeight: 600, fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.04em' }}>Action</th>
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
                      borderBottom: '1px solid var(--border-light)',
                      cursor: 'pointer',
                      transition: 'background-color 100ms ease',
                      height: '38px',
                    }}
                    onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = 'var(--bg-hover)')}
                    onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = 'transparent')}
                  >
                    <td style={{ padding: '7px 14px', fontFamily: 'var(--font-mono)', fontWeight: 600, color: 'var(--text-primary)', fontSize: '11.5px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                        {d.has_prompt_threat && (
                          <span title="Adversarial threat quarantined">
                            <ShieldAlert size={12} color="#dc2626" />
                          </span>
                        )}
                        <span>{d.dispute_id}</span>
                      </div>
                    </td>
                    <td style={{ padding: '7px 14px' }}>
                      {isReal ? (
                        <span
                          style={{
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '4px',
                            padding: '1px 6px',
                            borderRadius: '3px',
                            fontSize: '10.5px',
                            fontWeight: 600,
                            backgroundColor: 'var(--status-allow-bg)',
                            color: 'var(--status-allow-text)',
                            border: '1px solid var(--status-allow-border)',
                          }}
                        >
                          <span style={{ width: '5px', height: '5px', borderRadius: '50%', backgroundColor: '#059669' }} />
                          Live Sandbox
                        </span>
                      ) : (
                        <span className="badge badge-neutral" style={{ padding: '1px 6px', fontSize: '10.5px' }}>
                          Benchmark
                        </span>
                      )}
                    </td>
                    <td style={{ padding: '7px 14px', color: 'var(--text-secondary)', fontSize: '11.5px' }}>
                      {reasonReadable}
                    </td>
                    <td style={{ padding: '7px 14px', textAlign: 'right', fontFamily: 'var(--font-mono)', fontWeight: 600, fontSize: '12px' }}>
                      ${d.amount} <span style={{ fontSize: '10px', color: 'var(--text-muted)' }}>{d.currency}</span>
                    </td>
                    <td style={{ padding: '7px 14px' }}>
                      <span
                        style={{
                          fontSize: '10.5px',
                          fontWeight: 500,
                          padding: '1px 6px',
                          borderRadius: '3px',
                          backgroundColor: d.status === 'WAITING_FOR_SELLER_RESPONSE' ? '#f0f9ff' : 'var(--bg-subtle)',
                          color: d.status === 'WAITING_FOR_SELLER_RESPONSE' ? 'var(--signal-blue)' : 'var(--text-secondary)',
                          border: `1px solid ${d.status === 'WAITING_FOR_SELLER_RESPONSE' ? 'var(--signal-blue-border)' : 'var(--border-subtle)'}`,
                        }}
                      >
                        {d.status === 'WAITING_FOR_SELLER_RESPONSE' ? 'Waiting Response' : d.status}
                      </span>
                    </td>
                    <td style={{ padding: '7px 14px', textAlign: 'center' }}>
                      <span
                        className={`badge ${
                          d.overall_decision === 'ALLOW'
                            ? 'badge-allow'
                            : d.overall_decision === 'BLOCK'
                            ? 'badge-block'
                            : 'badge-review'
                        }`}
                        style={{ fontSize: '10.5px', padding: '1px 6px' }}
                      >
                        {d.overall_decision === 'ALLOW' && <CheckCircle2 size={10} />}
                        {d.overall_decision === 'BLOCK' && <XCircle size={10} />}
                        {d.overall_decision === 'REVIEW' && <AlertTriangle size={10} />}
                        {d.overall_decision}
                      </span>
                    </td>
                    <td style={{ padding: '7px 14px', textAlign: 'right' }}>
                      <button
                        className="btn btn-secondary"
                        style={{ padding: '2px 8px', fontSize: '10.5px', height: '22px' }}
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
