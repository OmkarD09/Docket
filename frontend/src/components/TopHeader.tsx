import React from 'react';
import { ChevronRight, LogOut, ShieldCheck, AlertOctagon, Loader2, AlertCircle } from 'lucide-react';
import type { NavSection } from './Sidebar';
import type { AuthenticatedMerchant, SyncStatusData, AuditStatusData } from '../types';

interface TopHeaderProps {
  activeSection: NavSection;
  selectedDisputeId?: string | null;
  currentUser?: AuthenticatedMerchant | null;
  onSignOut?: () => void;
  syncStatus?: SyncStatusData | null;
  auditStatus?: AuditStatusData | null;
}

function formatRelativeSyncTime(isoString: string | null | undefined): string {
  if (!isoString) return 'never';
  try {
    const diffMs = Date.now() - new Date(isoString).getTime();
    if (diffMs < 0) return 'just now';
    const diffSec = Math.floor(diffMs / 1000);
    if (diffSec < 10) return 'just now';
    if (diffSec < 60) return `${diffSec}s ago`;
    const diffMin = Math.floor(diffSec / 60);
    if (diffMin < 60) return `${diffMin}m ago`;
    const diffHour = Math.floor(diffMin / 60);
    return `${diffHour}h ago`;
  } catch {
    return 'recently';
  }
}

