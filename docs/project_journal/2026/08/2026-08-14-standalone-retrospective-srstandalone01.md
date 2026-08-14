---
id: 20260814-srstandalone01
title: Standalone Session Retrospective Repository
status: completed
created: 2026-08-14
updated: 2026-08-15
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
- Signed migration commit `fad88a480f40061424191fafea7d4b0b1f932da0`
  preserves the standalone source snapshot before the first local review.
- Catalog schema v3 and transport manifest v2 bind a closed
  `session_identity` witness independently of the mutable source label.
- Session identity now derives from the same domain-separated selector
  commitment in Session, Daily, Weekly, and Baseline modes. Session acceptance
  re-derives that source reference from the authenticated witness and rejects
  relabeling of non-target, unresolved, or exact-target evidence into another
  accounting class.
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
- Exact-secret admission for `a3836660..fad88a48` was clean with complete
  temporary cleanup.
- A fresh-context Codex review of `a3836660..fad88a48` found three issues: a
  cross-mode Session identity split, an ambiguous-witness state-table hole,
  and exact-tuple matching that could miss target gap variants. The follow-up
  centralizes commitment-derived Session references, uses an explicit closed
  three-state policy, and rejects forbidden target reasons independently of
  stage metadata.
- Reviewer-fix focused tests pass 8/8; identity, CLI, and module-boundary tests
  pass 104/104; full source-transport and orchestrator tests pass 207/207.
- The first reviewer-fix Python 3.13 full repository discovery passes
  1,572/1,572 in 2,686.649
  seconds. Ruff 0.13.2, both workflow files under `actionlint`, the OpenAI
  skill validator, the project-journal validator, and `git diff --check` also
  pass on the reviewer-fix tree.
- A second fresh-context Codex review of `a3836660..e50d6466` found two
  retained-history Git gaps: post-admission commands could rediscover mutable
  `.git` control files, and a later shallow boundary was not revalidated.
- The follow-up binds `.git`, `commondir`, and `gitdir` identity and content,
  enters the held common-dir descriptor before every post-admission Git
  command, verifies the relative git-dir and object store, and runs the closed
  object/ref command set with explicit bare metadata paths and a fixed
  discovery ceiling. Shallow history is an exact forbidden-metadata absence
  checked before and after every command.
- Six focused discovery, linked-worktree, shallow-drift, path-replacement, and
  ABA regressions pass. The complete publication transaction module passes
  91/91 in 2,470.280 seconds; the engine boundary suite passes 19/19 after its
  exact branch-proxy fixture is updated from 8,520 to 8,568.
- Final Python 3.13 full repository discovery passes 1,575/1,575 in 2,675.201
  seconds on the Git discovery and shallow-revalidation implementation tree.
- The next fresh-context Codex review of `a3836660..322fe97b` found that the
  publisher sign/verify canary inherited the complete host environment even
  though its GPG executable bytes were bound. That exposed the production
  `GNUPGHOME` to dynamic-loader, Python, shell, Git, and agent injection
  variables outside the executable-authority contract.
- The canary now reuses the publication layer's strict subprocess environment,
  adds only the dedicated `GNUPGHOME`, and keeps the fixed locale, `PATH`, and
  timezone contract. A real fake-GPG regression captures both sign and verify
  process environments and proves that poisoned host variables are absent.
- The canary-focused suite passes 5/5, the affected orchestrator suite passes
  111/111 in 194.853 seconds, and the module-boundary suite passes 19/19.
  Final Python 3.13 repository discovery passes 1,576/1,576 in 2,839.720
  seconds on the closed-environment implementation tree.
- A direct default-host canary probe is non-counting: executable authority
  rejected the ambient Homebrew GPG before keyring access because its `Cellar`
  ancestor is group-writable. This is the intended deployment boundary; the
  publication caller must supply a GPG executable under an admitted private
  path. The authorized disposable-GPG publication fixture is covered by the
  successful full discovery.
- The next fresh-context Codex review of `a3836660..add6f4a` found two further
  launch-boundary gaps: the public coordinator documentation and native action
  used Python without the complete isolation flags, and canary cleanup could
  reap its leader while leaving a same-group descendant alive.
