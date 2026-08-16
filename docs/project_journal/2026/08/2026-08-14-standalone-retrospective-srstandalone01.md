---
id: 20260814-srstandalone01
title: Standalone Session Retrospective Repository
status: completed
created: 2026-08-14
updated: 2026-08-16
branch: wip/standalone-retrospective
pr: https://github.com/Joey-Tools/codex-session-retrospective/pull/1
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
- The superseded old-repository implementation and prior installed/scheduled
  copy are retired. This repository is the only canonical source.
- Workspace registration follows this source merge. A replacement private sync
  and installed release are intentionally deferred to a separate workstream.

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
- The first hosted sharded run exposed a platform-specific fixture boundary:
  Ubuntu's default `/tmp` is world-writable, so the changed-GPG regression's
  copied executable was correctly rejected by the production authority before
  the test reached its intended same-path mutation. A global private `TMPDIR`
  attempt is non-counting: it made two deliberate writable-ancestor negative
  tests invalid and both corresponding shards failed.
- The final fixture fix scopes only the trusted mutable GPG copy to a private
  temporary directory below the repository root. The two negative fixtures
  continue to exercise the real world-writable temporary ancestor. All three
  exact regressions pass in 27.310 seconds; the CI contract passes 6/6, module
  boundaries pass 19/19, and the skill contract passes 5/5. `actionlint`, Ruff
  lint and formatting, and `git diff --check` remain clean.
- A fresh-context Codex review of `a3836660..1ac8498e` found three remaining
  access-policy and raw-evidence gaps: transport executable and snapshot
  authentication omitted Darwin extended ACLs, local `.git/config` admission
  omitted the same ACL check, and the remote raw-output temporary file was not
  descriptor-hardened before its first raw byte.
- Transport program components, committed source snapshots, remote helper
  snapshots, and the Python runtime now reject any extended ACL at both
  authenticated observations. Local Git config admission applies the same
  owner-controlled, no-ACL policy before and after its exact read. The remote
  relay hardens its anonymous spool through the held descriptor before any
  filtered or unfiltered raw output can be written; hardening failure enters
  the existing process-group cleanup path.
- Six exact ACL/spool regressions pass in 44.114 seconds. The complete source
  transport module passes 100/100 in 24.509 seconds, module boundaries pass
  19/19 in 1.870 seconds, and the canary support module passes 7/7 in 2.427
  seconds. CI and skill contracts pass 6/6 and 5/5; the installed OpenAI skill
  validator, Ruff 0.13.2 lint, changed-file formatting, `actionlint`, and
  `git diff --check` are clean.
- One redundant full publication-module run was interrupted at its declared
  45-minute cutoff and is non-counting. During that extra fifth heavy producer,
  the first four-shard attempt had one 15-second publisher-canary timeout in
  shard 2; the other 438 tests passed, but that shard is not counted. After the
  extra producer was quiescent, the complete canary support module passed and
  the exact canary case passed inside a clean shard-2 rerun.
- Final Python 3.13 evidence covers all 1,598 tests exactly once with no error
  scan matches: shard 0 passes 377/377 in 1,616.905 seconds, shard 1 passes
  427/427 in 1,290.111 seconds, the clean shard-2 rerun passes 439/439 in
  822.881 seconds, and shard 3 passes 355/355 in 1,299.679 seconds.
- A fresh-context Codex review of `a3836660..bb62131` found one final
  publication-durability gap: transaction creation could persist a journal
  before the run claim and retained sidecar protected the bundle, allowing
  expiry GC to remove the only publication input after a crash.
- Transaction creation now requires a callback that first binds the exact
  sidecar attempt and persists the identity-authenticated checkpoint claim;
  creation revalidates that claim before its journal write. The initial
  heartbeat is immutable across preclaim recovery, and a post-deadline retry is
  admitted only when the sidecar deadline matches the run and the heartbeat
  precedes the earliest raw, working, and export deadline. Concurrent GC
  continues to serialize on the same bundle lock and retains every bound pair.
- The three new crash-boundary regressions cover binding-before-claim,
  claim-before-journal, and journal-before-prepare recovery. Together with the
  existing phased-finalize, missing-sidecar, copied-journal, and symlinked-state
  regressions, the focused implementation checks pass. One test command used a
  nonexistent method selector and produced a loader-only error; its five real
  tests passed, and the corrected exact symlink test passed separately.
- Recovery also distinguishes an already authenticated same-attempt claim from
  an unclaimed bootstrap. The former can reopen committed or aborted journals
  without attempting to mutate the terminal retention sidecar; the latter must
  still prove the sidecar binding before any claim or journal is persisted.
