import React, { useState, useEffect, useMemo, useCallback } from 'react';
import {
  ShieldCheck,
  AlertOctagon,
  Search,
  Copy,
  Check,
  ChevronLeft,
  ChevronRight,
  X,
  ExternalLink,
  Lock,
  Filter,
  Calendar,
  Ticket,
  Link2,
  ChevronDown,
  ChevronUp,
  Layers,
} from 'lucide-react';
import type { AuditEventItem, AuditTrailResponse, AuditTrailVerificationDetails } from '../types';

interface AuditTrailViewProps {
  onNavigateToDispute?: (disputeId: string) => void;
}

/**
 * Format timestamp into an unambiguous format:
 * e.g., "03 Nov 2026, 06:01:51 PM"
 */
function formatAuditTimestamp(isoString: string): string {
  if (!isoString) return '—';
  try {
    const d = new Date(isoString);
    if (isNaN(d.getTime())) return isoString;
    return new Intl.DateTimeFormat('en-GB', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: true,
    })
      .format(d)
      .replace(/\b(am|pm)\b/g, (m) => m.toUpperCase());
  } catch {
    return isoString;
  }
}

/**
 * Map raw event types to professional human-readable labels
 */
function getEventTypeLabel(eventType: string): string {
  switch (eventType) {
    case 'DISPUTE_INGESTED':
      return 'Dispute Ingested';
    case 'DISPUTE_SYNCHRONIZED':
      return 'Dispute Synchronized';
    case 'DUPLICATE_WEBHOOK_RECEIVED':
      return 'Duplicate Webhook';
    case 'DUPLICATE_WEBHOOK_IGNORED':
      return 'Duplicate Ignored';
    case 'EVIDENCE_RECONCILED':
      return 'Evidence Reconciled';
    case 'POLICY_EVALUATED':
      return 'Policy Evaluated';
    case 'APPROVAL_REQUESTED':
      return 'Approval Requested';
    case 'APPROVAL_GRANTED':
      return 'Approval Granted';
    case 'APPROVAL_REJECTED':
      return 'Approval Rejected';
    case 'APPROVAL_EXPIRED':
      return 'Approval Expired';
    case 'APPROVAL_CONSUMED':
      return 'Approval Consumed';
    case 'DISPATCH_ATTEMPTED':
      return 'Dispatch Attempted';
    case 'DISPATCH_SUCCEEDED':
      return 'Dispatch Succeeded';
    case 'DISPATCH_FAILED':
      return 'Dispatch Failed';
    default:
      return eventType.replace(/_/g, ' ').replace(/\b\w/g, (l) => l.toUpperCase());
  }
}

/**
 * Map actors to clean human-readable names
 */
function getActorLabel(actor: string): string {
  switch (actor) {
    case 'PAYPAL_WEBHOOK':
      return 'PayPal Webhook';
    case 'SYSTEM':
      return 'Docket Engine';
    case 'PAYPAL_SANDBOX_API':
      return 'PayPal Sandbox API';
    case 'APPROVAL_GATE':
      return 'Approval Gate';
    case 'MERCHANT_OPERATOR':
      return 'Merchant Operator';
    case 'POLICY_ENGINE':
      return 'Policy Engine';
    case 'RECONCILER':
      return 'Evidence Reconciler';
    case 'APPROVAL_SERVICE':
      return 'Approval Service';
    case 'DISPATCHER':
      return 'PayPal Dispatcher';
    default:
      return actor.replace(/_/g, ' ').replace(/\b\w/g, (l) => l.toUpperCase());
  }
}

/**
 * Return appropriate styling for event type badge
 */
function getEventTypeBadgeClass(eventType: string): string {
  switch (eventType) {
    case 'POLICY_EVALUATED':
    case 'DISPATCH_SUCCEEDED':
    case 'APPROVAL_GRANTED':
      return 'badge-allow';
    case 'DISPATCH_FAILED':
    case 'APPROVAL_REJECTED':
    case 'APPROVAL_EXPIRED':
      return 'badge-block';
    case 'APPROVAL_REQUESTED':
      return 'badge-review';
    case 'DUPLICATE_WEBHOOK_RECEIVED':
    case 'DUPLICATE_WEBHOOK_IGNORED':
    case 'APPROVAL_CONSUMED':
      return 'badge-neutral';
    case 'DISPUTE_SYNCHRONIZED':
      return 'badge-signal';
    default:
      return 'badge-signal';
  }
}

/**
 * Return appropriate styling for result/summary badge
 */
function getResultBadgeClass(result?: string): string {
  if (!result) return 'badge-neutral';
  const upper = result.toUpperCase();
  if (upper.includes('SIMULATED')) {
    return 'badge-review';
  }
  if (upper.includes('ALLOW') || upper.includes('APPROVED') || upper.includes('LIVE 200') || upper.includes('200 OK')) {
    return 'badge-allow';
  }
  if (upper.includes('REVIEW') || upper.includes('WAITING') || upper.includes('TICKET') || upper.includes('SYNC')) {
    return 'badge-review';
  }
  if (upper.includes('BLOCK') || upper.includes('REJECTED') || upper.includes('FAILED') || upper.includes('EXPIRED')) {
    return 'badge-block';
  }
  if (upper.includes('DUPLICATE') || upper.includes('CONSUMED')) {
    return 'badge-neutral';
  }
  return 'badge-signal';
}

