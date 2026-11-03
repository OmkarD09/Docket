import React, { useMemo } from 'react';
import { AgGridReact } from 'ag-grid-react';
import { AllCommunityModule, ModuleRegistry, themeQuartz } from 'ag-grid-community';
import type { ColDef, RowSelectedEvent } from 'ag-grid-community';
import { ShieldAlert, CheckCircle2, AlertTriangle, XCircle } from 'lucide-react';
import type { DisputeSummary } from '../types';

// Register AG Grid Community Modules
ModuleRegistry.registerModules([AllCommunityModule]);

// AG Grid Custom Theme using v36 Design System Theme API - Editorial Light Mode
const docketLightTheme = themeQuartz.withParams({
  backgroundColor: '#ffffff',
  foregroundColor: '#0f172a',
  headerBackgroundColor: '#f8f9fa',
  headerTextColor: '#475569',
  oddRowBackgroundColor: '#ffffff',
  borderColor: '#e2e8f0',
  accentColor: '#0f172a',
  rowHoverColor: '#f8fafc',
  fontSize: 13,
  fontFamily: "'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
  headerFontSize: 12,
  headerFontWeight: 600,
  rowHeight: 46,
  headerHeight: 40,
});

interface DisputeTableProps {
  disputes: DisputeSummary[];
  selectedDisputeId: string | null;
  onSelectDispute: (disputeId: string) => void;
}