- One complete publication-module attempt is non-counting: APFS had only about
  113 MiB available and the run ended with 51 `ENOSPC` errors after 1,642.900
  seconds. It nevertheless exposed the terminal-sidecar recovery regression,
  which was fixed before any final gate was accepted. After disk capacity was
  restored, the complete publication module passed 101/101 in 2,534.780
  seconds and the CLI/orchestrator modules passed 161/161 in 240.997 seconds.
- Final Python 3.13 evidence covers all 1,601 tests exactly once with no error
  scan matches: shards 0 through 3 pass 378/378 in 955.991 seconds, 428/428 in
  766.543 seconds, 439/439 in 806.293 seconds, and 356/356 in 771.432 seconds.
  The exact architecture checks pass 2/2; Ruff lint, changed-file formatting,
  `actionlint`, the installed skill validator, project-journal validation, and
  `git diff --check` are clean.
- A fresh-context Codex review of `a3836660..5ad3c8c2` found three retained
  publication recovery gaps: a sidecar could bind before its checkpoint claim
  and then lose raw input to expiry GC, an expired preclaim could become
  permanently unrecoverable, and the public checkpoint API could persist a
  claim without first binding an exact retained bundle.
- The follow-up persists the canonical staging locator, requires every new
  publication claim to bind that bundle, and serializes binding and expiry GC
  on the same bundle lock. Stale recovery is non-renewing and must revalidate
  either the authenticated checkpoint transition or the terminal publication
  plan while that exact lock remains held. Receipt validation is closed and
  split into narrow binding and orchestrator-coordination owners to keep the
  publication dependency graph acyclic.
- The first final publication-module attempt exposed one migrated test fixture
  that copied a checkpoint and then created a different unbound bundle. That
  run was interrupted and is non-counting. The fixture now forks before export
  binding and drives both copies through `mark_exported`; its exact same-root,
  different-attempt regression passes in 50.313 seconds without weakening the
  production locator contract.
- Final Python 3.13 affected-module evidence passes: retained export 62/62 in
  3.703 seconds, orchestrator 112/112 in 180.084 seconds, v2 CLI 43/43 in
  55.975 seconds, publication transaction 103/103 in 2,329.355 seconds, and
  architecture/CI/skill contracts 30/30 in 2.500 seconds. Final discovery
  contains 1,604 unique tests partitioned exactly once as 378, 429, 439, and
  358 tests across the four deterministic shards.
- Ruff 0.13.2 lint and changed-file formatting, both workflows under
  `actionlint`, the installed OpenAI skill validator, and `git diff --check`
  pass on the frozen implementation tree.
- A fresh-context Codex review of `a3836660..c490b096` found two terminal
  recovery gaps: authenticated aborted publications retained raw inputs
  forever, and the aborted checkpoint discarded its claim before a lost CLI
  response could retry.
- The follow-up retains the exact publication claim through aborted finalize
  acknowledgement, validates the durable abort journal and attempt-bound
  terminal sidecar before claiming raw cleanup, and records a distinct
  identity-authenticated `expired_aborted` cleanup disposition. Completed raw
  cleanup removes the nonformal durable candidate while preserving an
  authenticated cleanup claim and receipt for idempotent replay.
- The new integration regression covers lost aborted-checkpoint responses with
  both a present and already-collected retained bundle, then proves raw input
  removal after the seven-day deadline. The exact integration passes 1/1 in
  40.629 seconds; the terminal-binding and unauthenticated-abort fail-closed
  regressions pass 2/2, and six adjacent publication, preclaim, committed-GC,
  and ordinary expired-cleanup regressions pass 6/6 in 123.740 seconds.
- The first full follow-up attempt is non-counting. Shards 1 and 3 passed
  430/430 and 359/359, while shard 0 exposed one migrated assertion that still
  expected an aborted acknowledgement to discard its retry claim and shard 2
  exposed the lifecycle line budget plus the exact branch proxy. The behavior
  assertion now requires same-claim idempotent replay. Abort/GC coordination
  moved into bounded `publication_claims.py` and `raw_cleanup_state.py` owners;
  `orchestrator_lifecycle.py` is 3,321 lines under its 3,325-line ceiling, and
  the exact branch proxy is 8,669 with four branches of slack.