export const TopHeader: React.FC<TopHeaderProps> = ({
  activeSection,
  selectedDisputeId,
  currentUser,
  onSignOut,
  syncStatus,
  auditStatus,
}) => {
  const getSectionMetadata = () => {
    switch (activeSection) {
      case 'overview':
        return {
          title: 'Operations Overview',
          crumb: 'Docket',
          subCrumb: 'Operations',
        };
      case 'disputes':
        return {
          title: selectedDisputeId ? `Dispute Workspace: ${selectedDisputeId}` : 'Dispute Workspace',
          crumb: 'Docket',
          subCrumb: 'Disputes',
          leaf: selectedDisputeId || undefined,
        };
      case 'audit':
        return {
          title: 'Audit Trail & Integrity Ledger',
          crumb: 'Docket',
          subCrumb: 'Compliance',
          leaf: 'Audit Trail',
        };
      case 'benchmark':
        return {
          title: 'Benchmark Scorecard 2.0',
          crumb: 'Docket',
          subCrumb: 'Verification',
          leaf: 'Benchmarks',
        };
      default:
        return {
          title: 'Dispute Operations',
          crumb: 'Docket',
          subCrumb: 'Operations',
        };
    }
  };

  const meta = getSectionMetadata();

  // 1. PayPal Sync Indicator Presentation
  const getPayPalIndicatorConfig = () => {
    if (!syncStatus) {
      return {
        bg: 'var(--bg-subtle)',
        border: 'var(--border-subtle)',
        color: 'var(--text-secondary)',
        dotColor: '#059669',
        isSpinning: false,
        label: 'PayPal Sandbox',
        subtext: 'Connecting...',
        tooltip: 'Connecting to PayPal Sandbox REST API...',
      };
    }

    switch (syncStatus.status) {
      case 'SYNCING':
        return {
          bg: 'rgba(217, 119, 6, 0.08)',
          border: 'rgba(217, 119, 6, 0.25)',
          color: '#B45309',
          dotColor: '#D97706',
          isSpinning: true,
          label: 'PayPal Sandbox',
          subtext: 'Syncing...',
          tooltip: `Automated dispute reconciliation in progress. Last synced: ${syncStatus.last_successful_sync || 'pending'}`,
        };
      case 'UP_TO_DATE':
      case 'CONNECTED':
        return {
          bg: 'rgba(5, 150, 105, 0.08)',
          border: 'rgba(5, 150, 105, 0.22)',
          color: '#047857',
          dotColor: '#059669',
          isSpinning: false,
          label: 'PayPal Sandbox',
          subtext: `Synced ${formatRelativeSyncTime(syncStatus.last_successful_sync)}`,
          tooltip: `PayPal Sandbox connected & up-to-date (${syncStatus.reconciled_records} reconciled records). Environment: ${syncStatus.environment}. Interval: ${syncStatus.interval_seconds}s.`,
        };
      case 'DELAYED':
        return {
          bg: 'rgba(217, 119, 6, 0.08)',
          border: 'rgba(217, 119, 6, 0.25)',
          color: '#B45309',
          dotColor: '#D97706',
          isSpinning: false,
          label: 'PayPal Sandbox',
          subtext: 'Reconciliation Delayed',
          tooltip: `Sync delayed: ${syncStatus.error_summary || 'Retrying with backoff'}. Last successful: ${syncStatus.last_successful_sync || 'never'}.`,
        };
      case 'FAILED':
      default:
        return {
          bg: 'rgba(220, 38, 38, 0.08)',
          border: 'rgba(220, 38, 38, 0.25)',
          color: '#B91C1C',
          dotColor: '#DC2626',
          isSpinning: false,
          label: 'PayPal Sandbox',
          subtext: 'Sync Failure',
          tooltip: `Sync failed: ${syncStatus.error_summary || 'Connection error'}. Consecutive failures: ${syncStatus.consecutive_failures}`,
        };
    }
  };

  // 2. Audit Chain Verification Indicator Presentation
  const getAuditIndicatorConfig = () => {
    if (!auditStatus) {
      return {
        bg: 'var(--bg-subtle)',
        border: 'var(--border-subtle)',
        color: 'var(--text-secondary)',
        isSpinning: false,
        icon: ShieldCheck,
        iconColor: '#059669',
        label: 'Ledger',
        subtext: 'Verifying...',
        tooltip: 'Initializing continuous audit verification...',
      };
    }

    switch (auditStatus.status) {
      case 'VERIFYING':
        return {
          bg: 'rgba(217, 119, 6, 0.08)',
          border: 'rgba(217, 119, 6, 0.25)',
          color: '#B45309',
          isSpinning: true,
          icon: Loader2,
          iconColor: '#D97706',
          label: 'Ledger',
          subtext: 'Verifying...',
          tooltip: `Verifying full SHA-256 chain across ${auditStatus.total_events} SQLite records...`,
        };
      case 'VERIFIED':
        return {
          bg: 'rgba(5, 150, 105, 0.08)',
          border: 'rgba(5, 150, 105, 0.22)',
          color: '#047857',
          isSpinning: false,
          icon: ShieldCheck,
          iconColor: '#059669',
          label: 'Ledger Intact',
          subtext: `${auditStatus.verified_events} verified`,
          tooltip: `SHA-256 audit ledger continuously verified: ${auditStatus.verified_events} / ${auditStatus.total_events} intact events. Last checked: ${auditStatus.last_verified_at || 'just now'}. ${auditStatus.tail_truncation_notice}`,
        };
      case 'INTEGRITY_WARNING':
        return {
          bg: 'rgba(217, 119, 6, 0.08)',
          border: 'rgba(217, 119, 6, 0.25)',
          color: '#B45309',
          isSpinning: false,
          icon: AlertCircle,
          iconColor: '#D97706',
          label: 'Ledger Warning',
          subtext: `${auditStatus.failed_events} alert`,
          tooltip: `Integrity warning: ${auditStatus.error_details || 'Verification anomaly detected'}`,
        };
      case 'VERIFICATION_FAILED':
      default:
        return {
          bg: 'rgba(220, 38, 38, 0.08)',
          border: 'rgba(220, 38, 38, 0.25)',
          color: '#B91C1C',
          isSpinning: false,
          icon: AlertOctagon,
          iconColor: '#DC2626',
          label: 'Ledger Compromised',
          subtext: `${auditStatus.failed_events} failed`,
          tooltip: `CRITICAL: Audit chain verification failed! Sensitive operations gated. Error: ${auditStatus.error_details}`,
        };
    }
  };

  const ppConfig = getPayPalIndicatorConfig();
  const auditConfig = getAuditIndicatorConfig();
  const AuditIcon = auditConfig.icon;

  return (
    <header className="top-header">
      <div className="header-left">
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1px' }}>
          <div className="breadcrumb-label">
            <span>{meta.crumb}</span>
            <ChevronRight size={10} color="var(--text-tertiary)" />
            <span>{meta.subCrumb}</span>
            {meta.leaf && (
              <>
                <ChevronRight size={10} color="var(--text-tertiary)" />
                <span style={{ color: 'var(--text-secondary)', fontWeight: 600 }}>{meta.leaf}</span>
              </>
            )}
          </div>
          <h1 className="page-title">{meta.title}</h1>
        </div>
      </div>

      <div className="header-actions">
        {/* 1. Automated PayPal Synchronisation Live Indicator */}
        <div
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '7px',
            padding: '4px 10px',
            borderRadius: '5px',
            backgroundColor: ppConfig.bg,
            border: `1px solid ${ppConfig.border}`,
            fontSize: '11px',
            color: ppConfig.color,
            fontWeight: 500,
            cursor: 'default',
            userSelect: 'none',
            transition: 'all 0.15s ease',
          }}
          title={ppConfig.tooltip}
        >
          {ppConfig.isSpinning ? (
            <Loader2 size={11} className="spin" color={ppConfig.dotColor} />
          ) : (
            <span
              style={{
                width: '6px',
                height: '6px',
                borderRadius: '50%',
                backgroundColor: ppConfig.dotColor,
                boxShadow: `0 0 0 2px ${ppConfig.dotColor}33`,
              }}
            />
          )}
          <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
            <span style={{ fontWeight: 600 }}>{ppConfig.label}</span>
            <span style={{ opacity: 0.8, fontSize: '10.5px' }}>· {ppConfig.subtext}</span>
          </div>
        </div>

        {/* 2. Automated Continuous Audit Integrity Live Indicator */}
        <div
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '6px',
            padding: '4px 10px',
            borderRadius: '5px',
            backgroundColor: auditConfig.bg,
            border: `1px solid ${auditConfig.border}`,
            fontSize: '11px',
            color: auditConfig.color,
            fontWeight: 500,
            cursor: 'default',
            userSelect: 'none',
            transition: 'all 0.15s ease',
          }}
          title={auditConfig.tooltip}
        >
          <AuditIcon size={12} className={auditConfig.isSpinning ? 'spin' : ''} color={auditConfig.iconColor} />
          <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
            <span style={{ fontWeight: 600 }}>{auditConfig.label}</span>
            <span style={{ opacity: 0.8, fontSize: '10.5px' }}>· {auditConfig.subtext}</span>
          </div>
        </div>

        {/* 3. Merchant Operator Profile & Sign Out */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '10px',
            paddingLeft: '12px',
            borderLeft: '1px solid var(--border-subtle)',
          }}
        >
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
            }}
            title={currentUser ? `Signed in as ${currentUser.display_name} (${currentUser.role})` : 'Merchant Principal'}
          >
            <div
              style={{
                width: '26px',
                height: '26px',
                borderRadius: '50%',
                backgroundColor: 'var(--accent-slate)',
                color: '#FFFFFF',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: '11px',
                fontWeight: 700,
                letterSpacing: '0.02em',
                boxShadow: '0 1px 2px rgba(15, 23, 42, 0.12)',
              }}
            >
              {currentUser
                ? currentUser.display_name
                    .split(' ')
                    .map((n) => n[0])
                    .slice(0, 2)
                    .join('')
                    .toUpperCase()
                : 'MO'}
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', lineHeight: 1.2 }}>
              <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-primary)' }}>
                {currentUser ? currentUser.display_name : 'Merchant Operator'}
              </span>
              <span
                style={{
                  fontSize: '9.5px',
                  color: 'var(--text-muted)',
                  fontFamily: 'var(--font-mono)',
                  letterSpacing: '0.02em',
                }}
              >
                {currentUser ? currentUser.role : 'OPERATIONS_LEAD'}
              </span>
            </div>
          </div>

          {onSignOut && (
            <button
              onClick={onSignOut}
              className="btn btn-secondary"
              style={{
                height: '26px',
                padding: '2px 8px',
                fontSize: '11px',
                gap: '5px',
                color: 'var(--text-secondary)',
              }}
              title="Sign out of Docket Command Desk and clear active session token"
            >
              <LogOut size={12} />
              <span>Sign Out</span>
            </button>
          )}
        </div>
      </div>
    </header>
  );
};
