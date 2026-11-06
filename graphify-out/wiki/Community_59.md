# Community 59

> 24 nodes

## Key Concepts

- **ObservationEvent** (21 connections) — `.agents/skills/skill-comply/scripts/parser.py`
- **parser.py** (18 connections) — `.agents/skills/skill-comply/scripts/parser.py`
- **ComplianceSpec** (16 connections) — `.agents/skills/skill-comply/scripts/parser.py`
- **grader.py** (15 connections) — `.agents/skills/skill-comply/scripts/grader.py`
- **report.py** (15 connections) — `.agents/skills/skill-comply/scripts/report.py`
- **generate_report()** (12 connections) — `.agents/skills/skill-comply/scripts/report.py`
- **classifier.py** (11 connections) — `.agents/skills/skill-comply/scripts/classifier.py`
- **ComplianceResult** (9 connections) — `.agents/skills/skill-comply/scripts/grader.py`
- **classify_events()** (8 connections) — `.agents/skills/skill-comply/scripts/classifier.py`
- **_steps_to_promote()** (6 connections) — `.agents/skills/skill-comply/scripts/report.py`
- **_check_temporal_order()** (5 connections) — `.agents/skills/skill-comply/scripts/grader.py`
- **_step_compliance_rate()** (5 connections) — `.agents/skills/skill-comply/scripts/report.py`
- **StepResult** (4 connections) — `.agents/skills/skill-comply/scripts/grader.py`
- **_parse_classification()** (4 connections) — `.agents/skills/skill-comply/scripts/classifier.py`
- **_overall_compliance()** (4 connections) — `.agents/skills/skill-comply/scripts/report.py`
- **Path** (1 connections)
- **Classify tool calls against compliance steps using LLM.** (1 connections) — `.agents/skills/skill-comply/scripts/classifier.py`
- **Classify which tool calls match which compliance steps. Returns {step_id:…** (1 connections) — `.agents/skills/skill-comply/scripts/classifier.py`
- **Parse LLM classification output into {step_id: [event_indices]}.** (1 connections) — `.agents/skills/skill-comply/scripts/classifier.py`
- **Grade observation traces against compliance specs using LLM classification.** (1 connections) — `.agents/skills/skill-comply/scripts/grader.py`
- **Check before_step/after_step constraints. Returns failure reason or None.** (1 connections) — `.agents/skills/skill-comply/scripts/grader.py`
- **Parse observation traces (JSONL) and compliance specs (YAML).** (1 connections) — `.agents/skills/skill-comply/scripts/parser.py`
- **Generate Markdown compliance reports.** (1 connections) — `.agents/skills/skill-comply/scripts/report.py`
- **Generate a Markdown compliance report. Args: skill_path: Path to the skill file…** (1 connections) — `.agents/skills/skill-comply/scripts/report.py`

## Relationships

- [Community 33](Community_33.md) (21 shared connections)
- [Community 27](Community_27.md) (20 shared connections)
- [Community 75](Community_75.md) (10 shared connections)
- [Community 2](Community_2.md) (4 shared connections)
- [Community 13](Community_13.md) (3 shared connections)

## Source Files

- `.agents/skills/skill-comply/scripts/classifier.py`
- `.agents/skills/skill-comply/scripts/grader.py`
- `.agents/skills/skill-comply/scripts/parser.py`
- `.agents/skills/skill-comply/scripts/report.py`

## Audit Trail

- EXTRACTED: 85 (77%)
- INFERRED: 25 (23%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*