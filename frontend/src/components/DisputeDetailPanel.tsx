import React, { useState, useEffect } from 'react';
import {
  ShieldAlert,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Truck,
  Package,
  Clock,
  Lock,
  Send,
  RefreshCw,
  Copy,
  Check,
} from 'lucide-react';
import type { DisputeDetail } from '../types';

interface DisputeDetailPanelProps {
  disputeId: string | null;
  onRefresh: () => void;
}

export const DisputeDetailPanel: React.FC<DisputeDetailPanelProps> = ({
  disputeId,
  onRefresh,
}) => {
  const [detail, setDetail] = useState<DisputeDetail | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [actionLoading, setActionLoading] = useState<boolean>(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<boolean>(false);

  useEffect(() => {
    if (!disputeId) {
      setDetail(null);
      return;
    }
    fetchDetail(disputeId);
  }, [disputeId]);

  const fetchDetail = async (id: string) => {
    setLoading(true);
    setActionError(null);
    setActionSuccess(null);
    try {
      const resp = await fetch(`/api/disputes/${id}`);
      if (resp.ok) {
        const data = await resp.json();
        setDetail(data);
      } else {
        setActionError(`Failed to load case: HTTP ${resp.status}`);
      }
    } catch (err: any) {
      setActionError(err.message || 'Error fetching case details');
    } finally {
      setLoading(false);
    }
  };

  const handleGenerateTicket = async () => {
    if (!disputeId) return;
    setActionLoading(true);
    setActionError(null);
    try {
      const resp = await fetch(`/api/disputes/${disputeId}/ticket`, { method: 'POST' });
      if (!resp.ok) {
        const err = await resp.json();
        throw new Error(err.detail || 'Ticket generation failed');
      }
      await fetchDetail(disputeId);
      setActionSuccess('Cryptographic approval ticket generated with 24-hour TTL.');
    } catch (err: any) {
      setActionError(err.message);
    } finally {
      setActionLoading(false);
    }
  };

  const handleAuthorize = async (decision: 'APPROVE' | 'REJECT') => {
    if (!disputeId || !detail?.approval_request) return;
    setActionLoading(true);
    setActionError(null);
    try {
      const resp = await fetch(`/api/disputes/${disputeId}/authorize`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          approval_id: detail.approval_request.approval_id,
          decision: decision,
          token: detail.approval_request.token,
          merchant_user_id: 'merchant_ops_primary',
          rejection_reason: decision === 'REJECT' ? 'Rejected by merchant operations lead' : undefined,
        }),
      });

      if (!resp.ok) {
        const err = await resp.json();
        throw new Error(err.detail || 'Authorization failed');
      }

      await fetchDetail(disputeId);
      onRefresh();
      setActionSuccess(`Merchant authorization recorded: ${decision}`);
    } catch (err: any) {
      setActionError(err.message);
    } finally {
      setActionLoading(false);
    }
  };

  const handleDispatch = async () => {
    if (!disputeId) return;
    setActionLoading(true);
    setActionError(null);
    try {
      const resp = await fetch(`/api/disputes/${disputeId}/dispatch`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          custom_notes: 'Docket Evidence Reconciliation Verified Package Delivery Proof',
        }),
      });

      if (!resp.ok) {
        const err = await resp.json();
        throw new Error(err.detail || 'Dispatch failed');
      }

      const resJson = await resp.json();
      await fetchDetail(disputeId);
      onRefresh();
      setActionSuccess(
        `Evidence successfully submitted to PayPal API! Status code: ${resJson.paypal_status_code || 200}`
      );
    } catch (err: any) {
      setActionError(err.message);
    } finally {
      setActionLoading(false);
    }
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(true);
    setTimeout(() => setCopiedId(false), 2000);
  };

  if (!disputeId) {
    return (
      <div className="empty-state" style={{ height: '100%' }}>
        <Package size={32} style={{ color: 'var(--text-tertiary)' }} />
        <p style={{ marginTop: '12px', fontWeight: 600, color: 'var(--text-secondary)' }}>
          No Dispute Selected
        </p>
        <p style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
          Select a dispute record from the table to inspect evidence and policy assessment.
        </p>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="empty-state" style={{ height: '100%' }}>
        <RefreshCw size={24} className="spin" style={{ color: 'var(--accent-primary)' }} />
        <p style={{ marginTop: '12px', color: 'var(--text-secondary)' }}>
          Retrieving cross-source evidence and policy state...
        </p>
      </div>
    );
  }

  if (!detail) {
    return (
      <div className="empty-state" style={{ height: '100%' }}>
        <AlertTriangle size={32} style={{ color: 'var(--status-block-dot)' }} />
        <p style={{ marginTop: '12px', color: 'var(--text-secondary)' }}>
          Dispute details unavailable.
        </p>
      </div>
    );
  }

  const { dispute, matched_order, matched_shipments, evaluation, approval_request, approval_record, dispatch_result, has_prompt_threat } = detail;
  const isReal = dispute?.dispute_id === 'PP-R-NKI-10193390';
  const overallDecision = evaluation?.overall_decision || 'REVIEW';
  const isReady = evaluation?.is_ready_for_submission || false;

  const reasonReadable = (dispute?.reason || '')
    .replace(/_/g, ' ')
    .toLowerCase()
    .replace(/\b\w/g, (c: string) => c.toUpperCase());

  return (
    <div className="detail-drawer">
      {/* 1. Header Overview Bar */}
      <div className="drawer-header">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span
              className="badge"
              style={{
                backgroundColor: isReal ? 'var(--status-allow-bg)' : 'var(--bg-subtle)',
                color: isReal ? 'var(--status-allow-text)' : 'var(--text-secondary)',
                border: `1px solid ${isReal ? 'var(--status-allow-border)' : 'var(--border-subtle)'}`,
              }}
            >
              {isReal ? 'Live PayPal Sandbox Dispute' : 'Synthetic Benchmark Scenario'}
            </span>
            {has_prompt_threat && (
              <span className="badge badge-threat" title="Adversarial prompt injection quarantined">
                <ShieldAlert size={12} /> Prompt Threat Quarantined
              </span>
            )}
          </div>

          <button
            onClick={() => fetchDetail(disputeId)}
            className="btn btn-secondary"
            style={{ padding: '3px 8px', fontSize: '11px', height: '26px' }}
            title="Refresh case state"
          >
            <RefreshCw size={12} /> Sync
          </button>
        </div>

        <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginTop: '4px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span className="font-mono" style={{ fontSize: '15px', fontWeight: 700, color: 'var(--text-primary)' }}>
              {dispute?.dispute_id}
            </span>
            <button
              onClick={() => copyToClipboard(dispute?.dispute_id)}
              style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-tertiary)' }}
              title="Copy Dispute ID"
            >
              {copiedId ? <Check size={13} color="#059669" /> : <Copy size={13} />}
            </button>
          </div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '4px' }}>
            <span className="font-mono" style={{ fontSize: '20px', fontWeight: 700, color: 'var(--text-primary)' }}>
              ${dispute?.dispute_amount?.value || '0.00'}
            </span>
            <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
              {dispute?.dispute_amount?.currency_code || 'USD'}
            </span>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '12px', color: 'var(--text-secondary)' }}>
          <span>{reasonReadable}</span>
          <span style={{ display: 'flex', alignItems: 'center', gap: '4px', color: 'var(--text-muted)', fontSize: '11px' }}>
            <Clock size={12} />
            Due: {dispute?.seller_response_due_date ? new Date(dispute.seller_response_due_date).toLocaleDateString() : 'Immediate Action Window'}
          </span>
        </div>
      </div>

      <div className="drawer-content">
        {/* Action Error / Success Notifications */}
        {actionError && (
          <div style={{ padding: '10px 14px', borderRadius: '6px', backgroundColor: 'var(--status-block-bg)', border: '1px solid var(--status-block-border)', color: 'var(--status-block-text)', fontSize: '12px' }}>
            <strong>Action Refused:</strong> {actionError}
          </div>
        )}
        {actionSuccess && (
          <div style={{ padding: '10px 14px', borderRadius: '6px', backgroundColor: 'var(--status-allow-bg)', border: '1px solid var(--status-allow-border)', color: 'var(--status-allow-text)', fontSize: '12px' }}>
            {actionSuccess}
          </div>
        )}

        {/* 2. Docket Policy Assessment Card (The Main Decision Anchor) */}
        <div
          className="panel-card"
          style={{
            borderLeft: `4px solid ${
              overallDecision === 'ALLOW'
                ? 'var(--status-allow-dot)'
                : overallDecision === 'BLOCK'
                ? 'var(--status-block-dot)'
                : 'var(--status-review-dot)'
            }`,
          }}
        >
          <div className="panel-card-header">
            <span className="panel-card-title">
              {overallDecision === 'ALLOW' && <CheckCircle2 size={14} color="var(--status-allow-dot)" />}
              {overallDecision === 'BLOCK' && <XCircle size={14} color="var(--status-block-dot)" />}
              {overallDecision === 'REVIEW' && <AlertTriangle size={14} color="var(--status-review-dot)" />}
              Docket Policy Assessment: {overallDecision}
            </span>
            <span
              className={`badge ${
                overallDecision === 'ALLOW'
                  ? 'badge-allow'
                  : overallDecision === 'BLOCK'
                  ? 'badge-block'
                  : 'badge-review'
              }`}
            >
              {overallDecision}
            </span>
          </div>

          <div className="panel-card-body">
            {/* Primary Explanation */}
            <div>
              <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)' }}>
                {evaluation?.summary || 'Policy evaluation completed.'}
              </div>
              <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '4px', lineHeight: 1.5 }}>
                {overallDecision === 'BLOCK' && (
                  <span>
                    Deterministic invariant checks prevented a false claim. Carrier delivery proof was not verified to the buyer's destination address.
                  </span>
                )}
                {overallDecision === 'ALLOW' && (
                  <span>
                    All required invariants passed. Verified carrier tracking establishes physical delivery to the recipient postal code matching the order.
                  </span>
                )}
                {overallDecision === 'REVIEW' && (
                  <span>
                    Discrepancy or advisory threshold identified. Merchant review is required before any counter-claim can be authorized.
                  </span>
                )}
              </div>
            </div>

            {/* Invariants & Rules Matrix */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', padding: '10px', backgroundColor: 'var(--bg-subtle)', borderRadius: '6px' }}>
              <div>
                <span className="kv-key">Factual Readiness</span>
                <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-primary)' }}>
                  {evaluation?.factual_readiness || 'N/A'}
                </div>
              </div>
              <div>
                <span className="kv-key">Action Eligibility</span>
                <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-primary)' }}>
                  {evaluation?.action_readiness || 'N/A'}
                </div>
              </div>
            </div>

            {/* Violated Invariants Chips */}
            {evaluation?.check_results && evaluation.check_results.some(c => c.decision === 'BLOCK' || c.decision === 'REVIEW') && (
              <div>
                <span className="kv-key" style={{ textTransform: 'uppercase' }}>Rule Findings & Invariants:</span>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginTop: '6px' }}>
                  {evaluation.check_results
                    .filter(c => c.decision !== 'ALLOW')
                    .map((check, idx) => (
                      <div
                        key={idx}
                        style={{
                          padding: '6px 10px',
                          borderRadius: '5px',
                          backgroundColor: check.decision === 'BLOCK' ? 'var(--status-block-bg)' : 'var(--status-review-bg)',
                          border: `1px solid ${check.decision === 'BLOCK' ? 'var(--status-block-border)' : 'var(--status-review-border)'}`,
                          fontSize: '11px',
                          width: '100%',
                        }}
                      >
                        <div style={{ fontWeight: 600, color: check.decision === 'BLOCK' ? 'var(--status-block-text)' : 'var(--status-review-text)' }}>
                          {check.rule_identifier}
                        </div>
                        <div style={{ color: 'var(--text-secondary)', marginTop: '2px', lineHeight: 1.4 }}>
                          {check.explanation}
                        </div>
                        {check.recommended_next_action && (
                          <div style={{ marginTop: '4px', fontStyle: 'italic', color: 'var(--text-muted)' }}>
                            Directive: {check.recommended_next_action}
                          </div>
                        )}
                      </div>
                    ))}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* 3. Evidence Provenance & Reconciliation (Evidence-First Hierarchy) */}
        <div className="panel-card">
          <div className="panel-card-header">
            <span className="panel-card-title">
              <Truck size={14} color="var(--accent-primary)" />
              Carrier Tracking & Delivery Provenance
            </span>
            <span className="badge badge-neutral">USPS / Carrier Signal</span>
          </div>

          <div className="panel-card-body">
            {matched_shipments && matched_shipments.length > 0 ? (
              matched_shipments.map((ship, idx) => (
                <div key={idx} style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  <div className="kv-grid">
                    <div className="kv-pair">
                      <span className="kv-key">Carrier</span>
                      <span className="kv-val">{ship.carrier_name}</span>
                    </div>
                    <div className="kv-pair">
                      <span className="kv-key">Tracking Status</span>
                      <span className="kv-val" style={{ color: ship.tracking_status === 'DELIVERED' ? 'var(--status-allow-text)' : 'var(--status-block-text)' }}>
                        {ship.tracking_status}
                      </span>
                    </div>
                    <div className="kv-pair">
                      <span className="kv-key">Tracking Number</span>
                      <span className="kv-val font-mono">{ship.tracking_number}</span>
                    </div>
                    <div className="kv-pair">
                      <span className="kv-key">Signature On File</span>
                      <span className="kv-val">
                        {ship.recipient_signature_present ? 'Verified Signature' : 'No Signature (Direct Delivery)'}
                      </span>
                    </div>
                  </div>

                  {/* Address Alignment Table */}
                  <div style={{ padding: '8px 12px', backgroundColor: 'var(--bg-subtle)', borderRadius: '6px', fontSize: '11px', display: 'flex', flexDirection: 'column', gap: '4px' }}>
                    <div style={{ fontWeight: 600, color: 'var(--text-secondary)' }}>Destination Postal Matching:</div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--text-primary)' }}>
                      <span>Order Postal Code: <strong>{matched_order?.shipping_address?.postal_code || 'N/A'}</strong></span>
                      <span>Delivery Postal Code: <strong>{ship.shipment_address?.postal_code || 'N/A'}</strong></span>
                    </div>
                    {matched_order?.shipping_address?.postal_code !== ship.shipment_address?.postal_code && ship.shipment_address?.postal_code && (
                      <div style={{ color: 'var(--status-block-text)', fontWeight: 600, marginTop: '2px' }}>
                        * Postal code mismatch detected between order and carrier scan.
                      </div>
                    )}
                  </div>
                </div>
              ))
            ) : (
              <div style={{ fontSize: '12px', color: 'var(--text-muted)', fontStyle: 'italic' }}>
                No carrier tracking records linked to this dispute.
              </div>
            )}
          </div>
        </div>

        {/* 4. Matched Merchant Order Record */}
        <div className="panel-card">
          <div className="panel-card-header">
            <span className="panel-card-title">
              <Package size={14} color="var(--accent-primary)" />
              Merchant Order Record
            </span>
            <span className="badge badge-neutral">ERP Source</span>
          </div>

          <div className="panel-card-body">
            {matched_order ? (
              <div className="kv-grid">
                <div className="kv-pair">
                  <span className="kv-key">Order Reference</span>
                  <span className="kv-val font-mono">{matched_order.order_id}</span>
                </div>
                <div className="kv-pair">
                  <span className="kv-key">Customer Name</span>
                  <span className="kv-val">{matched_order.customer_name || 'N/A'}</span>
                </div>
                <div className="kv-pair">
                  <span className="kv-key">Customer Email</span>
                  <span className="kv-val font-mono">{matched_order.customer_email || 'N/A'}</span>
                </div>
                <div className="kv-pair">
                  <span className="kv-key">Gross Amount</span>
                  <span className="kv-val font-mono">
                    ${matched_order.gross_amount?.value} {matched_order.gross_amount?.currency_code}
                  </span>
                </div>
              </div>
            ) : (
              <div style={{ fontSize: '12px', color: 'var(--text-muted)', fontStyle: 'italic' }}>
                No internal order record matched to this transaction.
              </div>
            )}
          </div>
        </div>

        {/* 5. Affirmative Human-in-the-Loop Merchant Action Desk */}
        <div className="panel-card" style={{ border: '1px solid var(--border-strong)', boxShadow: 'var(--shadow-card)' }}>
          <div className="panel-card-header" style={{ backgroundColor: 'var(--bg-subtle)' }}>
            <span className="panel-card-title">
              <Lock size={14} color="var(--accent-primary)" />
              Merchant Action & Submission Desk
            </span>
            <span
              className={`badge ${
                approval_record?.decision === 'APPROVE'
                  ? 'badge-allow'
                  : isReady
                  ? 'badge-review'
                  : 'badge-block'
              }`}
            >
              {approval_record?.decision === 'APPROVE'
                ? 'AUTHORIZED'
                : isReady
                ? 'AWAITING APPROVAL'
                : 'SUBMISSION BARRED'}
            </span>
          </div>

          <div className="panel-card-body">
            {!isReady ? (
              <div style={{ padding: '12px', borderRadius: '6px', backgroundColor: 'var(--status-block-bg)', border: '1px solid var(--status-block-border)', color: 'var(--status-block-text)', fontSize: '12px', lineHeight: 1.45 }}>
                <strong>External Submission Disabled:</strong> Docket policy invariants have refused this claim. Unverified delivery claims cannot be submitted to PayPal.
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                {!approval_request ? (
                  <div>
                    <p style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '8px' }}>
                      Evidence passes deterministic policy barriers. Generate an HMAC-SHA256 authorization ticket to review and approve submission.
                    </p>
                    <button
                      onClick={handleGenerateTicket}
                      disabled={actionLoading}
                      className="btn btn-primary"
                      style={{ width: '100%' }}
                    >
                      <Lock size={13} /> Generate Cryptographic Approval Ticket
                    </button>
                  </div>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                    <div style={{ padding: '10px', backgroundColor: 'var(--bg-subtle)', borderRadius: '6px', fontSize: '11px', display: 'flex', flexDirection: 'column', gap: '4px' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                        <span style={{ color: 'var(--text-muted)' }}>Ticket ID:</span>
                        <span className="font-mono">{approval_request.approval_id}</span>
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                        <span style={{ color: 'var(--text-muted)' }}>Payload SHA-256:</span>
                        <span className="font-mono" title={approval_request.payload_hash}>
                          {approval_request.payload_hash.substring(0, 16)}...
                        </span>
                      </div>
                    </div>

                    {!approval_record ? (
                      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
                        <button
                          onClick={() => handleAuthorize('APPROVE')}
                          disabled={actionLoading}
                          className="btn btn-allow"
                        >
                          <CheckCircle2 size={13} /> Authorize (Approve)
                        </button>
                        <button
                          onClick={() => handleAuthorize('REJECT')}
                          disabled={actionLoading}
                          className="btn btn-secondary"
                          style={{ color: '#dc2626' }}
                        >
                          <XCircle size={13} /> Reject Submission
                        </button>
                      </div>
                    ) : approval_record.decision === 'APPROVE' ? (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                        <div style={{ fontSize: '12px', color: 'var(--status-allow-text)', fontWeight: 600 }}>
                          Approval Authorized by {approval_record.merchant_user_id}
                        </div>
                        {dispatch_result ? (
                          <div style={{ padding: '8px 12px', borderRadius: '5px', backgroundColor: 'var(--status-allow-bg)', border: '1px solid var(--status-allow-border)', fontSize: '11px', color: 'var(--status-allow-text)' }}>
                            <strong>Dispatched Successfully!</strong> Receipt: HTTP {dispatch_result.paypal_status_code || 200}
                          </div>
                        ) : (
                          <button
                            onClick={handleDispatch}
                            disabled={actionLoading}
                            className="btn btn-primary"
                            style={{ width: '100%' }}
                          >
                            <Send size={13} /> Submit Evidence to PayPal API
                          </button>
                        )}
                      </div>
                    ) : (
                      <div style={{ padding: '8px 12px', borderRadius: '5px', backgroundColor: 'var(--status-block-bg)', color: 'var(--status-block-text)', fontSize: '11px' }}>
                        Dispute submission was rejected by merchant.
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* 6. Technical Details & Developer Payloads (Collapsible Details - Hidden from primary flow) */}
        <details className="code-details">
          <summary>
            Inspect Technical Payloads & Raw Schemas (Developer View)
          </summary>
          <div style={{ marginTop: '8px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
              Proposed PayPal <code>provide-evidence</code> Payload:
            </div>
            <pre className="code-block">
              {JSON.stringify(detail.proposed_payload || {}, null, 2)}
            </pre>
          </div>
        </details>
      </div>
    </div>
  );
};
