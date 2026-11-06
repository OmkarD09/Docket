# Docket — Design System & Specification
## Benchmark Scorecard 2.0: Financial Analytics & Policy Evaluation Workspace

**Product:** DOCKET  
**Descriptor:** Evidence-backed AI for PayPal disputes.  
**Design Identity:** Graphite & Signal Blue.  
**Core Design Philosophy:** **SHOW LESS INITIALLY. REVEAL MORE WHEN NEEDED.**

---

## 1. Product Identity & Design Principles

Docket is an evidence-reconciliation and deterministic policy enforcement platform for merchant dispute operations. It is designed for finance, risk, and operations teams who demand precision, mathematical accountability, and high information density.

### Principles:
1. **Precise and Trustworthy:** Financial operations depend on auditability. No approximate numbers, fake metric percentages, or decorative badges.
2. **Minimal and Data-Oriented:** Avoid generic dark AI dashboards, glowing borders, gradients, and glassmorphism. White and neutral surfaces provide visual calm.
3. **Restrained Semantic Palette:** Green (`ALLOW`), Amber (`REVIEW`), and Red (`BLOCK` / `THREAT`) are reserved exclusively for actual policy evaluation outcomes and cryptographic verification results. They are never used for decorative accents.
4. **Information-Dense but Breathable:** Compact rows with 32–36px height, tabular numerals, proper column proportions, and on-demand drawers instead of permanently crowded split views.

---

## 2. Official Color Palette & Design Tokens

### Canvas & Surfaces
| Token | Hex | Role |
| :--- | :--- | :--- |
| `--bg-canvas` | `#F8F9FA` | Main application background canvas |
| `--bg-surface` | `#FFFFFF` | Primary surface for cards, panels, and drawer |
| `--bg-subtle` | `#F1F5F9` | Subtle background for nested controls and code excerpts |
| `--bg-header` | `#FAFBFC` | Headers, table column headers, and toolbars |
| `--bg-hover` | `#F8FAFC` | Interactive row and button hover state |

### Typography
| Token | Hex | Role |
| :--- | :--- | :--- |
| `--text-primary` | `#0F172A` | Primary text: Headings, IDs, amounts, key numbers |
| `--text-secondary` | `#475569` | Secondary text: Body, explanations, rule names |
| `--text-muted` | `#64748B` | Metadata, timestamps, subheaders, category labels |
| `--text-tertiary` | `#94A3B8` | Subtle separators, disabled elements |

### Structural Borders & Dividers
| Token | Hex | Role |
| :--- | :--- | :--- |
| `--border-subtle` | `#E2E8F0` | Structural card borders and section boundaries |
| `--border-light` | `#EAECF0` | Internal row dividers and cell borders |
| `--border-strong` | `#CBD5E1` | Interactive borders, focus states, input borders |

### Brand & Accents
| Token | Hex | Role |
| :--- | :--- | :--- |
| `--accent-slate` | `#0F172A` | Primary brand slate: Logo icon, primary action buttons |
| `--accent-hover` | `#1E293B` | Primary button hover state |
| `--signal-blue` | `#0369A1` | Informational accents, active navigation, progress bars |
| `--signal-blue-subtle` | `#F0F9FF` | Active row background, selected cell highlight |
| `--signal-blue-border` | `#BAE6FD` | Active focus rings, selected tag borders |

### Semantic Policy Outcomes
| Policy State | Text | Background | Border | Indicator Dot |
| :--- | :--- | :--- | :--- | :--- |
| **ALLOW** | `#065F46` | `#ECFDF5` | `#A7F3D0` | `#059669` |
| **REVIEW** | `#92400E` | `#FFFBEB` | `#FDE68A` | `#D97706` |
| **BLOCK** | `#991B1B` | `#FEF2F2` | `#FECACA` | `#DC2626` |
| **THREAT** | `#881337` | `#FFF1F2` | `#FECDD3` | `#881337` |

---

## 3. Typography & Monospace Rules

- **UI Font Family:** `Inter`, `Plus Jakarta Sans`, `-apple-system`, `BlinkMacSystemFont`, sans-serif.
- **Monospace Family:** `JetBrains Mono`, `ui-monospace`, `monospace`.
  - **Monospace Usage:** Strictly reserved for technical identifiers: Scenario IDs (`SCENARIO_01_INR_LABEL_CREATED`), Invariant Identifiers (`RULE_DELIVERY_PROOF`), Order IDs, Tracking Numbers, SHA-256 Hashes, and Raw JSON Payloads. Ordinary UI text, summaries, and categories remain sans-serif.