- The final reviewer-fix focused matrix passes 6/6 in 75.339 seconds, covering
  the attempt-bound terminal sidecar, lost abort response replay, pre-reservation
  abort recovery, unauthenticated abort retention, and both architecture gates.
  Final Python 3.13 discovery covers all 1,606 tests exactly once: shards 0
  through 3 pass 378/378 in 863.602 seconds, 430/430 in 693.663 seconds,
  439/439 in 724.989 seconds, and 359/359 in 755.340 seconds.

## Final Separation State

- The implementation is logically separated: this repository is the canonical
  source and its v1 and v2 CLIs start directly from the repository root under
  Python 3.13 without importing or reading implementation files from
  `codex-workflow-hygiene`.
- The repository has its own public GitHub remote, standalone root layout,
  tests, workflows, guidance, and project journal. It has no tracked symlink,
  submodule, or runtime path dependency back to the old repository.
- Remaining `codex-workflow-hygiene` references are migration provenance or
  synthetic redaction fixtures. They are not runtime dependencies.
- Original implementation PRs
  [`codex-workflow-hygiene#67`](https://github.com/Joey-Tools/codex-workflow-hygiene/pull/67)
  and
  [`codex-workflow-hygiene#69`](https://github.com/Joey-Tools/codex-workflow-hygiene/pull/69)
  are closed without merge. Their signed history remains available.
- The legacy implementation was removed from `codex-workflow-hygiene` through
  its dedicated removal PR after extraction. The prior installed and scheduled
  copy was retired independently; no replacement sync is part of this source
  PR.
- Terminal retry preserves the original machine-classified exception when its
  terminal replay also fails. Aborted and expired checkpoints cannot authorize
  reconstruction of an active publication journal, while a matching durable
  aborted journal remains recoverable.
- Persistent checkpoint-claim validation is owned by bounded
  `publication_claims.py`; the core publication aggregate and per-module line
  budgets remain below their existing ceilings.
- The first exact-head delivery review found that source transport committed
  only the Python interpreter leaf while leaving writable ancestor replacement
  outside the receipt. The superseding implementation reuses the shared
  executable authority to persist and revalidate every ancestor plus the leaf
  identity, content, owner, mode, and ACL policy before a command can be
  projected. Benign timestamp churn remains accepted; a writable ancestor or
  `argv[0]` replacement fails closed.
- Worker-only component reads now live in bounded
  `transport_program_components.py`, keeping the remote worker manifest at 13
  reachable modules instead of importing the parent-side executable authority.
  The affected source-transport suite passes 101/101 and the module-boundary
  suite passes 19/19 under Python 3.13.
- The superseding Python 3.13 shard run discovers 1,618 tests exactly once.
  Shards 0, 1, and 3 pass 383/383 in 1,170.614 seconds, 431/431 in 902.009
  seconds, and 360/360 in 967.676 seconds. Shard 2 passes 443/444 in 1,011.715
  seconds; its only failure is the unrelated 15-second publisher-canary
  deadline while four long shards contend on one host. The exact failed test
  then passes serially 1/1 in 0.741 seconds on the same frozen code tree, so the
  composite evidence executes and passes all 1,618 discovered tests without
  treating the original shard as a clean run.
- The final implementation-focused matrix passes 1/1 for aborted journal
  reconstruction and 2/2 for the exact architecture budgets. Complete Python
  3.13 discovery covers all 1,617 tests exactly once: shards 0 through 3 pass
  382/382 in 1,055.667 seconds, 431/431 in 815.379 seconds, 444/444 in 910.517
  seconds, and 360/360 in 873.137 seconds.
- Two final read-only pre-commit explorer attempts produced no terminal
  artifact within their 15- and 10-minute bounds and were stopped as
  inconclusive. They supply no review result; the exact frozen-head Codex
  review remains an independent delivery gate.
- Ruff lint, changed-file formatting, both workflows under `actionlint`, the
  installed skill validator, project-journal validation, CI/skill contracts
  11/11, and `git diff --check` are clean on the final source tree.

## Follow-up Work

1. Register `Joey-Tools/codex-session-retrospective` in `codex-workspace` after
   the standalone source PR merges.
2. Design and review replacement private sync and installed-release
   integration as a separate workstream.

## Acceptance Criteria

- Python 3.13 focused and full repository tests pass on the final committed
  tree.
- Source/session classification is receipt-bound and cannot silently discard
  the exact Session target.
- The skill and CLI contracts use the standalone root layout.
- Exact-secret admission, the required local Codex processor, hosted CI, and
  current-head GitHub Codex evidence pass for the final PR head.
- The signed source PR remains independent of replacement private sync work.
