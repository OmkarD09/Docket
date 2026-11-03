import React, { useState, useEffect } from 'react';
import { RefreshCw, Clock, ArrowDown, CheckCircle2, AlertOctagon } from 'lucide-react';
import type { AuditEventItem } from '../types';

export const AuditTrailView: React.FC = () => {
  const [events, setEvents] = useState<AuditEventItem[]>([]);
  const [chainIntact, setChainIntact] = useState<boolean>(true);
  const [loading, setLoading] = useState<boolean>(true);

  const fetchAuditTrail = async () => {
    setLoading(true);
    try {
      const resp = await fetch('/api/audit-trail');
      if (resp.ok) {
        const data = await resp.json();
        setEvents(data.events || []);
        setChainIntact(data.chain_intact);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAuditTrail();
  }, []);

  return (
    <div className="page-scrollable">
      {/* Header Banner */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <h2 style={{ fontSize: '18px', fontWeight: 700, color: 'var(--text-primary)', letterSpacing: '-0.02em' }}>
            Append-Only Cryptographic Audit Ledger
          </h2>
          <div style={{ fontSize: '13px', color: 'var(--text-muted)', marginTop: '4px' }}>
            Deterministic SHA-256 parent-hash chaining immutably logs every dispute ingestion, policy assessment, authorization record, and API submission.
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <div
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              padding: '5px 12px',
              borderRadius: '6px',
              fontSize: '12px',
              fontWeight: 600,
              backgroundColor: chainIntact ? 'var(--status-allow-bg)' : 'var(--status-block-bg)',
              color: chainIntact ? 'var(--status-allow-text)' : 'var(--status-block-text)',
              border: `1px solid ${chainIntact ? 'var(--status-allow-border)' : 'var(--status-block-border)'}`,
            }}
          >
            {chainIntact ? <CheckCircle2 size={14} color="#059669" /> : <AlertOctagon size={14} color="#dc2626" />}
            <span>{chainIntact ? 'SHA-256 HASH CHAIN: 100% INTACT' : 'CHAIN INTEGRITY COMPROMISED'}</span>
          </div>

          <button className="btn btn-secondary" onClick={fetchAuditTrail} disabled={loading}>
            <RefreshCw size={13} className={loading ? 'spin' : ''} />
            <span>Refresh Ledger</span>
          </button>
        </div>
      </div>

      {/* Events List */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', maxWidth: '1000px' }}>
        {events.map((evt, idx) => (
          <div key={evt.event_id} style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <div
              style={{
                backgroundColor: 'var(--bg-surface)',
                border: '1px solid var(--border-subtle)',
                borderRadius: '8px',
                padding: '16px 20px',
                display: 'flex',
                flexDirection: 'column',
                gap: '10px',
                boxShadow: 'var(--shadow-sm)',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <span
                    style={{
                      fontSize: '11px',
                      fontWeight: 700,
                      padding: '3px 8px',
                      borderRadius: '4px',
                      backgroundColor: 'var(--bg-subtle)',
                      color: 'var(--text-primary)',
                      border: '1px solid var(--border-subtle)',
                      fontFamily: 'var(--font-mono)',
                    }}
                  >
                    {evt.event_type}
                  </span>
                  <span className="font-mono" style={{ fontWeight: 600, fontSize: '13px', color: 'var(--text-primary)' }}>
                    {evt.dispute_id}
                  </span>
                  <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                    Actor: <strong style={{ color: 'var(--text-secondary)' }}>{evt.actor}</strong>
                  </span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', color: 'var(--text-muted)' }}>
                  <Clock size={13} />
                  <span>{new Date(evt.timestamp).toLocaleString()}</span>
                </div>
              </div>

              {/* Hash Chain Signatures */}
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: '1fr 1fr',
                  gap: '12px',
                  backgroundColor: '#fafbfc',
                  border: '1px solid var(--border-subtle)',
                  padding: '8px 12px',
                  borderRadius: '5px',
                  fontSize: '11px',
                }}
              >
                <div>
                  <span style={{ color: 'var(--text-muted)' }}>Parent Hash: </span>
                  <span className="font-mono" style={{ color: evt.parent_hash === 'GENESIS' ? '#059669' : 'var(--text-secondary)' }}>
                    {evt.parent_hash}
                  </span>
                </div>
                <div>
                  <span style={{ color: 'var(--text-muted)' }}>Event Hash: </span>
                  <span className="font-mono" style={{ color: 'var(--accent-primary)', fontWeight: 600 }}>
                    {evt.event_hash}
                  </span>
                </div>
              </div>

              {/* Payload Excerpt */}
              {evt.payload && Object.keys(evt.payload).length > 0 && (
                <div style={{ fontSize: '11px', marginTop: '2px' }}>
                  <details className="code-details">
                    <summary style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
                      View Event Payload Data
                    </summary>
                    <pre className="code-block" style={{ marginTop: '6px' }}>
                      {JSON.stringify(evt.payload, null, 2)}
                    </pre>
                  </details>
                </div>
              )}
            </div>

            {idx < events.length - 1 && (
              <div style={{ display: 'flex', justifyContent: 'center' }}>
                <ArrowDown size={14} color="#94a3b8" />
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};
