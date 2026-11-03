import React from 'react';
import {
  Scale,
  LayoutDashboard,
  Layers,
  ShieldCheck,
  BarChart3,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';

export type NavSection = 'overview' | 'disputes' | 'audit' | 'benchmark';

interface SidebarProps {
  activeSection: NavSection;
  onSelectSection: (section: NavSection) => void;
  collapsed: boolean;
  onToggleCollapse: () => void;
  disputeCount: number;
}

export const Sidebar: React.FC<SidebarProps> = ({
  activeSection,
  onSelectSection,
  collapsed,
  onToggleCollapse,
  disputeCount,
}) => {
  const navItems = [
    {
      id: 'overview' as NavSection,
      label: 'Overview',
      icon: <LayoutDashboard size={16} strokeWidth={2} />,
    },
    {
      id: 'disputes' as NavSection,
      label: 'Disputes',
      icon: <Layers size={16} strokeWidth={2} />,
      badge: disputeCount > 0 ? disputeCount : undefined,
    },
    {
      id: 'audit' as NavSection,
      label: 'Audit Ledger',
      icon: <ShieldCheck size={16} strokeWidth={2} />,
    },
    {
      id: 'benchmark' as NavSection,
      label: 'Benchmark Scorecard',
      icon: <BarChart3 size={16} strokeWidth={2} />,
    },
  ];

  return (
    <aside className={`sidebar ${collapsed ? 'collapsed' : ''}`}>
      <div>
        {/* Brand Header */}
        <div className="sidebar-brand">
          <div className="brand-icon-box" title="Docket - Dispute Operations">
            <Scale size={16} strokeWidth={2.5} />
          </div>
          {!collapsed && (
            <div className="brand-text-block">
              <span className="brand-name">DOCKET</span>
              <span className="brand-descriptor">Dispute Operations</span>
            </div>
          )}
        </div>

        {/* Primary Navigation */}
        <nav className="sidebar-nav">
          {navItems.map((item) => {
            const isActive = activeSection === item.id;
            return (
              <button
                key={item.id}
                onClick={() => onSelectSection(item.id)}
                className={`nav-link ${isActive ? 'active' : ''}`}
                title={collapsed ? item.label : undefined}
              >
                <span style={{ display: 'flex', alignItems: 'center', color: isActive ? 'var(--signal-blue)' : 'inherit' }}>
                  {item.icon}
                </span>
                {!collapsed && (
                  <>
                    <span>{item.label}</span>
                    {item.badge !== undefined && (
                      <span className="nav-badge">{item.badge}</span>
                    )}
                  </>
                )}
              </button>
            );
          })}
        </nav>
      </div>

      {/* Footer & Environment Status */}
      <div className="sidebar-footer">
        {!collapsed ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <div className="env-pill">
              <span className="env-indicator-dot" />
              <span>PayPal Sandbox: Live</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: '10.5px', color: 'var(--text-muted)' }}>v1.4.0 (Policy Ready)</span>
              <button
                onClick={onToggleCollapse}
                className="btn btn-secondary"
                style={{ padding: '3px 6px', height: '24px' }}
                title="Collapse sidebar"
              >
                <ChevronLeft size={13} />
              </button>
            </div>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '8px' }}>
            <span className="env-indicator-dot" title="PayPal Sandbox: Live" />
            <button
              onClick={onToggleCollapse}
              className="btn btn-secondary"
              style={{ padding: '3px 6px', height: '24px' }}
              title="Expand sidebar"
            >
              <ChevronRight size={13} />
            </button>
          </div>
        )}
      </div>
    </aside>
  );
};
