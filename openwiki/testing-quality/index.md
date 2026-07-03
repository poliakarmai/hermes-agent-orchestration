# Testing & Quality — Invariants, Review, and CI/CD

This repository has minimal automated tests. Quality is maintained through documentation, invariant enforcement, and structured review pipelines.

## 1. Invariants (from /AGENTS.md)

These are hard rules that must never be broken:

1. **One gateway — two roles.** A single Hermes gateway serves demo and Pro users. Do not create separate gateway instances for bots.
2. **Isolation through profiles.** Tenants are isolated via `channel_profiles`, not by forking gateway processes.
3. **Rights through channel_profiles.** Do not patch bot code for access control — use `disabled_toolsets` in profile configs.
4. **`hermes_config.py` is SSOT for IDs.** Never hardcode `ADMIN_ID`/`UNLIMITED_USERS` in scripts. Always `from hermes_config import ADMIN_IDS`.

## 2. Constitution-Driven Quality

The system operates under a written constitution (`/docs/03-constitution.md`):

- **Judge is mandatory** before ALL code/config/script changes: `judge <files>` before `git commit`
- **Exceptions:** Trading orders, emergency restart, cron tasks
- **Completion:** Only when `passed: true` is returned

## 3. Skill Review Pipeline (Three-Stage)

When a tenant contributes a skill back to the base, it goes through mandatory review:

| Stage | Check | Tool |
|-------|-------|------|
| **Stage 0** | YAML frontmatter, required fields, naming conventions | `skill-validate.py` |
| **Stage 1** | Security scan — injections, dangerous commands | `skill-security-scan.py` |
| **Stage 2** | Judge review — constitution compliance, safety | DeepSeek API (`~/.local/bin/judge`) |
| **Stage 3** | Adversarial review — contradictions, hallucinations | DeepSeek API (second model) |

Blocking criteria: CRITICAL findings at Stage 1, `passed: false` at Stage 2, `approved: false` at Stage 3.

## 4. Cross-Model Review (from docs/06-roadmap.md)

All critical orchestration changes are reviewed by **two additional models at $0/month**:
- Qwen (open-source)
- Nemotron (open-source)

This provides adversarial validation without additional API costs.

## 5. Code Quality Patterns

### Import Pattern (from hermes_config.py enforcement)

```python
# ✅ Correct
from hermes_config import ADMIN_IDS

# ❌ Wrong — never hardcode
ADMIN_ID = 5529208670
```

### Optional Dependency Pattern (from apolaibot-demo.py)

```python
try:
    import pyotp
    TOTP_ENABLED = True
except ImportError:
    TOTP_ENABLED = False
    # Graceful fallback
```

### Error Handling Pattern (from bots/scripts)

- Scripts use `try/except` with logging via `logger`
- Cron scripts: **silent when OK, alert when broken**
- Polling bots: `ERROR_SLEEP=5` seconds on connection failure

## 6. Git Workflow

Based on commit history (git log inspection):

- **Commit messages** are descriptive, often bilingual (Russian + English)
- **Feature consolidation** — multiple related changes in single commits
- **Roadmap tracking** — each feature references a roadmap item (#X/26)
- **Architectural decisions documented** in commit messages and docs
- **Deduplication** — merged `hermes-orchestration` into `hermes-agent-orchestration` (commit d4e956d)

## 7. Future CI/CD (from roadmap)

The roadmap (docs/06-roadmap.md) identifies these future quality improvements:

- **CI/CD for skills** — auto-testing when tenants import skills
- **Panel for managing tenants** — web dashboard (status, costs, subscriptions)
- **Observability** — Grafana/Prometheus for gateway monitoring (currently using custom `metrics-collector.py` + dashboard)

## 8. Change Guidance for Agents

When modifying any of these areas, run the related checks:

| Change Area | Check / Review Step | Source |
|-------------|--------------------|--------|
| Tenant onboarding | `hermes-tenant onboard --dry-run` (run once), verify `channel_profiles`/`channel_prompts` | `/scripts/hermes-tenant` |
| Skill sync changes | Test with `--dry-run` first, verify `--status` output | `/scripts/skill-sync.py` |
| Rate limit changes | Check `rate_limits.db` queries, verify tier loading | `/scripts/rate_limiter.py` |
| Bot changes | Test locally, verify systemd service restart | `/bots/apolaibot-demo.py` |
| Payment flow | Run `miropolbot.py` in test mode, verify DB writes | `/bots/miropolbot.py` |
| ID configuration | Always import from `hermes_config.py`, never hardcode | `/hermes_config.py` |
| Cron script changes | Respect "no_agent" + "silent when OK" rules | `/docs/05-onboarding-checklist.md` |

## Source Map

| Check / Tool | File |
|--------------|------|
| Skill validator (Stage 0) | `/scripts/skill-validate.py` |
| Security scanner (Stage 1) | `skill-security-scan.py` (referenced, not in repo) |
| Judge CLI (Stage 2) | `~/.local/bin/judge` |
| Cross-model review | Uses Qwen + Nemotron (referenced in roadmap) |
| Constitution | `/docs/03-constitution.md` |
| Invariant enforcement | `/AGENTS.md` |
| Onboarding checklist | `/docs/05-onboarding-checklist.md` |
