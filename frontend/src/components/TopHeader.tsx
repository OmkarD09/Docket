import React from 'react';
import { RefreshCw, ChevronRight } from 'lucide-react';
import type { NavSection } from './Sidebar';

interface TopHeaderProps {
  activeSection: NavSection;
  selectedDisputeId?: string | null;
  onRefresh: () => void;
  loading: boolean;
}

export const TopHeader: React.FC<TopHeaderProps> = ({
  activeSection,
  selectedDisputeId,
  onRefresh,
  loading,
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
          subCrumb: selectedDisputeId ? 'Disputes' : 'Disputes',
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
        {/* PayPal Sandbox Status Badge */}
        <div
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '6px',
            padding: '4px 10px',
            borderRadius: '5px',
            backgroundColor: 'var(--bg-subtle)',
            border: '1px solid var(--border-subtle)',
            fontSize: '11px',
            color: 'var(--text-secondary)',
            fontWeight: 500,
          }}
          title="Direct connection to api-m.sandbox.paypal.com (Merchant sandbox verified)"
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
          <span>PayPal Sandbox (REST v1)</span>
        </div>

        {/* Sync Button */}
        <button
          onClick={onRefresh}
          className="btn btn-secondary"
          style={{ height: '30px', padding: '4px 10px', fontSize: '11.5px', gap: '6px' }}
          disabled={loading}
          title="Synchronize dispute records and audit integrity state with backend"
        >
          <RefreshCw size={12} className={loading ? 'spin' : ''} />
          <span>Sync State</span>
        </button>

        {/* Merchant Operator Profile */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            paddingLeft: '10px',
            borderLeft: '1px solid var(--border-subtle)',
            height: '24px',
          }}
          title="Signed in as Merchant Operations Primary (HMAC Supervisor)"
        >
          <div
            style={{
              width: '24px',
              height: '24px',
              borderRadius: '50%',
              backgroundColor: 'var(--accent-slate)',
              color: '#FFFFFF',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: '10.5px',
              fontWeight: 700,
              letterSpacing: '0.02em',
            }}
          >
            MO
          </div>
        </div>
      </div>
    </header>
  );
};

