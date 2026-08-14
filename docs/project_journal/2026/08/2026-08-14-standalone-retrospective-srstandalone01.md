---
id: 20260814-srstandalone01
title: Standalone Session Retrospective Repository
status: active
created: 2026-08-14
updated: 2026-08-14
branch: wip/standalone-retrospective
pr:
supersedes:
  - 20260716-srv2e01
superseded_by:
---

# Standalone Session Retrospective Repository

## Summary

- Created `Joey-Tools/codex-session-retrospective` as the canonical source
  repository for the complete Retrospective skill.
- Migrated the v1 comparison helper, modular v2 engine, closed CLI and schemas,
  references, agent metadata, fixtures, and Retrospective-specific tests from
  the closed `codex-workflow-hygiene` PRs #67 and #69.
- Adopted a singleton-skill layout with `SKILL.md`, `agents/`, `references/`,
  and `scripts/` at the repository root.

## Current State

- The standalone repository and task-scoped `wip/standalone-retrospective`
  branch exist.
- The migrated implementation includes the uncommitted source/session policy
  follow-up from the former #69 owner worktree.
- Catalog schema v3 and transport manifest v2 bind a closed
  `session_identity` witness independently of the mutable source label.
- Session acceptance re-derives the source reference from the authenticated
  witness and rejects relabeling of non-target, unresolved, or exact-target
  evidence into another accounting class.
- Private sync, installed release changes, workspace registry changes, and the
  legacy deletion PR are intentionally out of scope until this repository is
  complete.

## Validation

- Python 3.13 v2 engine tests: 632 passed.
- Python 3.13 v1, CLI, skill, and CI contract tests: 937 passed.
- Focused source-identity and module-boundary tests: 22 passed after formatting.
- Ruff 0.13.2 lint passed for `scripts/` and `tests/`; edited Python files pass
  the formatter check without mechanically rewriting inherited migration-only
  sources.
- Both GitHub Actions workflows pass `actionlint`.
- The installed OpenAI skill validator passes through an isolated Python 3.13
  environment with PyYAML.
- Python 3.13 full repository discovery: 1,569 passed in 2,605.189 seconds.
- Signed commit, exact-secret admission, review, and hosted PR evidence remain
  pending.

## Acceptance

- Python 3.13 focused and full repository tests pass.
- Source/session classification is receipt-bound and cannot silently discard
  the exact Session target.
- The skill and CLI contracts use the standalone root layout.
- Exact-secret admission, the required local Codex processor, hosted CI, and
  current-head GitHub Codex evidence pass for the final PR head.
- The signed source PR merges without changing any private sync repository.