- **Tabular Numerals:** All financial amounts, metric figures, timestamps, and ratio counts utilize `font-variant-numeric: tabular-nums` to guarantee vertical alignment.

---

## 4. Benchmark Scorecard 2.0 Screen Architecture

### Header Area
- Page title: `Benchmark Scorecard`
- Subtitle: `Evaluate Docket's evidence-validation and deterministic policy engine.`
- Mandatory synthetic boundary pill: `SYNTHETIC BENCHMARK DATA — NOT LIVE PAYPAL DISPUTES`
- Actions:
  - `Run Evaluation Suite`: Executes live test suite via `POST /api/eval/run` and displays completion toast.
  - `Export Report`: Downloads structured JSON scorecard report (`docket_benchmark_scorecard_2.0.json`).

### Section 1: Four Compact Metrics Strip
Balanced 4-column horizontal strip:
1. **Total Scenarios:** Actual scenario count in evaluation dataset (`20`).
2. **Passed Scenarios:** Formatted as $X / Y$ (`20 / 20`).
3. **False ALLOW:** Count of unsupported claims permitted (`0`).
4. **False BLOCK:** Count of valid evidence incorrectly refused (`0`).

### Section 2: Two Primary Analytical Panels (~45% / ~55% Grid)
- **Panel A: Decision Confusion Matrix (45% Width):**
  - Expected ALLOW, Expected REVIEW, Expected BLOCK vs. Actual ALLOW, Actual REVIEW, Actual BLOCK.
  - Interactive cells: Clicking any cell filters the Scenario Execution Ledger below to the corresponding subset.
  - Clean green subtle background for diagonal matches (`match-allow`, `match-review`, `match-block`).
  - Warning red highlight if off-diagonal error cells contain non-zero values.
- **Panel B: Rule Performance (55% Width):**
  - Displays deterministic rules:
    - Delivery Proof Validation (`RULE_DELIVERY_PROOF`)
    - Address Matching (`RULE_ADDRESS_MATCH`)
    - Citation Integrity (`RULE_CITATION_INTEGRITY`)
    - HATEOAS Action Validation (`RULE_HATEOAS_ACTION`)
    - Signature Assessment (`RULE_SIGNATURE_ASSESSMENT`)
  - Restrained 5px progress bars with pass rates and pass/total ratios.
  - Interactive rows: Clicking a rule filters the scenario table to cases evaluating that rule.

### Section 3: Scenario Execution Ledger (Full-Width Data Table)
- Segmented control filters: `All (20)`, `Passed (20)`, `Failed (0)`, `Review (6)`, `Threats (1)`.
- Dropdown filters: Category filter, Primary Invariant filter.
- Real-time search: Filters across scenario ID, invariant name, and evidence summary.
- Active filter badges with one-click clear.
- Columns: Scenario ID, Category, Expected Decision, Actual Decision, Result (PASS/FAIL), Primary Invariant, Evidence Summary.
- Visual state: Failed rows are tinted with a subtle red background; passed rows remain clean neutral.

### Section 4: On-Demand Slide-Over Detail Drawer
- Width: `480px`, anchored to the right edge with a soft backdrop overlay (`rgba(15, 23, 42, 0.25)`).
- Does not reserve permanent desktop space when closed.
- Sections:
  1. **Decision Summary:** Expected vs Actual decisions, Result, Refusal status, Threat quarantine status.
  2. **Input Evidence:** Order ID, gross amount, carrier, tracking number, tracking status, customer dispute note (with quarantined text alert), and refund records.
  3. **Policy Findings:** Primary invariant, violated invariants list, discrepancies list, factual and action readiness.
  4. **Operational Rationale:** Human-readable operational explanation of the policy decision.
  5. **Technical Inspector:** Collapsible `<details>` raw JSON viewer with one-click Copy JSON feedback.

---

## 5. Responsive Behavior

| Viewport | Behavior |
| :--- | :--- |
| **1440 × 900 (Primary Desktop)** | 4-column metric strip, side-by-side 45/55 analytical panels, full-width ledger, 480px slide-over drawer. |
| **1280 × 720 (Compact Desktop)** | Main content scales gracefully with independent vertical scroll; ledger maintains horizontal proportion without browser horizontal overflow. |
| **< 1100px (Tablet / Narrow)** | Analytical grid stacks into single-column layout; metrics collapse into $2 \times 2$ grid; drawer adapts to 90vw. |

