# Judgment Day — F0 Onboarding Docs Review

**Date:** 2026-09-18
**Target:** `AGENTS.md` + `.claude/commands/home-ops.md`
**Scope:** Documentation accuracy, CLI command verification, security/privacy, onboarding correctness
**Mode:** READ ONLY — no fixes, no commit, no push

---

## Executive Summary

**Verdict: ESCALATED**

Both judges (jd-judge-a, jd-judge-b) independently identified the same 3 issues.
No severe/critical blockers found. Issues are WARNING-level documentation accuracy and one medium security concern.

---

## Judge Results

| Judge | Severe | Warning | Info | Verdict |
|-------|--------|---------|------|---------|
| jd-judge-a | 0 | 3 | 1 | ESCALATED |
| jd-judge-b | 0 | 3 | 1 | ESCALATED |

**Consensus:** 3/3 issues confirmed by both judges.

---

## Confirmed Findings

### 1. `snapshots-reset` misclassified as future command (WARNING)

**Location:** `AGENTS.md` Section 6 (Roadmap)
**Issue:** Documentation lists `snapshots-reset` as a future command, but `uv run homeops snapshots-reset --help` confirms it EXISTS in the current CLI.
**Impact:** Users/agents may avoid using a valid command.
**Fix:** Move `snapshots-reset` from Section 6 (Roadmap) to Section 2 (CLI Commands).

### 2. `$ARGUMENTS` passed unvalidated to shell commands (MEDIUM SECURITY)

**Location:** `.claude/commands/home-ops.md`
**Issue:** `$ARGUMENTS` is interpolated directly into shell commands (`uv run homeops scan $ARGUMENTS`, etc.) without validation or quoting.
**Impact:** Potential shell injection if user input contains metacharacters.
**Fix:** Quote `"$ARGUMENTS"` or validate/sanitize before interpolation.

### 3. Cloud agent privacy warning incomplete (WARNING)

**Location:** `AGENTS.md` Section 4 (Guardrails)
**Issue:** Privacy section warns about local data but does not clearly state that conversations with cloud-hosted agents (Claude Code, ChatGPT, etc.) are processed by the provider. Users may mistakenly believe salary/financial data never leaves the PC when using cloud agents.
**Impact:** Users may share sensitive financial data in cloud agent chats.
**Fix:** Add explicit warning: "When using cloud-hosted agents, do NOT share salaries, bank details, or financial data in the conversation — they are processed by the provider."

---

## Informational Notes

- `profile` and `sources` subcommands correctly documented as FUTURE (not in CLI).
- All other CLI commands (`scan`, `status`, `approve`, `setup`, `tui`, `web`, `analytics`, `daemon`) verified against `--help` output.
- Onboarding flow (Section 3) is clear and actionable.
- Security guardrails (Section 4) are comprehensive except for the cloud agent gap.

---

## Scope

- **In scope:** `AGENTS.md`, `.claude/commands/home-ops.md`, CLI command verification via `--help`.
- **Out of scope:** F1–F4 implementation status, code review, DB queries, live scan/setup/approve execution.

---

## Next Steps

Awaiting explicit human authorization to proceed with fixes.
No automatic remediation performed.
