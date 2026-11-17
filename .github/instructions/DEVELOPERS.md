# Developer & Agent Playbook

Workflow expectations for contributors using GitHub tooling.

## Separation of concerns
- `FINALIZATION_CHECKLIST.md` — implementation status, roadmap, decisions, evidence.
- `AGENTS.md` — operating rules, invariants, official references.
- `.github/instructions/` — GitHub-native developer guidance (this file).

## Must-read before starting work
1. `FINALIZATION_CHECKLIST.md` — know what is done, what is pending, what is blocked.
2. `docs/ARCHITECTURE.md` — understand the action bridge and container model.
3. `AGENTS.md` — invariants and agent rules.

## Contribution acceptance criteria
- Install remains idempotent/re-runnable.
- Uninstall remains reversible with preserve-by-default behavior.
- Secrets are never committed.
- No default WAN exposure is introduced.
- `shell_command` is NOT used for ADB/Bluetooth (broken pattern — see `docs/ARCHITECTURE.md`).
- QA checks pass: `./scripts/qa.sh` (`shellcheck` + `docker compose config`).

## PR hygiene
- Keep diffs small, reversible, and explicitly scoped.
- Explain user-visible behavior changes.
- Cite official docs for security/runtime-sensitive changes.
- Update `*.example` templates and `docs/` when config behavior changes.
- Update `FINALIZATION_CHECKLIST.md` if status or roadmap changes.

## Reference hierarchy
1. Official docs (authoritative — see `SOURCES.md`).
2. Upstream project repos (implementation patterns only).
3. Community examples (verify before adopting).

## Verification
```bash
./scripts/qa.sh                                          # shellcheck + compose validate
./scripts/smoke/run_release_smoke.sh --mode verify       # non-destructive, read-only report
```
Lifecycle qualification is the manual runbook `docs/SMOKE_TEST_RUNBOOK.md` (no automated `--mode full`).
