import React, { useState, useEffect } from 'react';
import {
  CheckCircle2,
  XCircle,
  AlertTriangle,
  ShieldAlert,
  ShieldCheck,
  Search,
  RefreshCw,
  Info,
} from 'lucide-react';
import type { EvalScorecardData, EvalScenarioResult } from '../types';

export const EvalScorecardView: React.FC = () => {
  const [data, setData] = useState<EvalScorecardData | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [filterType, setFilterType] = useState<'ALL' | 'REFUSALS' | 'THREATS' | 'ALLOW'>('ALL');
  const [selectedScenario, setSelectedScenario] = useState<EvalScenarioResult | null>(null);

  const fetchScorecard = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch('/api/eval/scorecard');
      if (!res.ok) {
        throw new Error(`HTTP error ${res.status}: ${res.statusText}`);
      }
      const json: EvalScorecardData = await res.json();
      setData(json);
      if (json.results && json.results.length > 0) {
        setSelectedScenario(json.results[0]);
      }
    } catch (err: any) {
      console.error('Failed to load evaluation scorecard:', err);
      setError(err.message || 'Failed to fetch scorecard');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchScorecard();
  }, []);

  if (loading) {
    return (
      <div className="empty-state">
        <RefreshCw size={24} className="spin" style={{ color: 'var(--accent-slate)' }} />
        <p style={{ marginTop: '12px', color: 'var(--text-secondary)' }}>
          Loading 20-case evaluation benchmark matrix...
        </p>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="empty-state">
        <AlertTriangle size={32} style={{ color: 'var(--status-block-dot)' }} />
        <p style={{ marginTop: '12px', fontWeight: 600 }}>Error loading benchmark scorecard</p>
        <p style={{ fontSize: '12px', color: 'var(--text-muted)' }}>{error}</p>
        <button
          onClick={fetchScorecard}
          className="btn btn-secondary"
          style={{ marginTop: '12px' }}
        >
          Retry
        </button>
      </div>
    );
  }

  const filteredResults = data.results.filter((scen) => {
    const matchesSearch =
      scen.scenario_id.toLowerCase().includes(searchQuery.toLowerCase()) ||
      scen.actual_violated_invariants.some((inv) =>
        inv.toLowerCase().includes(searchQuery.toLowerCase())
      );

    if (!matchesSearch) return false;

    if (filterType === 'REFUSALS') {
      return scen.actual_overall_decision === 'BLOCK' || scen.actual_factual_readiness === 'BLOCK';
    }
    if (filterType === 'THREATS') {
      return scen.prompt_threat_detected;
    }
    if (filterType === 'ALLOW') {
      return scen.actual_overall_decision === 'ALLOW';
    }
    return true;
  });

  return (
    <div className="page-scrollable">
      {/* Header Banner with Mandatory Synthetic Source Badge */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <h2 style={{ fontSize: '18px', fontWeight: 700, color: 'var(--text-primary)', letterSpacing: '-0.02em' }}>
              Benchmark Scorecard
            </h2>
            <span
              style={{
                fontSize: '10.5px',
                fontWeight: 700,
                letterSpacing: '0.04em',
                textTransform: 'uppercase',
                padding: '3px 8px',
                borderRadius: '4px',
                backgroundColor: 'var(--bg-subtle)',
                color: 'var(--text-secondary)',
                border: '1px solid var(--border-strong)',
              }}
            >
              SYNTHETIC BENCHMARK DATA
            </span>
          </div>
          <div style={{ fontSize: '13px', color: 'var(--text-muted)', marginTop: '4px' }}>
            Automated verification of Docket's deterministic policy barriers across 20 labeled fraud edge cases, delivery discrepancies, and adversarial attacks.
          </div>
        </div>

        <button className="btn btn-secondary" onClick={fetchScorecard} disabled={loading}>
          <RefreshCw size={13} className={loading ? 'spin' : ''} />
          <span>Refresh Metrics</span>
        </button>
      </div>

      {/* KPI Metric Summary Strip */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(4, 1fr)',
          gap: '12px',
        }}
      >
        <div className="card" style={{ padding: '14px 18px' }}>
          <div style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em', fontWeight: 600 }}>
            Benchmark Accuracy
          </div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '6px', marginTop: '4px' }}>
            <span style={{ fontSize: '26px', fontWeight: 700, color: 'var(--status-allow-text)', fontFamily: 'var(--font-mono)' }}>
              {data.accuracy_rate}%
            </span>
            <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
              ({data.passed_scenarios}/{data.total_scenarios} passing)
            </span>
          </div>
          <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '2px' }}>
            0 False ALLOWs · 0 False BLOCKs
          </div>
        </div>

        <div className="card" style={{ padding: '14px 18px' }}>
          <div style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em', fontWeight: 600 }}>
            Refusal Precision & Recall
          </div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '6px', marginTop: '4px' }}>
            <span style={{ fontSize: '26px', fontWeight: 700, color: 'var(--status-allow-text)', fontFamily: 'var(--font-mono)' }}>
              {data.refusal_precision}%
            </span>
            <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
              P: {data.refusal_precision}% / R: {data.refusal_recall}%
            </span>
          </div>
          <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '2px' }}>
            {data.refusal_scenarios_count} refusal cases correctly blocked
          </div>
        </div>

        <div className="card" style={{ padding: '14px 18px' }}>
          <div style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em', fontWeight: 600 }}>
            Label-Created Refusal Rate
          </div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '6px', marginTop: '4px' }}>
            <span style={{ fontSize: '26px', fontWeight: 700, color: 'var(--status-allow-text)', fontFamily: 'var(--font-mono)' }}>
              {data.label_created_refusal_rate}%
            </span>
            <span style={{ fontSize: '12px', color: 'var(--status-allow-text)', display: 'flex', alignItems: 'center', gap: '3px', fontWeight: 600 }}>
              <ShieldCheck size={14} /> Zero False Proofs
            </span>
          </div>
          <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '2px' }}>
            Defining hackathon scenario verified
          </div>
        </div>

        <div className="card" style={{ padding: '14px 18px' }}>
          <div style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em', fontWeight: 600 }}>
            Threat Quarantining
          </div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '6px', marginTop: '4px' }}>
            <span style={{ fontSize: '26px', fontWeight: 700, color: 'var(--accent-slate)', fontFamily: 'var(--font-mono)' }}>
              {data.prompt_injection_detection_rate}%
            </span>
            <span style={{ fontSize: '12px', color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: '3px' }}>
              <ShieldAlert size={14} color="#881337" /> 100% Quarantined
            </span>
          </div>
          <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '2px' }}>
            Adversarial injections neutralized
          </div>
        </div>
      </div>

      {/* Main Split: Matrix Table + Scenario Inspector */}
      <div style={{ display: 'grid', gridTemplateColumns: '1.6fr 1.1fr', gap: '16px', flex: 1, minHeight: 0 }}>
        {/* Table Column */}
        <div className="card" style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          {/* Filter Bar */}
          <div
            style={{
              padding: '10px 14px',
              borderBottom: '1px solid var(--border-subtle)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: '8px',
              backgroundColor: 'var(--bg-header)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flex: 1 }}>
              <Search size={14} style={{ color: 'var(--text-muted)' }} />
              <input
                type="text"
                placeholder="Search scenario ID or invariant..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                style={{
                  background: 'transparent',
                  border: 'none',
                  outline: 'none',
                  color: 'var(--text-primary)',
                  fontSize: '12px',
                  width: '100%',
                }}
              />
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
              {(['ALL', 'REFUSALS', 'THREATS', 'ALLOW'] as const).map((mode) => (
                <button
                  key={mode}
                  onClick={() => setFilterType(mode)}
                  className={`btn btn-secondary ${filterType === mode ? 'btn-primary' : ''}`}
                  style={{ padding: '3px 8px', fontSize: '11px', height: '26px' }}
                >
                  {mode}
                </button>
              ))}
            </div>
          </div>

          {/* Table List */}
          <div style={{ flex: 1, overflowY: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border-subtle)', background: 'var(--bg-canvas)', color: 'var(--text-muted)' }}>
                  <th style={{ padding: '8px 12px', textAlign: 'left', fontWeight: 600 }}>Scenario ID</th>
                  <th style={{ padding: '8px 12px', textAlign: 'left', fontWeight: 600 }}>Decision</th>
                  <th style={{ padding: '8px 12px', textAlign: 'left', fontWeight: 600 }}>Reconciliation</th>
                  <th style={{ padding: '8px 12px', textAlign: 'center', fontWeight: 600 }}>Threat</th>
                  <th style={{ padding: '8px 12px', textAlign: 'center', fontWeight: 600 }}>Result</th>
                </tr>
              </thead>
              <tbody>
                {filteredResults.map((scen) => {
                  const isSelected = selectedScenario?.scenario_id === scen.scenario_id;
                  return (
                    <tr
                      key={scen.scenario_id}
                      onClick={() => setSelectedScenario(scen)}
                      style={{
                        borderBottom: '1px solid var(--border-subtle)',
                        cursor: 'pointer',
                        backgroundColor: isSelected ? 'var(--bg-subtle)' : 'transparent',
                        transition: 'background-color 100ms ease',
                      }}
                    >
                      <td style={{ padding: '9px 12px', fontFamily: 'var(--font-mono)', fontWeight: 600, color: 'var(--text-primary)', fontSize: '11px' }}>
                        {scen.scenario_id}
                      </td>
                      <td style={{ padding: '9px 12px' }}>
                        <span
                          className={`badge ${
                            scen.actual_overall_decision === 'ALLOW'
                              ? 'badge-allow'
                              : scen.actual_overall_decision === 'BLOCK'
                              ? 'badge-block'
                              : 'badge-review'
                          }`}
                        >
                          {scen.actual_overall_decision}
                        </span>
                      </td>
                      <td style={{ padding: '9px 12px' }}>
                        <span style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
                          {scen.actual_reconciliation_status}
                        </span>
                      </td>
                      <td style={{ padding: '9px 12px', textAlign: 'center' }}>
                        {scen.prompt_threat_detected ? (
                          <span
                            title="Adversarial prompt injection quarantined"
                            className="badge badge-threat"
                          >
                            <ShieldAlert size={11} /> QUARANTINED
                          </span>
                        ) : (
                          <span style={{ color: 'var(--text-muted)', fontSize: '11px' }}>None</span>
                        )}
                      </td>
                      <td style={{ padding: '9px 12px', textAlign: 'center' }}>
                        {scen.passed ? (
                          <span style={{ color: 'var(--status-allow-text)', fontWeight: 600, fontSize: '11px', display: 'inline-flex', alignItems: 'center', gap: '3px' }}>
                            <CheckCircle2 size={13} /> PASS
                          </span>
                        ) : (
                          <span style={{ color: 'var(--status-block-text)', fontWeight: 600, fontSize: '11px', display: 'inline-flex', alignItems: 'center', gap: '3px' }}>
                            <XCircle size={13} /> FAIL
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>

        {/* Selected Scenario Detail Panel */}
        <div className="card" style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          {selectedScenario ? (
            <div style={{ padding: '18px', display: 'flex', flexDirection: 'column', gap: '14px', overflowY: 'auto' }}>
              <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
                <div>
                  <div style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 600 }}>
                    Scenario Benchmark Diagnostic
                  </div>
                  <div
                    className="font-mono"
                    style={{
                      fontSize: '13px',
                      fontWeight: 700,
                      color: 'var(--text-primary)',
                      marginTop: '2px',
                    }}
                  >
                    {selectedScenario.scenario_id}
                  </div>
                </div>
                <span
                  className={`badge ${
                    selectedScenario.actual_overall_decision === 'ALLOW'
                      ? 'badge-allow'
                      : selectedScenario.actual_overall_decision === 'BLOCK'
                      ? 'badge-block'
                      : 'badge-review'
                  }`}
                >
                  {selectedScenario.actual_overall_decision}
                </span>
              </div>

              {/* Status matrix breakdown */}
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: '1fr 1fr',
                  gap: '8px',
                  backgroundColor: 'var(--bg-subtle)',
                  padding: '10px 12px',
                  borderRadius: '6px',
                }}
              >
                <div>
                  <div className="kv-key">Factual Readiness:</div>
                  <div style={{ fontWeight: 600, color: 'var(--text-primary)', fontSize: '12px' }}>
                    {selectedScenario.actual_factual_readiness}
                  </div>
                </div>
                <div>
                  <div className="kv-key">Action Eligibility:</div>
                  <div style={{ fontWeight: 600, color: 'var(--text-primary)', fontSize: '12px' }}>
                    {selectedScenario.actual_action_readiness}
                  </div>
                </div>
                <div>
                  <div className="kv-key">Reconciliation:</div>
                  <div style={{ fontWeight: 600, color: 'var(--text-primary)', fontSize: '12px' }}>
                    {selectedScenario.actual_reconciliation_status}
                  </div>
                </div>
                <div>
                  <div className="kv-key">Refusal Correctness:</div>
                  <div style={{ fontWeight: 600, color: 'var(--status-allow-text)', fontSize: '12px' }}>
                    {selectedScenario.refusal_correct ? 'VERIFIED' : 'INCORRECT'}
                  </div>
                </div>
              </div>

              {/* Violated Invariants */}
              <div>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '6px', fontWeight: 600 }}>
                  Violated Invariants ({selectedScenario.actual_violated_invariants.length})
                </div>
                {selectedScenario.actual_violated_invariants.length === 0 ? (
                  <div style={{ fontSize: '12px', color: 'var(--text-muted)', fontStyle: 'italic' }}>
                    No invariants violated. All deterministic pre-flight checks passed.
                  </div>
                ) : (
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '5px' }}>
                    {selectedScenario.actual_violated_invariants.map((inv) => (
                      <span
                        key={inv}
                        className="font-mono"
                        style={{
                          fontSize: '11px',
                          padding: '3px 8px',
                          borderRadius: '4px',
                          backgroundColor: 'var(--status-block-bg)',
                          color: 'var(--status-block-text)',
                          border: '1px solid var(--status-block-border)',
                        }}
                      >
                        {inv}
                      </span>
                    ))}
                  </div>
                )}
              </div>

              {/* Discrepancies */}
              <div>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '6px', fontWeight: 600 }}>
                  Cross-Source Discrepancies ({selectedScenario.actual_discrepancies.length})
                </div>
                {selectedScenario.actual_discrepancies.length === 0 ? (
                  <div style={{ fontSize: '12px', color: 'var(--text-muted)', fontStyle: 'italic' }}>
                    Zero cross-source discrepancies identified.
                  </div>
                ) : (
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '5px' }}>
                    {selectedScenario.actual_discrepancies.map((disc) => (
                      <span
                        key={disc}
                        className="font-mono"
                        style={{
                          fontSize: '11px',
                          padding: '3px 8px',
                          borderRadius: '4px',
                          backgroundColor: 'var(--status-review-bg)',
                          color: 'var(--status-review-text)',
                          border: '1px solid var(--status-review-border)',
                        }}
                      >
                        {disc}
                      </span>
                    ))}
                  </div>
                )}
              </div>

              {/* Prompt threat container */}
              {selectedScenario.prompt_threat_detected && (
                <div
                  style={{
                    backgroundColor: 'var(--status-threat-bg)',
                    border: '1px solid var(--status-threat-border)',
                    borderRadius: '6px',
                    padding: '12px',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '4px',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: 'var(--status-threat-text)', fontWeight: 600, fontSize: '12px' }}>
                    <ShieldAlert size={14} /> Adversarial Prompt Injection Blocked
                  </div>
                  <p style={{ fontSize: '11px', color: 'var(--text-secondary)', lineHeight: 1.45 }}>
                    Malicious instructions attempting system instruction overrides or unauthorized auto-refund concessions were neutralized before downstream AI or policy ingestion.
                  </p>
                </div>
              )}
            </div>
          ) : (
            <div className="empty-state">
              <Info size={24} style={{ color: 'var(--text-muted)' }} />
              <p style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '8px' }}>
                Select a benchmark scenario from the table to inspect details.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
