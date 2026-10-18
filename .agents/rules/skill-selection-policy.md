# Automatic Skill Selection & Governance Policy

This policy governs automatic discovery, selection, and application of workspace skills, rules, workflows, and agents across all present and future conversations in this workspace.

## 1. Skill Discovery & Progressive Disclosure
- **Inspect on Task Start:** At the beginning of each applicable task, inspect the installed skills under [.agents/skills/](file:///c:/Users/ACER/Downloads/Docket/.agents/skills).
- **Read Before Acting:** Always read the corresponding `SKILL.md` (and necessary `references/` or `scripts/`) before executing a skill's workflow. Never assume instructions or run commands blindly.
- **Truth in Execution:** Never claim a skill, tool, command, test, audit, or validation was executed unless it actually ran and produced verified results.

## 2. UI & Design Skill Selection

### Impeccable ([.agents/skills/impeccable/](file:///c:/Users/ACER/Downloads/Docket/.agents/skills/impeccable/SKILL.md))
- **When to select:** Automatically select for frontend design review, UI planning, UX critique, accessibility audits, responsive design checks, layout/typeset refinements, UI polish, edge-case hardening, and extracting design systems / tokens into `DESIGN.md`.
- **Execution:** Uses native launcher `.agents/skills/impeccable/scripts/impeccable.cmd` on Windows. Review `SKILL.md` commands table for targeted directives (`critique`, `audit`, `polish`, `shape`, `typeset`, etc.).

### Taste Skill Collection ([.agents/skills/](file:///c:/Users/ACER/Downloads/Docket/.agents/skills/))
Select the specific Taste Skill that aligns with the task's visual requirements:
- **`design-taste-frontend` (v2 default):** Building, styling, or reviewing landing pages, marketing sites, portfolios, or public web pages requiring art direction, real imagery, and browser-based inspection.
- **`redesign-existing-projects`:** Auditing and upgrading existing UI layouts, spacing, hierarchy, and styling without breaking functionality.
- **`high-end-visual-design`:** Designing polished, premium, agency-quality software product UI with soft contrast and refined spacing.
- **`minimalist-ui`:** Editorial product UI requiring restrained monochrome palettes and crisp structure.
- **`industrial-brutalist-ui`:** Technical, utilitarian, terminal, or brutalist aesthetics with rigid grids and raw contrast.
- **`stitch-design-taste`:** Building semantic design systems and tokens for Google Stitch.
- **`image-to-code`:** Visual workflows where UI is generated from reference images.
- **`brandkit` / `imagegen-*`:** Image-based design comps and visual brand-kit boards.
- **`full-output-enforcement`:** Exhaustive, unabridged code generation without placeholder comments or truncated blocks.

## 3. Engineering & Code Quality (ECC)
- **Rules & Standards:** Consult relevant language and framework rules in [.agents/rules/](file:///c:/Users/ACER/Downloads/Docket/.agents/rules/) for coding conventions, security practices, and pattern enforcement.
- **Workflows & Lifecycle:** Use applicable workflows in [.agents/workflows/](file:///c:/Users/ACER/Downloads/Docket/.agents/workflows/) (e.g., `feature-dev.md`, `code-review.md`, `quality-gate.md`, `build-fix.md`).
- **Engineering Skills:** Leverage [.agents/skills/](file:///c:/Users/ACER/Downloads/Docket/.agents/skills/) for disciplined engineering:
  - `tdd-workflow`: Test-driven development (red-green-refactor).
  - `verification-loop`: Rigorous post-implementation verification.
  - `architecture-decision-records`: Tracking architectural changes.
  - `error-handling`: Defensive error handling patterns.
  - `codebase-onboarding` & `repo-scan`: Structural exploration and codebase mapping.
- **Specialized Agents:** Utilize role-based agents in [.agents/agents/](file:///c:/Users/ACER/Downloads/Docket/.agents/agents/) (e.g., `code-reviewer.md`, `security-reviewer.md`, `planner.md`).

## 4. Synthesis & Precedence Rules
1. **Combine Complementary Skills:** For full-stack or frontend feature work, combine ECC engineering rigor (TDD, typing, security, tests) with Impeccable / Taste Skill visual standards.
2. **Resolve Conflicts:** If stylistic or UI advice conflicts with correctness, security, or explicit functional requirements, always prioritize security, correctness, and the user's explicit task requirements.
3. **No Redundancy:** Do not run competing or duplicate critique passes simultaneously. Select the single best-fit tool for the current step.
4. **Scope Discipline:** Never initialize product truth, create application documents, or add scaffolding unless specifically directed by the user.
