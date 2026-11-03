import React from 'react';
import { RefreshCw } from 'lucide-react';
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
  const getSectionTitle = () => {
    switch (activeSection) {
      case 'overview':
        return 'Overview';
      case 'disputes':
        return selectedDisputeId ? `Dispute Workspace: ${selectedDisputeId}` : 'Dispute Workspace';
      case 'audit':
        return 'Cryptographic Audit Ledger';
      case 'benchmark':
        return 'Benchmark Scorecard (20 Scenarios)';
      default:
        return 'Dispute Operations';
    }
  };

  const getBreadcrumb = () => {
    switch (activeSection) {
      case 'overview':
        return 'Docket / Operations';
      case 'disputes':
        return selectedDisputeId ? `Docket / Disputes / ${selectedDisputeId}` : 'Docket / Disputes';
      case 'audit':
        return 'Docket / Compliance / Audit Trail';
      case 'benchmark':
        return 'Docket / Verification / Benchmarks';
      default:
        return 'Docket';
    }
  };

  return (
    <header className="top-header">
      <div className="header-left">
        <div>
          <div className="breadcrumb-label">{getBreadcrumb()}</div>
          <h1 className="page-title">{getSectionTitle()}</h1>
        </div>
      </div>

      <div className="header-actions">
        <div
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '6px',
            padding: '4px 10px',
            borderRadius: '6px',
            backgroundColor: 'var(--bg-subtle)',
            border: '1px solid var(--border-subtle)',
            fontSize: '11px',
            color: 'var(--text-secondary)',
            fontWeight: 500,
          }}
          title="Direct REST API connection to api-m.sandbox.paypal.com"
        >
          <span style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: '#059669' }} />
          <span>PayPal Sandbox Active</span>
        </div>

        <button
          onClick={onRefresh}
          className="btn btn-secondary"
          style={{ height: '30px', padding: '4px 10px', fontSize: '11.5px' }}
          disabled={loading}
          title="Sync dispute records with backend"
        >
          <RefreshCw size={12} className={loading ? 'spin' : ''} />
          <span>Sync State</span>
        </button>
      </div>
    </header>
  );
};
