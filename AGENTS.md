# Workspace Agent Guidelines

This workspace is configured with Google Antigravity 2.0 customizations located in `.agents/`.

All agent interactions must adhere to the persistent [Skill Selection Policy](file:///.agents/rules/skill-selection-policy.md):
- Inspect available skills under `.agents/skills/` before starting any complex task.
- Read `SKILL.md` before invoking skills.
- Automatically select **Impeccable** for frontend critique, UI audits, and design refinement.
- Automatically select **Taste Skill** collection skills for art direction, layout aesthetics, and visual design.
- Apply **Everything Claude Code (ECC)** rules, workflows, and skills for code engineering, TDD, security, and verification.
- Always prioritize correctness, security, and the user's explicit task requirements.
