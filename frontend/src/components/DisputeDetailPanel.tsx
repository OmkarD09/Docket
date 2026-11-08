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
  X,
} from 'lucide-react';
import type { DisputeDetail } from '../types';

interface DisputeDetailPanelProps {
  disputeId: string | null;
  onRefresh: () => void;
  onClose?: () => void;
}

export const DisputeDetailPanel: React.FC<DisputeDetailPanelProps> = ({
  disputeId,
  onRefresh,
  onClose,
}) => {
  const [detail, setDetail] = useState<DisputeDetail | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [actionLoading, setActionLoading] = useState<boolean>(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<boolean>(false);
  const [copiedPayload, setCopiedPayload] = useState<boolean>(false);

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

  const copyToClipboard = (text?: string) => {
    if (!text) return;
    navigator.clipboard.writeText(text);
    setCopiedId(true);
    setTimeout(() => setCopiedId(false), 2000);
  };

  const formatDeadline = (isoString?: string | null, status?: string) => {
    if (status === 'RESOLVED') return 'Closed';
    if (!isoString) return 'Immediate Action Window';
    try {
      const d = new Date(isoString);
      if (isNaN(d.getTime())) return 'Immediate Action Window';
      return d.toLocaleDateString('en-US', { month: 'short', day: '2-digit', year: 'numeric' });
    } catch {
      return 'Immediate Action Window';
    }
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
        <RefreshCw size={24} className="spin" style={{ color: 'var(--accent-slate)' }} />
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

  const {
    dispute,
    matched_order,
    matched_shipments,
    evaluation,
    approval_request,
    approval_record,
    dispatch_result,
    has_prompt_threat,
  } = detail;

  const isReal = dispute?.dispute_id === 'PP-R-NKI-10193390';
  const overallDecision = evaluation?.overall_decision || 'REVIEW';

  const reasonReadable = (dispute?.reason || '')
    .replace(/_/g, ' ')
    .toLowerCase()
    .replace(/\b\w/g, (c: string) => c.toUpperCase());

  // Non-ALLOW check results
  const nonAllowChecks = evaluation?.check_results?.filter((c) => c.decision !== 'ALLOW') || [];
  const primaryCheck = nonAllowChecks[0];
  const recommendedDirective =
    primaryCheck?.recommended_next_action ||
    (overallDecision === 'ALLOW'
      ? 'Authorize evidence submission and dispatch package delivery proof to PayPal API.'
      : 'Review cross-source discrepancies or contact customer.');

  return (
    <div className="detail-drawer">
      {/* 1. Header Overview Bar: Identity, Origin, Amount, Status, Deadline */}
      <div className="drawer-header">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap' }}>
            <span
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '4px',
                padding: '2px 8px',
                borderRadius: '4px',
                fontSize: '11px',
                fontWeight: 600,
                backgroundColor: isReal ? 'var(--status-allow-bg)' : 'var(--bg-subtle)',
                color: isReal ? 'var(--status-allow-text)' : 'var(--text-secondary)',
                border: `1px solid ${isReal ? 'var(--status-allow-border)' : 'var(--border-subtle)'}`,
              }}
            >
              {isReal ? (
                <>
                  <span style={{ width: '5px', height: '5px', borderRadius: '50%', backgroundColor: '#059669' }} />
                  Live Sandbox
                </>
              ) : (
                'Benchmark'
              )}
            </span>

            <span
              style={{
                fontSize: '11px',
                fontWeight: 500,
                padding: '2px 8px',
                borderRadius: '4px',
                backgroundColor: dispute?.status === 'WAITING_FOR_SELLER_RESPONSE' ? '#f0f9ff' : 'var(--bg-subtle)',
                color: dispute?.status === 'WAITING_FOR_SELLER_RESPONSE' ? '#0369a1' : 'var(--text-secondary)',
                border: `1px solid ${dispute?.status === 'WAITING_FOR_SELLER_RESPONSE' ? '#bae6fd' : 'var(--border-subtle)'}`,
              }}
            >
              {dispute?.status === 'WAITING_FOR_SELLER_RESPONSE'
                ? 'Waiting Response'
                : dispute?.status?.replace(/_/g, ' ') || 'Open'}
            </span>

            {has_prompt_threat && (
              <span className="badge badge-threat" title="Adversarial prompt injection quarantined">
                <ShieldAlert size={12} /> Threat Quarantined
              </span>
            )}
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <button
              onClick={() => fetchDetail(disputeId)}
              className="btn btn-secondary"
              style={{ padding: '2px 8px', fontSize: '11px', height: '24px' }}
              title="Refresh case state"
            >
              <RefreshCw size={11} /> Sync
            </button>
            {onClose && (
              <button
                onClick={onClose}
                className="btn btn-secondary"
                style={{ padding: '4px', height: '24px', width: '24px', borderRadius: '4px' }}
                title="Close inspection panel"
              >
                <X size={13} />
              </button>
            )}
          </div>
        </div>

        {/* Dispute ID & Amount */}
        <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginTop: '6px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span className="font-mono" style={{ fontSize: '15px', fontWeight: 700, color: 'var(--text-primary)' }}>
              {dispute?.dispute_id}
            </span>
            <button
              onClick={() => copyToClipboard(dispute?.dispute_id)}
              style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)' }}
              title="Copy Dispute ID"
            >
              {copiedId ? <Check size={13} color="#059669" /> : <Copy size={13} />}
            </button>
          </div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '4px' }}>
            <span className="font-mono" style={{ fontSize: '20px', fontWeight: 700, color: 'var(--text-primary)' }}>
              ${dispute?.dispute_amount?.value || '0.00'}
            </span>
            <span style={{ fontSize: '11px', color: 'var(--text-muted)', fontWeight: 600 }}>
              {dispute?.dispute_amount?.currency_code || 'USD'}
            </span>
          </div>
        </div>

        {/* Reason & Deadline */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '12px', marginTop: '2px' }}>
          <span style={{ color: 'var(--text-secondary)', fontWeight: 500 }}>{reasonReadable}</span>
          <span style={{ display: 'flex', alignItems: 'center', gap: '4px', color: 'var(--text-muted)', fontSize: '11.5px' }}>
            <Clock size={12} />
            Deadline: {formatDeadline(dispute?.seller_response_due_date, dispute?.status)}
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

        {/* 2 & 3. One Clear Docket Policy Decision & Concise Explanation */}
        <div className="panel-card">
          <div className="panel-card-header">
            <span className="panel-card-title">
              <span
                style={{
                  width: '7px',
                  height: '7px',
                  borderRadius: '50%',
                  backgroundColor:
                    overallDecision === 'ALLOW'
                      ? 'var(--status-allow-dot)'
                      : overallDecision === 'BLOCK'
                      ? 'var(--status-block-dot)'
                      : 'var(--status-review-dot)',
                }}
              />
              Docket Policy Assessment
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
              {overallDecision === 'ALLOW' && <CheckCircle2 size={11} />}
              {overallDecision === 'BLOCK' && <XCircle size={11} />}
              {overallDecision === 'REVIEW' && <AlertTriangle size={11} />}
              {overallDecision}
            </span>
          </div>

          <div className="panel-card-body">
            <div>
              <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)', lineHeight: 1.4 }}>
                {evaluation?.summary || 'Policy evaluation completed.'}
              </div>
              <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '4px', lineHeight: 1.5 }}>
                {overallDecision === 'BLOCK' && (
                  <span>
                    Deterministic policy invariants blocked counter-claim submission. Carrier tracking has not confirmed physical delivery to the recipient postal code.
                  </span>
                )}
                {overallDecision === 'ALLOW' && (
                  <span>
                    All policy barriers passed. Carrier delivery proof confirmed physical delivery matching the order shipping address.
                  </span>
                )}
                {overallDecision === 'REVIEW' && (
                  <span>
                    Advisory threshold or data discrepancy flagged. Merchant manual review is required before authorization.
                  </span>
                )}
              </div>
            </div>

            {/* Tri-Partite Readiness Strip: Factual Readiness | Action Eligibility | Recommendation */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '8px', padding: '8px 12px', backgroundColor: 'var(--bg-subtle)', borderRadius: '5px' }}>
              <div>
                <span className="kv-key">Factual Readiness</span>
                <span
                  style={{
                    fontSize: '11.5px',
                    fontWeight: 700,
                    color:
                      evaluation?.factual_readiness === 'ALLOW'
                        ? 'var(--status-allow-text)'
                        : evaluation?.factual_readiness === 'BLOCK'
                        ? 'var(--status-block-text)'
                        : 'var(--status-review-text)',
                    display: 'block',
                    marginTop: '2px',
                  }}
                >
                  {evaluation?.factual_readiness || 'N/A'}
                </span>
              </div>
              <div>
                <span className="kv-key">Action Eligibility</span>
                <span
                  style={{
                    fontSize: '11.5px',
                    fontWeight: 700,
                    color:
                      evaluation?.action_readiness === 'ALLOW'
                        ? 'var(--status-allow-text)'
                        : evaluation?.action_readiness === 'BLOCK'
                        ? 'var(--status-block-text)'
                        : 'var(--status-review-text)',
                    display: 'block',
                    marginTop: '2px',
                  }}
                >
                  {evaluation?.action_readiness || 'N/A'}
                </span>
              </div>
              <div>
                <span className="kv-key">Recommendation</span>
                <span
                  style={{
                    fontSize: '11.5px',
                    fontWeight: 700,
                    color:
                      overallDecision === 'ALLOW'
                        ? 'var(--status-allow-text)'
                        : overallDecision === 'BLOCK'
                        ? 'var(--status-block-text)'
                        : 'var(--status-review-text)',
                    display: 'block',
                    marginTop: '2px',
                  }}
                >
                  {overallDecision === 'ALLOW' ? 'AUTHORIZE' : overallDecision === 'REVIEW' ? 'INVESTIGATE' : 'HOLD / REFUND'}
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* 4. Evidence & Source Provenance */}
        <div className="panel-card">
          <div className="panel-card-header">
            <span className="panel-card-title">
              <Truck size={13} color="var(--accent-slate)" />
              Evidence & Source Provenance
            </span>
            <span className="badge badge-neutral">Reconciled Nodes</span>
          </div>

          <div className="panel-card-body">
            {/* Carrier Tracking */}
            <div>
              <div style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: '6px' }}>
                Carrier Tracking
              </div>
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
                        <span
                          className="kv-val"
                          style={{
                            color:
                              ship.tracking_status === 'DELIVERED'
                                ? 'var(--status-allow-text)'
                                : 'var(--status-block-text)',
                          }}
                        >
                          {ship.tracking_status}
                        </span>
                      </div>
                      <div className="kv-pair">
                        <span className="kv-key">Tracking Number</span>
                        <span className="kv-val font-mono" style={{ fontSize: '11px' }}>
                          {ship.tracking_number}
                        </span>
                      </div>
                      <div className="kv-pair">
                        <span className="kv-key">Signature</span>
                        <span className="kv-val">
                          {ship.recipient_signature_present ? 'Verified Signature' : 'No Signature'}
                        </span>
                      </div>
                    </div>

                    {/* Destination Postal Alignment */}
                    <div
                      style={{
                        padding: '6px 10px',
                        backgroundColor: 'var(--bg-subtle)',
                        borderRadius: '5px',
                        fontSize: '11.5px',
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                      }}
                    >
                      <span style={{ color: 'var(--text-secondary)' }}>
                        Postal Alignment: Order <strong>{matched_order?.shipping_address?.postal_code || 'N/A'}</strong> ↔ Delivery <strong>{ship.shipment_address?.postal_code || 'N/A'}</strong>
                      </span>
                      {matched_order?.shipping_address?.postal_code === ship.shipment_address?.postal_code && ship.shipment_address?.postal_code ? (
                        <span style={{ color: 'var(--status-allow-text)', fontWeight: 600, fontSize: '11px' }}>
                          Matched
                        </span>
                      ) : (
                        <span style={{ color: 'var(--status-block-text)', fontWeight: 600, fontSize: '11px' }}>
                          Mismatch
                        </span>
                      )}
                    </div>
                  </div>
                ))
              ) : (
                <div style={{ fontSize: '12px', color: 'var(--text-muted)', fontStyle: 'italic' }}>
                  No carrier tracking linked.
                </div>
              )}
            </div>

            {/* Merchant Order Divider */}
            <div style={{ borderTop: '1px solid var(--border-light)', paddingTop: '10px' }}>
              <div style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: '6px' }}>
                Merchant Order (ERP)
              </div>
              {matched_order ? (
                <div className="kv-grid">
                  <div className="kv-pair">
                    <span className="kv-key">Order ID</span>
                    <span className="kv-val font-mono">{matched_order.order_id}</span>
                  </div>
                  <div className="kv-pair">
                    <span className="kv-key">Customer</span>
                    <span className="kv-val">{matched_order.customer_name || 'N/A'}</span>
                  </div>
                  <div className="kv-pair">
                    <span className="kv-key">Email</span>
                    <span className="kv-val font-mono" style={{ fontSize: '11px' }}>{matched_order.customer_email || 'N/A'}</span>
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
                  No internal order record matched.
                </div>
              )}
            </div>
          </div>
        </div>

        {/* 5. Individual Policy Findings (Without garish red containers) */}
        <div className="panel-card">
          <div className="panel-card-header">
            <span className="panel-card-title">
              Policy Invariant Findings
            </span>
            <span className="badge badge-neutral">
              {nonAllowChecks.length > 0 ? `${nonAllowChecks.length} Invariant Flagged` : 'All Invariants Passed'}
            </span>
          </div>

          <div className="panel-card-body">
            {nonAllowChecks.length === 0 ? (
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: 'var(--status-allow-text)', fontSize: '12px', fontWeight: 500 }}>
                <CheckCircle2 size={13} color="var(--status-allow-dot)" />
                <span>All 5 policy invariants verified (DeliveryProof, AddressMatch, HATEOASAction, SignatureAssessment, CitationIntegrity).</span>
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {nonAllowChecks.map((check, idx) => (
                  <div
                    key={idx}
                    style={{
                      padding: '8px 12px',
                      borderRadius: '6px',
                      backgroundColor: check.decision === 'BLOCK' ? 'var(--status-block-bg)' : 'var(--status-review-bg)',
                      border: `1px solid ${check.decision === 'BLOCK' ? 'var(--status-block-border)' : 'var(--status-review-border)'}`,
                      fontSize: '11.5px',
                    }}
                  >
                    <div style={{ fontWeight: 600, color: check.decision === 'BLOCK' ? 'var(--status-block-text)' : 'var(--status-review-text)' }}>
                      {check.rule_identifier}
                    </div>
                    <div style={{ color: 'var(--text-secondary)', marginTop: '2px', lineHeight: 1.45 }}>
                      {check.explanation}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* 6. Recommended Next Step */}
        <div
          style={{
            padding: '12px 14px',
            borderRadius: '6px',
            backgroundColor: overallDecision === 'BLOCK' ? 'var(--bg-subtle)' : 'var(--signal-blue-subtle)',
            border: `1px solid ${overallDecision === 'BLOCK' ? 'var(--border-subtle)' : 'var(--signal-blue-border)'}`,
          }}
        >
          <div style={{ fontSize: '11px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em', color: overallDecision === 'BLOCK' ? 'var(--text-muted)' : 'var(--signal-blue)' }}>
            Recommended Directive
          </div>
          <div style={{ fontSize: '12.5px', fontWeight: 500, color: 'var(--text-primary)', marginTop: '3px', lineHeight: 1.45 }}>
            {recommendedDirective}
          </div>
        </div>

        {/* 7. Merchant Approval and Available Actions */}
        <div className="panel-card" style={{ border: '1px solid var(--border-strong)' }}>
          <div className="panel-card-header" style={{ backgroundColor: 'var(--bg-header)' }}>
            <span className="panel-card-title">
              <Lock size={13} color="var(--accent-slate)" />
              Merchant Approval & Actions
            </span>
            <span
              className={`badge ${
                approval_record?.decision === 'APPROVE'
                  ? 'badge-allow'
                  : overallDecision === 'ALLOW'
                  ? 'badge-allow'
                  : overallDecision === 'REVIEW'
                  ? 'badge-review'
                  : 'badge-block'
              }`}
            >
              {approval_record?.decision === 'APPROVE'
                ? 'AUTHORIZED'
                : overallDecision === 'ALLOW'
                ? 'AWAITING APPROVAL'
                : overallDecision === 'REVIEW'
                ? 'REVIEW REQUIRED'
                : 'SUBMISSION BARRED'}
            </span>
          </div>

          <div className="panel-card-body">
            {overallDecision === 'BLOCK' ? (
              <div style={{ padding: '10px 12px', borderRadius: '5px', backgroundColor: 'var(--status-block-bg)', border: '1px solid var(--status-block-border)', color: 'var(--status-block-text)', fontSize: '12px', lineHeight: 1.45 }}>
                <strong>External Submission Barred:</strong> Deterministic policy invariants blocked evidence dispatch. Carrier tracking has not confirmed completed delivery to the recipient postal code.
              </div>
            ) : overallDecision === 'REVIEW' ? (
              <div style={{ padding: '10px 12px', borderRadius: '5px', backgroundColor: 'var(--status-review-bg)', border: '1px solid var(--status-review-border)', color: 'var(--status-review-text)', fontSize: '12px', lineHeight: 1.45 }}>
                <strong>Factual Review Outstanding:</strong> PayPal dispute lifecycle permits response (Action Eligibility: ALLOW), but factual readiness requires merchant resolution of data discrepancies or courier inquiries before evidence can be dispatched.
                <div style={{ marginTop: '6px', fontSize: '11.5px', color: 'var(--text-secondary)' }}>
                  <strong>Directive:</strong> {recommendedDirective}
                </div>
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                {!approval_request ? (
                  <div>
                    <p style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '8px', lineHeight: 1.4 }}>
                      Evidence passes policy verification. Generate a cryptographic HMAC-SHA256 ticket to review and authorize dispatch.
                    </p>
                    <button
                      onClick={handleGenerateTicket}
                      disabled={actionLoading}
                      className="btn btn-primary"
                      style={{ width: '100%', height: '32px' }}
                    >
                      <Lock size={13} /> Generate Cryptographic Approval Ticket
                    </button>
                  </div>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                    <div style={{ padding: '8px 12px', backgroundColor: 'var(--bg-subtle)', borderRadius: '5px', fontSize: '11px', display: 'flex', flexDirection: 'column', gap: '4px' }}>
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
                          style={{ height: '32px' }}
                        >
                          <CheckCircle2 size={13} /> Authorize (Approve)
                        </button>
                        <button
                          onClick={() => handleAuthorize('REJECT')}
                          disabled={actionLoading}
                          className="btn btn-secondary"
                          style={{ color: '#dc2626', height: '32px' }}
                        >
                          <XCircle size={13} /> Reject
                        </button>
                      </div>
                    ) : approval_record.decision === 'APPROVE' ? (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                        <div style={{ fontSize: '12px', color: 'var(--status-allow-text)', fontWeight: 600 }}>
                          Approval Authorized by {approval_record.merchant_user_id}
                        </div>
                        {dispatch_result ? (
                          <div style={{ padding: '8px 12px', borderRadius: '5px', backgroundColor: 'var(--status-allow-bg)', border: '1px solid var(--status-allow-border)', fontSize: '11.5px', color: 'var(--status-allow-text)' }}>
                            <strong>Dispatched Successfully!</strong> Receipt: HTTP {dispatch_result.paypal_status_code || 200}
                          </div>
                        ) : (
                          <button
                            onClick={handleDispatch}
                            disabled={actionLoading}
                            className="btn btn-primary"
                            style={{ width: '100%', height: '32px' }}
                          >
                            <Send size={13} /> Submit Evidence to PayPal API
                          </button>
                        )}
                      </div>
                    ) : (
                      <div style={{ padding: '8px 12px', borderRadius: '5px', backgroundColor: 'var(--status-block-bg)', color: 'var(--status-block-text)', fontSize: '11.5px' }}>
                        Dispute submission was rejected by merchant operations.
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Expandable Technical Inspector (Collapsible - Developer View) */}
        <details className="code-details">
          <summary>
            Inspect Technical Payloads & Citations (Developer View)
          </summary>
          <div style={{ marginTop: '8px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                Proposed PayPal <code>provide-evidence</code> Payload:
              </span>
              <button
                onClick={(e) => {
                  e.preventDefault();
                  if (detail.proposed_payload) {
                    navigator.clipboard.writeText(JSON.stringify(detail.proposed_payload, null, 2));
                    setCopiedPayload(true);
                    setTimeout(() => setCopiedPayload(false), 2000);
                  }
                }}
                className="btn btn-secondary"
                style={{ padding: '2px 7px', fontSize: '10.5px', height: '22px', gap: '4px' }}
                title="Copy JSON Payload"
              >
                {copiedPayload ? <Check size={11} color="#059669" /> : <Copy size={11} />}
                <span>{copiedPayload ? 'Copied' : 'Copy JSON'}</span>
              </button>
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
