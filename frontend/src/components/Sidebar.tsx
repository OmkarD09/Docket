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
      shortcut: '1',
      icon: <LayoutDashboard size={15} strokeWidth={2} />,
    },
    {
      id: 'disputes' as NavSection,
      label: 'Disputes',
      shortcut: '2',
      icon: <Layers size={15} strokeWidth={2} />,
      badge: disputeCount > 0 ? disputeCount : undefined,
    },
    {
      id: 'audit' as NavSection,
      label: 'Audit Trail',
      shortcut: '3',
      icon: <ShieldCheck size={15} strokeWidth={2} />,
    },
    {
      id: 'benchmark' as NavSection,
      label: 'Benchmark Scorecard',
      shortcut: '4',
      icon: <BarChart3 size={15} strokeWidth={2} />,
    },
  ];

  return (
    <aside className={`sidebar ${collapsed ? 'collapsed' : ''}`}>
      <div>
        {/* Brand Header */}
        <div className="sidebar-brand">
          <div className="brand-icon-box" title="Docket - Dispute Operations">
            <Scale size={15} strokeWidth={2.5} />
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
                <span
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    color: isActive ? 'var(--signal-blue)' : 'var(--text-muted)',
                    transition: 'color var(--transition-fast)',
                  }}
                >
                  {item.icon}
                </span>
                {!collapsed && (
                  <>
                    <span style={{ flex: 1, letterSpacing: '-0.01em' }}>{item.label}</span>
                    {item.badge !== undefined && (
                      <span className="nav-badge">{item.badge}</span>
                    )}
                    <span
                      style={{
                        fontSize: '10px',
                        color: 'var(--text-tertiary)',
                        fontFamily: 'var(--font-mono)',
                        marginLeft: item.badge === undefined ? 'auto' : '4px',
                        opacity: isActive ? 0.9 : 0.6,
                      }}
                    >
                      {item.shortcut}
                    </span>
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
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '6px 8px',
                borderRadius: '5px',
                backgroundColor: 'var(--bg-surface)',
                border: '1px solid var(--border-light)',
              }}
            >
              <div className="env-pill">
                <span className="env-indicator-dot" />
                <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-primary)' }}>
                  PayPal Sandbox
                </span>
              </div>
              <span
                style={{
                  fontSize: '9.5px',
                  fontWeight: 600,
                  color: 'var(--status-allow-text)',
                  backgroundColor: 'var(--status-allow-bg)',
                  padding: '1px 5px',
                  borderRadius: '3px',
                  border: '1px solid var(--status-allow-border)',
                }}
              >
                LIVE
              </span>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: '10.5px', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                v1.4.0 (Policy Ready)
              </span>
              <button
                onClick={onToggleCollapse}
                className="btn btn-secondary"
                style={{ padding: '2px 5px', height: '22px' }}
                title="Collapse sidebar"
              >
                <ChevronLeft size={12} />
              </button>
            </div>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '8px' }}>
            <span className="env-indicator-dot" title="PayPal Sandbox: Live" />
            <button
              onClick={onToggleCollapse}
              className="btn btn-secondary"
              style={{ padding: '2px 5px', height: '22px' }}
              title="Expand sidebar"
            >
              <ChevronRight size={12} />
            </button>
          </div>
        )}
      </div>
    </aside>
  );
};