- The public coordinator now requires `python3 -I -B -S` in the skill,
  operator reference, README, automation cutover records, native coordinator
  actions, and its direct-entry startup guard. Runtime regressions prove that
  missing flags fail closed and that poisoned `PYTHONPATH`, `sitecustomize`,
  and current-directory modules do not execute.
- Canary supervision retains the launch PGID before leader reaping, kills the
  complete group on every terminal path, reaps the leader, and waits for exact
  group absence. Darwin `EPERM` from a killed orphan zombie remains unproven
  and is polled until `ESRCH`; persistent `EPERM` still fails closed. Real
  closed-pipe success and inherited-pipe timeout descendants are both covered.
- Canary-focused tests pass 7/7; focused CLI/skill tests pass 11/11; module
  boundaries pass 19/19 with the CLI's 1,950-line cap unchanged and the exact
  branch proxy updated from 8,568 to 8,591. The complete affected authority,
  projection, CLI, transport, orchestrator, and skill matrix passes 292/292 in
  294.832 seconds.
- Final Python 3.13 repository discovery passes 1,582/1,582 in 2,833.264
  seconds on the isolated-launch and complete process-group cleanup tree.
- The next fresh-context Codex review of `a3836660..43a79368` found two release
  blockers: production finalize did not bind a persisted trusted GPG
  executable, and the single 1,582-test CI job had no deterministic sharding or
  job timeout.
- `doctor` and `start` now require an absolute `--publisher-gpg-program`.
  Start persists the executable's canonical path plus a digest over its
  identity, bytes, and ancestor access policy; every authenticated history read
  and final publication revalidates that exact authority. Finalize has no
  ambient or caller override. Real publication regressions prove that a
  stripped `PATH` still uses the persisted executable and that same-path
  content mutation fails before the publication adapter starts.
- CI now assigns every discovered test ID to one of four stable SHA-256 shards,
  runs each shard under Python 3.13 with a 40-minute timeout, preserves the
  aggregate `test` check, and cancels superseded workflow runs. The isolated
  sharder entrypoint and partition contract have dedicated regressions.
- The complete affected authority, publication, CLI, transport, skill, and CI
  module group passes 384/384 in 2,862.198 seconds. Ruff lint, edited-file
  formatting, `actionlint`, the OpenAI skill validator, and the module/skill/CI
  contract group also pass.
- A first local four-shard attempt is non-counting because its task wrapper
  accidentally propagated `RLIMIT_FSIZE` into five oversized-file fixtures.
  The corrected wrapper bounds only the retained output pipe. The clean rerun
  covers all 1,589 tests exactly once: shard counts 374, 427, 435, and 353 all
  pass in 1,146.277, 917.407, 914.556, and 830.574 seconds respectively. The
  slowest shard remains below half of the CI timeout.
- A final read-only GPG authority audit found two related release-boundary
  gaps: the formal publication request did not compare its persisted GPG
  program and authority digest with the adapter's exact admitted executable,
  and the keyring probe re-resolved the path without first requiring the
  adapter's captured authority digest. The adapter now captures that digest at
  construction, the keyring probe rejects any replacement before keyring or
  home access, and formal publication requires an exact fingerprint,
  `GNUPGHOME`, executable path, and authority-digest match before side effects.
- The three new authority regressions plus the complete CI, module-boundary,
  and publication-focused group pass 28/28 in 62.706 seconds. The final
  post-fix Python 3.13 run covers all 1,592 tests exactly once across the
  deterministic shards: 375, 427, 437, and 353 tests pass in 1,494.843,
  1,231.485, 1,305.869, and 1,137.495 seconds respectively. The slowest shard
  remains below the 40-minute CI timeout, and the combined error scan is empty.

## Acceptance

- Python 3.13 focused and full repository tests pass.
- Source/session classification is receipt-bound and cannot silently discard
  the exact Session target.
- The skill and CLI contracts use the standalone root layout.
- Exact-secret admission, the required local Codex processor, hosted CI, and
  current-head GitHub Codex evidence pass for the final PR head.
- The signed source PR merges without changing any private sync repository.