function getEventDateKey(isoString: string): string {
  try {
    const d = new Date(isoString);
    if (isNaN(d.getTime())) return 'Unknown Date';
    return new Intl.DateTimeFormat('en-GB', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
    }).format(d);
  } catch {
    return 'Unknown Date';
  }
}

function getEventTimeStr(isoString: string): string {
  try {
    const d = new Date(isoString);
    if (isNaN(d.getTime())) return isoString;
    return new Intl.DateTimeFormat('en-GB', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: true,
    })
      .format(d)
      .replace(/\b(am|pm)\b/g, (m) => m.toUpperCase());
  } catch {
    return isoString;
  }
}

function getEventUtcTooltip(isoString: string): string {
  try {
    const d = new Date(isoString);
    if (isNaN(d.getTime())) return isoString;
    return `UTC Timestamp: ${d.toISOString()}`;
  } catch {
    return isoString;
  }
}

export const AuditTrailView: React.FC<AuditTrailViewProps> = ({ onNavigateToDispute }) => {
  const [events, setEvents] = useState<AuditEventItem[]>([]);
  const [totalEvents, setTotalEvents] = useState<number>(0);
  const [verifiedCount, setVerifiedCount] = useState<number>(0);
  const [failedCount, setFailedCount] = useState<number>(0);
  const [chainIntact, setChainIntact] = useState<boolean>(true);
  const [lastVerifiedAt, setLastVerifiedAt] = useState<string>('');
  const [verificationDetails, setVerificationDetails] = useState<AuditTrailVerificationDetails | null>(null);

  // Selection & Copy state
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  // Filters
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [eventTypeFilter, setEventTypeFilter] = useState<string>('ALL');
  const [actorFilter, setActorFilter] = useState<string>('ALL');
  const [verificationFilter, setVerificationFilter] = useState<string>('ALL');

  const fetchAuditTrail = useCallback(async () => {
    try {
      const resp = await fetch('/api/audit-trail');
      if (resp.ok) {
        const data: AuditTrailResponse = await resp.json();
        setEvents(data.events || []);
        setTotalEvents(data.total_events || (data.events || []).length);
        setVerifiedCount(data.verified_count || 0);
        setFailedCount(data.failed_count || 0);
        setChainIntact(data.chain_intact);
        setLastVerifiedAt(data.last_verified_at || new Date().toISOString());
        setVerificationDetails(data.verification_details || null);

        // Auto-select first event if none selected
        if (!selectedEventId && data.events && data.events.length > 0) {
          setSelectedEventId(data.events[0].event_id);
        }
      }
    } catch (err) {
      console.error('Failed to fetch audit trail:', err);
    }
  }, [selectedEventId]);

  useEffect(() => {
    fetchAuditTrail();
  }, [fetchAuditTrail]);

  // Copy helper with feedback
  const handleCopy = (text: string, key: string) => {
    navigator.clipboard.writeText(text);
    setCopiedKey(key);
    setTimeout(() => {
      setCopiedKey(null);
    }, 1800);
  };

  // Filtered events
  const filteredEvents = useMemo(() => {
    return events.filter((evt) => {
      // 1. Search Query
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase().trim();
        const matchesDispute = evt.dispute_id?.toLowerCase().includes(q);
        const matchesEventId = evt.event_id?.toLowerCase().includes(q);
        const matchesActor = evt.actor?.toLowerCase().includes(q);
        const matchesType = evt.event_type?.toLowerCase().includes(q);
        const matchesResult = evt.result?.toLowerCase().includes(q);
        if (!matchesDispute && !matchesEventId && !matchesActor && !matchesType && !matchesResult) {
          return false;
        }
      }

      // 2. Event Type Filter
      if (eventTypeFilter !== 'ALL' && evt.event_type !== eventTypeFilter) {
        return false;
      }

      // 3. Actor Filter
      if (actorFilter !== 'ALL' && evt.actor !== actorFilter) {
        return false;
      }

      // 4. Verification Status Filter
      if (verificationFilter === 'VERIFIED' && evt.is_verified === false) {
        return false;
      }
      if (verificationFilter === 'FAILED' && evt.is_verified !== false) {
        return false;
      }

      return true;
    });
  }, [events, searchQuery, eventTypeFilter, actorFilter, verificationFilter]);

  // Synchronize drawer selection with filtered results
  useEffect(() => {
    if (filteredEvents.length > 0) {
      const exists = filteredEvents.some((e) => e.event_id === selectedEventId);
      if (!exists) {
        setSelectedEventId(filteredEvents[0].event_id);
      }
    }
  }, [filteredEvents, selectedEventId]);

  // Current selected event object
  const selectedEvent = useMemo(() => {
    if (!selectedEventId) return null;
    return events.find((e) => e.event_id === selectedEventId) || null;
  }, [events, selectedEventId]);

  // Index of current selected event in full chain (for Prev / Next navigation)
  const currentChainIndex = useMemo(() => {
    if (!selectedEventId) return -1;
    return events.findIndex((e) => e.event_id === selectedEventId);
  }, [events, selectedEventId]);

  const handlePrevEvent = () => {
    if (currentChainIndex > 0) {
      setSelectedEventId(events[currentChainIndex - 1].event_id);
    }
  };

  const handleNextEvent = () => {
    if (currentChainIndex >= 0 && currentChainIndex < events.length - 1) {
      setSelectedEventId(events[currentChainIndex + 1].event_id);
    }
  };

  // Dedicated lifecycle state fetched directly from canonical SQLite
  const [lifecycleEvents, setLifecycleEvents] = useState<AuditEventItem[]>([]);
  const [lifecycleLoading, setLifecycleLoading] = useState<boolean>(false);
  const [groupRepeated, setGroupRepeated] = useState<boolean>(true);
  const [expandedGroups, setExpandedGroups] = useState<Record<string, boolean>>({});

  const activeDisputeId = selectedEvent?.dispute_id;

  useEffect(() => {
    if (!activeDisputeId) {
      setLifecycleEvents([]);
      return;
    }

    let isCancelled = false;
    setLifecycleLoading(true);

    fetch(`/api/disputes/${activeDisputeId}/lifecycle`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (!isCancelled && data && Array.isArray(data.events)) {
          setLifecycleEvents(data.events);
        } else if (!isCancelled) {
          const fallback = events.filter((e) => e.dispute_id === activeDisputeId);
          setLifecycleEvents(fallback);
        }
      })
      .catch(() => {
        if (!isCancelled) {
          const fallback = events.filter((e) => e.dispute_id === activeDisputeId);
          setLifecycleEvents(fallback);
        }
      })
      .finally(() => {
        if (!isCancelled) {
          setLifecycleLoading(false);
        }
      });

    return () => {
      isCancelled = true;
    };
  }, [activeDisputeId, events]);

  type LifecycleItem =
    | { type: 'single'; event: AuditEventItem }
    | {
        type: 'group';
        id: string;
        eventType: string;
        actor: string;
        events: AuditEventItem[];
        firstTimestamp: string;
        lastTimestamp: string;
      };

  interface DateSection {
    dateKey: string;
    items: LifecycleItem[];
  }

  const dateSections = useMemo<DateSection[]>(() => {
    if (!lifecycleEvents.length) return [];

    const map = new Map<string, AuditEventItem[]>();
    for (const evt of lifecycleEvents) {
      const dk = getEventDateKey(evt.timestamp);
      if (!map.has(dk)) {
        map.set(dk, []);
      }
      map.get(dk)!.push(evt);
    }

    const sections: DateSection[] = [];

    for (const [dateKey, dayEvents] of map.entries()) {
      if (!groupRepeated) {
        sections.push({
          dateKey,
          items: dayEvents.map((e) => ({ type: 'single', event: e })),
        });
        continue;
      }

      const items: LifecycleItem[] = [];
      let i = 0;
      while (i < dayEvents.length) {
        const curr = dayEvents[i];
        let j = i + 1;
        while (
          j < dayEvents.length &&
          dayEvents[j].event_type === curr.event_type &&
          dayEvents[j].actor === curr.actor &&
          !curr.event_type.startsWith('APPROVAL_') &&
          !curr.event_type.startsWith('DISPATCH_')
        ) {
          j++;
        }

        const runCount = j - i;
        if (runCount >= 2) {
          const groupEvents = dayEvents.slice(i, j);
          const groupId = `grp_${curr.event_id}_${runCount}`;
          items.push({
            type: 'group',
            id: groupId,
            eventType: curr.event_type,
            actor: curr.actor,
            events: groupEvents,
            firstTimestamp: curr.timestamp,
            lastTimestamp: groupEvents[groupEvents.length - 1].timestamp,
          });
          i = j;
        } else {
          items.push({ type: 'single', event: curr });
          i++;
        }
      }

      sections.push({ dateKey, items });
    }

    return sections;
  }, [lifecycleEvents, groupRepeated]);

  const renderTimelineEventItem = (rEvt: AuditEventItem) => {
    const isActive = rEvt.event_id === selectedEventId;
    const isSim = rEvt.is_simulated || (rEvt.result && rEvt.result.includes('Simulated'));

    return (
      <div
        key={rEvt.event_id}
        className={`audit-timeline-item ${isActive ? 'active' : ''}`}
        onClick={() => setSelectedEventId(rEvt.event_id)}
        title={getEventUtcTooltip(rEvt.timestamp)}
      >
        <div className="audit-timeline-dot" />

        {/* Top row: Badges + Timestamp */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '6px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '5px', flexWrap: 'wrap' }}>
            <span
              className={`badge ${getEventTypeBadgeClass(rEvt.event_type)}`}
              style={{ fontSize: '10px' }}
            >
              {getEventTypeLabel(rEvt.event_type)}
            </span>

            {/* Approval ticket ID connection */}
            {rEvt.approval_id && (
              <span
                className="timeline-ticket-pill"
                title={`Approval Ticket ID: ${rEvt.approval_id}`}
              >
                <Ticket size={9} />
                <span>{rEvt.approval_id.slice(0, 11)}</span>
              </span>
            )}

            {/* Dispatch Correlation ID */}
            {rEvt.correlation_id && (
              <span
                className="timeline-corr-pill"
                title={`PayPal Debug Correlation ID: ${rEvt.correlation_id}`}
              >
                <Link2 size={9} />
                <span>{rEvt.correlation_id.slice(0, 16)}...</span>
              </span>
            )}

            {/* Simulation marker */}
            {isSim && (
              <span
                className="badge badge-neutral"
                style={{
                  fontSize: '9px',
                  padding: '1px 5px',
                  backgroundColor: '#fffbeb',
                  color: '#92400e',
                  border: '1px solid #fde68a',
                  fontWeight: 600,
                }}
                title="Simulated test dispatch verification — No live PayPal mutation occurred"
              >
                Simulation
              </span>
            )}
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '4px', whiteSpace: 'nowrap' }}>
            <span style={{ fontSize: '10px', color: 'var(--text-muted)' }}>
              {getEventTimeStr(rEvt.timestamp)}
            </span>
          </div>
        </div>

        {/* Bottom row: Actor + Result + Chain Index */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            marginTop: '3px',
            fontSize: '11px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ color: 'var(--text-secondary)' }}>{getActorLabel(rEvt.actor)}</span>
            {rEvt.global_chain_index && (
              <span className="timeline-chain-index" title="Position in global SHA-256 audit chain">
                Chain #{rEvt.global_chain_index}
              </span>
            )}
          </div>

          <span
            className={`badge ${getResultBadgeClass(rEvt.result)}`}
            style={{ fontSize: '9.5px', padding: '1px 5px' }}
          >
            {rEvt.result || 'Logged'}
          </span>
        </div>
      </div>
    );
  };

  // Clear all active filters
  const hasActiveFilters =
    searchQuery.trim() !== '' ||
    eventTypeFilter !== 'ALL' ||
    actorFilter !== 'ALL' ||
    verificationFilter !== 'ALL';

  const clearFilters = () => {
    setSearchQuery('');
    setEventTypeFilter('ALL');
    setActorFilter('ALL');
    setVerificationFilter('ALL');
  };

  return (
    <div className="audit-workspace-container">
      {/* 1. Operational Header Area */}
      <div className="audit-header-area">
        <div className="audit-header-top">
          <div>
            <div style={{ fontSize: '15px', fontWeight: 700, color: 'var(--text-primary)', letterSpacing: '-0.015em' }}>
              Cryptographic Audit Ledger
            </div>
            <div className="audit-subtitle">
              Tamper-evident SHA-256 hash-chained audit trail with forward verification and event-level tamper detection.
            </div>
          </div>

          <div className="audit-header-actions">
            {/* Cryptographic Chain Integrity Indicator */}
            {chainIntact ? (
              <div
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '6px',
                  padding: '4px 10px',
                  borderRadius: '5px',
                  fontSize: '11px',
                  fontWeight: 600,
                  backgroundColor: 'var(--status-allow-bg)',
                  color: 'var(--status-allow-text)',
                  border: '1px solid var(--status-allow-border)',
                }}
                title={`Last verified: ${formatAuditTimestamp(lastVerifiedAt)}`}
              >
                <ShieldCheck size={13} color="#059669" />
                <span>
                  Chain Intact · {verifiedCount} / {totalEvents} Verified · {formatAuditTimestamp(lastVerifiedAt)}
                </span>
              </div>
            ) : (
              <div
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '6px',
                  padding: '4px 10px',
                  borderRadius: '5px',
                  fontSize: '11px',
                  fontWeight: 600,
                  backgroundColor: 'var(--status-block-bg)',
                  color: 'var(--status-block-text)',
                  border: '1px solid var(--status-block-border)',
                }}
                title={verificationDetails?.error_message || 'Hash chain verification failed'}
              >
                <AlertOctagon size={13} color="#dc2626" />
                <span>
                  Integrity Compromised · {failedCount} Failure{failedCount > 1 ? 's' : ''} Detected
                </span>
              </div>
            )}

            {/* Continuous Autonomous Verification Badge */}
            <div
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                padding: '4px 10px',
                borderRadius: '5px',
                fontSize: '11px',
                fontWeight: 500,
                backgroundColor: 'var(--bg-subtle)',
                border: '1px solid var(--border-subtle)',
                color: 'var(--text-secondary)',
              }}
              title="Continuous verification runs automatically on every transaction event and periodic background cycle."
            >
              <span
                style={{
                  width: '6px',
                  height: '6px',
                  borderRadius: '50%',
                  backgroundColor: '#059669',
                  boxShadow: '0 0 0 2px rgba(5, 150, 105, 0.2)',
                }}
              />
              <span>Continuous Verification Active</span>
            </div>
          </div>
        </div>

        {/* 2. High-Level Summary Metrics (3 cards) */}
        <div className="audit-metrics-strip">
          <div className="audit-metric-card">
            <span className="audit-metric-label">Total Ledger Events</span>
            <span className="audit-metric-val">{totalEvents}</span>
            <span className="audit-metric-subtext">Tamper-evident hash-chained records</span>
          </div>

          <div className="audit-metric-card">
            <span className="audit-metric-label" style={{ color: 'var(--status-allow-text)' }}>
              Verified Intact Records
            </span>
            <span className="audit-metric-val" style={{ color: '#059669' }}>
              {verifiedCount}
            </span>
            <span className="audit-metric-subtext">Deterministic SHA-256 chain</span>
          </div>

          <div className={`audit-metric-card ${failedCount > 0 ? 'has-failures' : ''}`}>
            <span className="audit-metric-label">Integrity Failures</span>
            <span
              className="audit-metric-val"
              style={{ color: failedCount > 0 ? 'var(--status-block-dot)' : 'var(--text-secondary)' }}
            >
              {failedCount}
            </span>
            <span className="audit-metric-subtext">
              {failedCount === 0 ? 'Zero tampering detected' : 'Cryptographic link broken!'}
            </span>
          </div>
        </div>
      </div>

      {/* 3. Event Filtering & Search Toolbar */}
      <div className="audit-toolbar">
        <div className="audit-toolbar-left">
          {/* Search Box */}
          <div className="audit-search-input-wrapper">
            <Search
              size={13}
              style={{
                position: 'absolute',
                left: '8px',
                top: '50%',
                transform: 'translateY(-50%)',
                color: 'var(--text-muted)',
              }}
            />
            <input
              type="text"
              className="audit-search-input"
              placeholder="Search Dispute ID, Event ID, Actor..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>

          {/* Event Type Filter */}
          <select
            className="audit-select"
            value={eventTypeFilter}
            onChange={(e) => setEventTypeFilter(e.target.value)}
          >
            <option value="ALL">All Event Types</option>
            <option value="DISPUTE_INGESTED">Dispute Ingested</option>
            <option value="DISPUTE_SYNCHRONIZED">Dispute Synchronized</option>
            <option value="DUPLICATE_WEBHOOK_RECEIVED">Duplicate Webhook</option>
            <option value="DUPLICATE_WEBHOOK_IGNORED">Duplicate Ignored</option>
            <option value="EVIDENCE_RECONCILED">Evidence Reconciled</option>
            <option value="POLICY_EVALUATED">Policy Evaluated</option>
            <option value="APPROVAL_REQUESTED">Approval Requested</option>
            <option value="APPROVAL_GRANTED">Approval Granted</option>
            <option value="APPROVAL_REJECTED">Approval Rejected</option>
            <option value="DISPATCH_ATTEMPTED">Dispatch Attempted</option>
            <option value="DISPATCH_SUCCEEDED">Dispatch Succeeded</option>
            <option value="DISPATCH_FAILED">Dispatch Failed</option>
          </select>

          {/* Actor Filter */}
          <select
            className="audit-select"
            value={actorFilter}
            onChange={(e) => setActorFilter(e.target.value)}
          >
            <option value="ALL">All Actors</option>
            <option value="PAYPAL_WEBHOOK">PayPal Webhook</option>
            <option value="SYSTEM">Docket Engine</option>
            <option value="POLICY_ENGINE">Policy Engine</option>
            <option value="RECONCILER">Evidence Reconciler</option>
            <option value="APPROVAL_SERVICE">Approval Service</option>
            <option value="MERCHANT_OPERATOR">Merchant Operator</option>
            <option value="DISPATCHER">PayPal Dispatcher</option>
          </select>

          {/* Verification Status Filter */}
          <select
            className="audit-select"
            value={verificationFilter}
            onChange={(e) => setVerificationFilter(e.target.value)}
          >
            <option value="ALL">All Verifications</option>
            <option value="VERIFIED">Verified Only</option>
            <option value="FAILED">Integrity Failures Only</option>
          </select>

          {/* Clear Filters Button */}
          {hasActiveFilters && (
            <button
              className="btn btn-secondary"
              onClick={clearFilters}
              style={{ height: '28px', fontSize: '11px', padding: '0 8px' }}
            >
              <Filter size={11} />
              <span>Clear Filters</span>
            </button>
          )}
        </div>

        {/* Counter */}
        <div style={{ fontSize: '11.5px', color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>
          Showing <strong>{filteredEvents.length}</strong> of <strong>{events.length}</strong> records
        </div>
      </div>

      {/* 4. Split Workspace: Table on the left, Drawer on the right */}
      <div className={`audit-workspace-split ${!selectedEvent ? 'full-width' : ''}`}>
        {/* Main Audit Trail Table */}
        <div className="audit-table-container">
          <table className="audit-table">
            <thead>
              <tr>
                <th style={{ width: '175px', whiteSpace: 'nowrap' }}>Timestamp</th>
                <th style={{ width: '150px', whiteSpace: 'nowrap' }}>Event Type</th>
                <th style={{ width: '165px', whiteSpace: 'nowrap' }}>Dispute ID</th>
                <th style={{ width: '155px', whiteSpace: 'nowrap' }}>Actor</th>
                <th style={{ whiteSpace: 'nowrap' }}>Result / Summary</th>
                <th style={{ width: '105px', textAlign: 'center', whiteSpace: 'nowrap' }}>Integrity</th>
              </tr>
            </thead>
            <tbody>
              {filteredEvents.length === 0 ? (
                <tr>
                  <td colSpan={6} style={{ textAlign: 'center', padding: '36px', color: 'var(--text-muted)' }}>
                    No audit records match the selected filter criteria.
                  </td>
                </tr>
              ) : (
                filteredEvents.map((evt) => {
                  const isSelected = selectedEventId === evt.event_id;
                  const isIntact = evt.is_verified !== false;
                  return (
                    <tr
                      key={evt.event_id}
                      className={`audit-row ${isSelected ? 'selected' : ''}`}
                      onClick={() => setSelectedEventId(evt.event_id)}
                    >
                      {/* Timestamp */}
                      <td style={{ whiteSpace: 'nowrap' }}>
                        <span className="audit-timestamp">{formatAuditTimestamp(evt.timestamp)}</span>
                      </td>

                      {/* Event Type Badge */}
                      <td style={{ whiteSpace: 'nowrap' }}>
                        <span className={`badge ${getEventTypeBadgeClass(evt.event_type)}`}>
                          {getEventTypeLabel(evt.event_type)}
                        </span>
                      </td>

                      {/* Dispute ID */}
                      <td style={{ whiteSpace: 'nowrap' }}>
                        <span
                          className="font-mono"
                          style={{
                            fontSize: '11.5px',
                            fontWeight: 600,
                            color: isSelected ? 'var(--signal-blue)' : 'var(--text-primary)',
                            whiteSpace: 'nowrap',
                          }}
                        >
                          {evt.dispute_id}
                        </span>
                      </td>

                      {/* Actor */}
                      <td style={{ whiteSpace: 'nowrap' }}>
                        <span style={{ fontSize: '11.5px', color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>
                          {getActorLabel(evt.actor)}
                        </span>
                      </td>

                      {/* Result / Summary */}
                      <td style={{ whiteSpace: 'nowrap' }}>
                        <span className={`badge ${getResultBadgeClass(evt.result)}`}>
                          {evt.result || 'Logged'}
                        </span>
                      </td>

                      {/* Integrity */}
                      <td style={{ textAlign: 'center' }}>
                        {isIntact ? (
                          <span
                            className="badge badge-allow"
                            style={{ gap: '4px', fontSize: '10.5px', padding: '2px 6px' }}
                          >
                            <span
                              style={{
                                width: '5px',
                                height: '5px',
                                borderRadius: '50%',
                                backgroundColor: '#059669',
                              }}
                            />
                            <span>Verified</span>
                          </span>
                        ) : (
                          <span
                            className="badge badge-block"
                            style={{ gap: '4px', fontSize: '10.5px', padding: '2px 6px' }}
                          >
                            <span
                              style={{
                                width: '5px',
                                height: '5px',
                                borderRadius: '50%',
                                backgroundColor: '#dc2626',
                              }}
                            />
                            <span>Broken</span>
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        {/* 5. Event Detail Drawer (Right side) */}
        {selectedEvent && (
          <div className="audit-drawer">
            {/* Drawer Header */}
            <div className="audit-drawer-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span className={`badge ${getEventTypeBadgeClass(selectedEvent.event_type)}`}>
                  {getEventTypeLabel(selectedEvent.event_type)}
                </span>
                <span style={{ fontSize: '12.5px', fontWeight: 600, color: 'var(--text-primary)' }}>
                  Event Inspection
                </span>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span className="font-mono" style={{ fontSize: '10.5px', color: 'var(--text-muted)' }}>
                  {selectedEvent.event_id}
                </span>
                <button
                  className="btn btn-secondary"
                  onClick={() => setSelectedEventId(null)}
                  style={{ padding: '4px', height: '24px', width: '24px', borderRadius: '4px' }}
                  title="Close inspection drawer"
                >
                  <X size={13} />
                </button>
              </div>
            </div>

            {/* Drawer Body */}
            <div className="audit-drawer-body">
              {/* Section: Event Overview */}
              <div className="panel-card">
                <div className="panel-card-header">
                  <span className="panel-card-title">Event Overview</span>
                  <span className="badge badge-neutral" style={{ fontSize: '10.5px' }}>
                    Metadata
                  </span>
                </div>
                <div className="panel-card-body">
                  <div className="kv-grid">
                    <div className="kv-item">
                      <span className="kv-key">Event ID</span>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginTop: '2px' }}>
                        <span className="font-mono kv-val" style={{ fontSize: '11px' }}>
                          {selectedEvent.event_id}
                        </span>
                        <button
                          className="btn btn-secondary"
                          onClick={() => handleCopy(selectedEvent.event_id, 'eventId')}
                          style={{ padding: '2px 5px', height: '20px', fontSize: '10px' }}
                          title="Copy Event ID"
                        >
                          {copiedKey === 'eventId' ? (
                            <Check size={11} color="#059669" />
                          ) : (
                            <Copy size={11} />
                          )}
                        </button>
                      </div>
                    </div>

                    <div className="kv-item">
                      <span className="kv-key">Dispute ID</span>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginTop: '2px' }}>
                        <span className="font-mono kv-val" style={{ fontSize: '11px', color: 'var(--signal-blue)' }}>
                          {selectedEvent.dispute_id}
                        </span>
                        {onNavigateToDispute && (
                          <button
                            className="btn btn-secondary"
                            onClick={() => onNavigateToDispute(selectedEvent.dispute_id)}
                            style={{ padding: '2px 5px', height: '20px', fontSize: '10px' }}
                            title="Open in Disputes Workspace"
                          >
                            <ExternalLink size={11} />
                          </button>
                        )}
                      </div>
                    </div>

                    <div className="kv-item">
                      <span className="kv-key">Timestamp (Local)</span>
                      <span className="kv-val" style={{ fontSize: '11.5px' }}>
                        {formatAuditTimestamp(selectedEvent.timestamp)}
                      </span>
                    </div>

                    <div className="kv-item">
                      <span className="kv-key">Actor & Origin</span>
                      <span className="kv-val" style={{ fontSize: '11.5px' }}>
                        {getActorLabel(selectedEvent.actor)}
                      </span>
                    </div>

                    <div className="kv-item">
                      <span className="kv-key">Outcome / Result</span>
                      <div style={{ marginTop: '3px' }}>
                        <span className={`badge ${getResultBadgeClass(selectedEvent.result)}`}>
                          {selectedEvent.result || 'Logged'}
                        </span>
                      </div>
                    </div>

                    <div className="kv-item">
                      <span className="kv-key">UTC ISO Timestamp</span>
                      <span className="font-mono" style={{ fontSize: '10.5px', color: 'var(--text-muted)' }}>
                        {selectedEvent.timestamp}
                      </span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Section: Cryptographic Verification */}
              <div className="panel-card">
                <div className="panel-card-header">
                  <span className="panel-card-title">
                    <Lock size={12} />
                    <span>Cryptographic Verification</span>
                  </span>
                  {selectedEvent.is_verified !== false ? (
                    <span className="badge badge-allow" style={{ fontSize: '10.5px' }}>
                      SHA-256 Valid
                    </span>
                  ) : (
                    <span className="badge badge-block" style={{ fontSize: '10.5px' }}>
                      Hash Mismatch
                    </span>
                  )}
                </div>
                <div className="panel-card-body" style={{ gap: '10px' }}>
                  <div
                    style={{
                      padding: '8px 10px',
                      borderRadius: '5px',
                      backgroundColor:
                        selectedEvent.is_verified !== false ? 'var(--status-allow-bg)' : 'var(--status-block-bg)',
                      border: `1px solid ${
                        selectedEvent.is_verified !== false ? 'var(--status-allow-border)' : 'var(--status-block-border)'
                      }`,
                      fontSize: '11px',
                      color:
                        selectedEvent.is_verified !== false ? 'var(--status-allow-text)' : 'var(--status-block-text)',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '6px',
                    }}
                  >
                    {selectedEvent.is_verified !== false ? (
                      <>
                        <ShieldCheck size={14} color="#059669" />
                        <span>
                          <strong>Parent-Child Chain Verified:</strong> SHA-256(Parent + Payload) perfectly equals the
                          Event Hash.
                        </span>
                      </>
                    ) : (
                      <>
                        <AlertOctagon size={14} color="#dc2626" />
                        <span>
                          <strong>Chain Integrity Broken:</strong> Payload tampering or parent hash discontinuity
                          detected!
                        </span>
                      </>
                    )}
                  </div>

                  {/* Parent Hash */}
                  <div className="kv-item">
                    <span className="kv-key">Previous Event Parent Hash</span>
                    <div className="hash-badge-container" style={{ marginTop: '3px' }}>
                      <span
                        className="font-mono"
                        style={{
                          fontSize: '11px',
                          color: selectedEvent.parent_hash === 'GENESIS' ? '#059669' : 'var(--text-secondary)',
                          fontWeight: selectedEvent.parent_hash === 'GENESIS' ? 600 : 400,
                        }}
                      >
                        {selectedEvent.parent_hash === 'GENESIS'
                          ? 'GENESIS (Initial Seed)'
                          : `${selectedEvent.parent_hash.substring(0, 16)}...${selectedEvent.parent_hash.substring(
                              selectedEvent.parent_hash.length - 8
                            )}`}
                      </span>
                      <button
                        className="btn btn-secondary"
                        onClick={() => handleCopy(selectedEvent.parent_hash, 'parentHash')}
                        style={{ padding: '2px 6px', height: '20px', fontSize: '10px' }}
                        title="Copy full Parent Hash"
                      >
                        {copiedKey === 'parentHash' ? (
                          <Check size={11} color="#059669" />
                        ) : (
                          <Copy size={11} />
                        )}
                      </button>
                    </div>
                  </div>

                  {/* Current Event Hash */}
                  <div className="kv-item">
                    <span className="kv-key">Current Event Hash (Deterministic Digest)</span>
                    <div className="hash-badge-container" style={{ marginTop: '3px' }}>
                      <span
                        className="font-mono"
                        style={{
                          fontSize: '11px',
                          color: 'var(--signal-blue)',
                          fontWeight: 600,
                        }}
                      >
                        {`${selectedEvent.event_hash.substring(0, 16)}...${selectedEvent.event_hash.substring(
                          selectedEvent.event_hash.length - 8
                        )}`}
                      </span>
                      <button
                        className="btn btn-secondary"
                        onClick={() => handleCopy(selectedEvent.event_hash, 'eventHash')}
                        style={{ padding: '2px 6px', height: '20px', fontSize: '10px' }}
                        title="Copy full Event Hash"
                      >
                        {copiedKey === 'eventHash' ? (
                          <Check size={11} color="#059669" />
                        ) : (
                          <Copy size={11} />
                        )}
                      </button>
                    </div>
                  </div>

                  {/* Quick Chain Navigation */}
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      marginTop: '6px',
                      paddingTop: '8px',
                      borderTop: '1px solid var(--border-light)',
                    }}
                  >
                    <button
                      className="btn btn-secondary"
                      onClick={handlePrevEvent}
                      disabled={currentChainIndex <= 0}
                      style={{ fontSize: '11px', height: '26px' }}
                    >
                      <ChevronLeft size={12} />
                      <span>Previous in Chain</span>
                    </button>

                    <span style={{ fontSize: '10.5px', color: 'var(--text-muted)' }}>
                      Record {currentChainIndex + 1} of {events.length}
                    </span>

                    <button
                      className="btn btn-secondary"
                      onClick={handleNextEvent}
                      disabled={currentChainIndex >= events.length - 1}
                      style={{ fontSize: '11px', height: '26px' }}
                    >
                      <span>Next in Chain</span>
                      <ChevronRight size={12} />
                    </button>
                  </div>
                </div>
              </div>

              {/* Section: Original Event Payload */}
              <div className="panel-card">
                <div className="panel-card-header">
                  <span className="panel-card-title">Original Event Payload</span>
                  <button
                    className="btn btn-secondary"
                    onClick={() => handleCopy(JSON.stringify(selectedEvent.payload, null, 2), 'payload')}
                    style={{ padding: '2px 7px', height: '22px', fontSize: '10.5px' }}
                    title="Copy JSON Payload"
                  >
                    {copiedKey === 'payload' ? (
                      <>
                        <Check size={11} color="#059669" />
                        <span>Copied</span>
                      </>
                    ) : (
                      <>
                        <Copy size={11} />
                        <span>Copy JSON</span>
                      </>
                    )}
                  </button>
                </div>
                <div className="panel-card-body" style={{ padding: '10px' }}>
                  <details className="code-details" open>
                    <summary style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
                      Payload Content ({selectedEvent.payload ? Object.keys(selectedEvent.payload).length : 0} keys)
                    </summary>
                    <pre
                      className="code-block"
                      style={{
                        marginTop: '6px',
                        maxHeight: '220px',
                        overflowY: 'auto',
                        fontSize: '11px',
                      }}
                    >
                      {JSON.stringify(selectedEvent.payload, null, 2)}
                    </pre>
                  </details>
                </div>
              </div>

              {/* Section: Related Dispute Timeline */}
              <div className="panel-card">
                <div
                  className="panel-card-header"
                  style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span className="panel-card-title">Related Dispute Lifecycle</span>
                    <span className="badge badge-neutral" style={{ fontSize: '10.5px' }}>
                      {lifecycleEvents.length} Event{lifecycleEvents.length !== 1 ? 's' : ''}
                    </span>
                  </div>

                  {lifecycleEvents.length > 2 && (
                    <button
                      className="btn btn-secondary"
                      onClick={() => setGroupRepeated(!groupRepeated)}
                      style={{ height: '22px', fontSize: '10px', padding: '1px 7px', gap: '4px' }}
                      title={groupRepeated ? 'Show every event individually' : 'Group repeated consecutive operations'}
                    >
                      <Layers size={10} />
                      <span>{groupRepeated ? 'Show All' : 'Group Similar'}</span>
                    </button>
                  )}
                </div>

                <div className="panel-card-body">
                  <div
                    style={{
                      fontSize: '11.5px',
                      color: 'var(--text-muted)',
                      marginBottom: '8px',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                    }}
                  >
                    <span>
                      Operational timeline for{' '}
                      <strong className="font-mono" style={{ color: 'var(--signal-blue)' }}>
                        {selectedEvent.dispute_id}
                      </strong>
                      :
                    </span>
                    {lifecycleLoading && (
                      <span style={{ fontSize: '10.5px', color: 'var(--text-muted)' }}>Refreshing...</span>
                    )}
                  </div>

                  {dateSections.length === 0 ? (
                    <div style={{ padding: '16px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '11.5px' }}>
                      No lifecycle events recorded for this dispute.
                    </div>
                  ) : (
                    <div className="audit-timeline">
                      {dateSections.map((section) => (
                        <div key={section.dateKey} style={{ marginBottom: '8px' }}>
                          {/* Date Divider */}
                          <div className="timeline-date-header">
                            <Calendar size={11} color="var(--text-muted)" />
                            <span>{section.dateKey}</span>
                            <span className="timeline-date-count">
                              {section.items.reduce(
                                (acc, it) => acc + (it.type === 'group' ? it.events.length : 1),
                                0
                              )}{' '}
                              events
                            </span>
                          </div>

                          {/* Items under this date */}
                          {section.items.map((item) => {
                            if (item.type === 'group') {
                              const isExpanded = Boolean(expandedGroups[item.id]);
                              const hasActiveInside = item.events.some((e) => e.event_id === selectedEventId);
                              const shouldShowExpanded = isExpanded || hasActiveInside;

                              return (
                                <div key={item.id} style={{ marginBottom: '4px' }}>
                                  <div
                                    className={`timeline-group-header ${hasActiveInside ? 'active' : ''}`}
                                    onClick={() =>
                                      setExpandedGroups((prev) => ({
                                        ...prev,
                                        [item.id]: !shouldShowExpanded,
                                      }))
                                    }
                                  >
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                                      <span
                                        className={`badge ${getEventTypeBadgeClass(item.eventType)}`}
                                        style={{ fontSize: '10px' }}
                                      >
                                        {getEventTypeLabel(item.eventType)} ({item.events.length}×)
                                      </span>
                                      <span style={{ fontSize: '10.5px', color: 'var(--text-secondary)' }}>
                                        {getActorLabel(item.actor)}
                                      </span>
                                    </div>

                                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                                      <span style={{ fontSize: '10px', color: 'var(--text-muted)' }}>
                                        {getEventTimeStr(item.firstTimestamp)} – {getEventTimeStr(item.lastTimestamp)}
                                      </span>
                                      {shouldShowExpanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                                    </div>
                                  </div>

                                  {shouldShowExpanded && (
                                    <div className="timeline-group-nested">
                                      {item.events.map((gEvt) => renderTimelineEventItem(gEvt))}
                                    </div>
                                  )}
                                </div>
                              );
                            }

                            return renderTimelineEventItem(item.event);
                          })}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