export const DisputeTable: React.FC<DisputeTableProps> = ({
  disputes,
  selectedDisputeId,
  onSelectDispute,
}) => {
  // Column Definitions
  const colDefs = useMemo<ColDef<DisputeSummary>[]>(() => {
    return [
      {
        headerName: 'Dispute Reference',
        field: 'dispute_id',
        width: 180,
        pinned: 'left',
        cellRenderer: (params: any) => {
          const d: DisputeSummary = params.data;
          if (!d) return null;
          const isSelected = d.dispute_id === selectedDisputeId;
          return (
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', height: '100%' }}>
              {d.has_prompt_threat && (
                <span title="Adversarial prompt injection quarantined by Docket Security Guard">
                  <ShieldAlert size={13} color="#dc2626" />
                </span>
              )}
              <span
                className="font-mono"
                style={{
                  fontWeight: 600,
                  fontSize: '11.5px',
                  color: isSelected ? '#0f172a' : '#1e293b',
                  letterSpacing: '-0.01em',
                }}
              >
                {d.dispute_id}
              </span>
            </div>
          );
        },
      },
      {
        headerName: 'Origin',
        width: 115,
        cellRenderer: (params: any) => {
          const d: DisputeSummary = params.data;
          if (!d) return null;
          const isReal = d.dispute_id === 'PP-R-NKI-10193390' || (d.scenario_id && d.scenario_id.includes('REAL_SANDBOX'));
          if (isReal) {
            return (
              <span
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '4px',
                  padding: '2px 7px',
                  borderRadius: '4px',
                  fontSize: '10.5px',
                  fontWeight: 600,
                  backgroundColor: '#ecfdf5',
                  color: '#065f46',
                  border: '1px solid #a7f3d0',
                }}
              >
                <span style={{ width: '5px', height: '5px', borderRadius: '50%', backgroundColor: '#059669' }} />
                Live Sandbox
              </span>
            );
          }
          return (
            <span
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                padding: '2px 7px',
                borderRadius: '4px',
                fontSize: '10.5px',
                fontWeight: 500,
                backgroundColor: '#f1f5f9',
                color: '#475569',
                border: '1px solid #e2e8f0',
              }}
            >
              Benchmark
            </span>
          );
        },
      },
      {
        headerName: 'Dispute Reason',
        field: 'reason',
        minWidth: 160,
        flex: 1,
        cellRenderer: (params: any) => {
          const raw = params.value || '';
          const readable = raw
            .replace(/_/g, ' ')
            .toLowerCase()
            .replace(/\b\w/g, (c: string) => c.toUpperCase());
          return <span style={{ color: '#334155', fontWeight: 500, fontSize: '12px' }}>{readable}</span>;
        },
      },
      {
        headerName: 'Amount',
        field: 'amount',
        width: 110,
        headerClass: 'ag-right-aligned-header',
        cellRenderer: (params: any) => {
          const d = params.data;
          if (!d) return null;
          return (
            <div style={{ textAlign: 'right', width: '100%' }}>
              <span className="font-mono" style={{ fontWeight: 600, color: '#0f172a', fontSize: '12px' }}>
                ${d.amount}
              </span>
              <span style={{ fontSize: '10.5px', color: '#64748b', marginLeft: '3px' }}>
                {d.currency}
              </span>
            </div>
          );
        },
      },
      {
        headerName: 'PayPal Status',
        field: 'status',
        width: 165,
        cellRenderer: (params: any) => {
          const val = params.value || '';
          let label = val.replace(/_/g, ' ').toLowerCase().replace(/\b\w/g, (c: string) => c.toUpperCase());
          let style: React.CSSProperties = {
            padding: '2px 7px',
            borderRadius: '4px',
            fontSize: '10.5px',
            fontWeight: 500,
            display: 'inline-block',
          };

          if (val === 'WAITING_FOR_SELLER_RESPONSE') {
            label = 'Waiting Response';
            style = {
              ...style,
              backgroundColor: '#eff6ff',
              color: '#1e40af',
              border: '1px solid #bfdbfe',
              fontWeight: 600,
            };
          } else if (val === 'RESOLVED') {
            style = {
              ...style,
              backgroundColor: '#f8fafc',
              color: '#64748b',
              border: '1px solid #e2e8f0',
            };
          } else {
            style = {
              ...style,
              backgroundColor: '#f1f5f9',
              color: '#475569',
              border: '1px solid #e2e8f0',
            };
          }

          return <span style={style}>{label}</span>;
        },
      },
      {
        headerName: 'Docket Policy',
        field: 'overall_decision',
        width: 110,
        cellRenderer: (params: any) => {
          const dec = params.value;
          if (dec === 'ALLOW') {
            return (
              <span className="badge badge-allow">
                <CheckCircle2 size={11} /> ALLOW
              </span>
            );
          }
          if (dec === 'BLOCK') {
            return (
              <span className="badge badge-block">
                <XCircle size={11} /> BLOCK
              </span>
            );
          }
          return (
            <span className="badge badge-review">
              <AlertTriangle size={11} /> REVIEW
            </span>
          );
        },
      },
      {
        headerName: 'Evidence & Invariant Assessment',
        field: 'violated_invariants',
        minWidth: 170,
        flex: 1.2,
        cellRenderer: (params: any) => {
          const d: DisputeSummary = params.data;
          if (!d) return null;

          const hasInvariants = d.violated_invariants && d.violated_invariants.length > 0;
          const hasDiscrepancies = d.discrepancies && d.discrepancies.length > 0;

          if (!hasInvariants && !hasDiscrepancies) {
            return (
              <span style={{ color: '#059669', fontSize: '11px', fontStyle: 'italic', display: 'flex', alignItems: 'center', gap: '3px' }}>
                <CheckCircle2 size={11} /> Verified proof complete
              </span>
            );
          }

          const items = [...(d.violated_invariants || []), ...(d.discrepancies || [])].slice(0, 2);
          return (
            <div style={{ display: 'flex', alignItems: 'center', gap: '4px', overflow: 'hidden' }}>
              {items.map((it, idx) => {
                const label = it
                  .replace('RULE_', '')
                  .replace(/_/g, ' ')
                  .toLowerCase()
                  .replace(/\b\w/g, (c) => c.toUpperCase());
                return (
                  <span
                    key={idx}
                    style={{
                      fontSize: '10px',
                      padding: '2px 5px',
                      borderRadius: '3px',
                      backgroundColor: '#fef2f2',
                      color: '#991b1b',
                      border: '1px solid #fecaca',
                      whiteSpace: 'nowrap',
                      maxWidth: '110px',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                    }}
                    title={it}
                  >
                    {label}
                  </span>
                );
              })}
              {d.violated_invariants.length > 2 && (
                <span style={{ fontSize: '10px', color: '#64748b' }}>
                  +{d.violated_invariants.length - 2}
                </span>
              )}
            </div>
          );
        },
      },
    ];
  }, [selectedDisputeId]);

  const defaultColDef = useMemo<ColDef>(() => {
    return {
      sortable: true,
      filter: true,
      resizable: true,
    };
  }, []);

  const onRowSelected = (event: RowSelectedEvent<DisputeSummary>) => {
    if (event.node.isSelected() && event.data) {
      onSelectDispute(event.data.dispute_id);
    }
  };

  return (
    <div style={{ width: '100%', height: '100%' }}>
      <AgGridReact<DisputeSummary>
        theme={docketLightTheme}
        rowData={disputes}
        columnDefs={colDefs}
        defaultColDef={defaultColDef}
        rowSelection={{ mode: 'singleRow', checkboxes: false, enableClickSelection: true }}
        onRowSelected={onRowSelected}
        animateRows={false}
      />
    </div>
  );
};
