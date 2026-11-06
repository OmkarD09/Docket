# Community 339

> 9 nodes

## Key Concepts

- **_validate_import_url()** (8 connections) — `.agents/skills/continuous-learning-v2/scripts/instinct-cli.py`
- **test_validate_import_url_rejects_http()** (3 connections) — `.agents/skills/continuous-learning-v2/scripts/test_parse_instinct.py`
- **test_validate_import_url_rejects_private_hosts()** (3 connections) — `.agents/skills/continuous-learning-v2/scripts/test_parse_instinct.py`
- **test_validate_import_url_allows_public_https()** (2 connections) — `.agents/skills/continuous-learning-v2/scripts/test_parse_instinct.py`
- **ipaddress** (2 connections)
- **socket** (2 connections)
- **Validate remote instinct imports before opening a network connection.** (1 connections) — `.agents/skills/continuous-learning-v2/scripts/instinct-cli.py`
- **Remote imports should not downgrade to plaintext HTTP.** (1 connections) — `.agents/skills/continuous-learning-v2/scripts/test_parse_instinct.py`
- **Remote imports should not resolve to private or loopback addresses.** (1 connections) — `.agents/skills/continuous-learning-v2/scripts/test_parse_instinct.py`

## Relationships

- [Community 11](Community_11.md) (3 shared connections)
- [Community 19](Community_19.md) (3 shared connections)
- [Community 55](Community_55.md) (1 shared connections)

## Source Files

- `.agents/skills/continuous-learning-v2/scripts/instinct-cli.py`
- `.agents/skills/continuous-learning-v2/scripts/test_parse_instinct.py`

## Audit Trail

- EXTRACTED: 12 (80%)
- INFERRED: 3 (20%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*