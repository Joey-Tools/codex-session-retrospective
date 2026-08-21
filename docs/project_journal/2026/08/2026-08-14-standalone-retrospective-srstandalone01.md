---
id: 20260814-srstandalone01
title: Standalone Session Retrospective Repository
status: completed
created: 2026-08-14
updated: 2026-08-21
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
- The first PR-head delivery cycle for `6814250e` exposed one CI fixture error
  and two fresh-review gaps. The source-transport adversarial fixture placed its
  copied Python under a sticky world-writable temporary ancestor; migration-only
  history reads inherited repository Git controls; and migration provenance
  still described legacy retirement as future work after retirement had already
  completed. The CI failure and all review evidence for that head are superseded
  by the following signed fix head.
- The source-transport fixture now creates its copied interpreter below an
  owner-controlled ignored repository directory. History reads now route through
  bounded `legacy_history_git.py`, which uses the shared executable authority,
  closed Git environment and command controls, complete local-repository
  admission, and pre/post object and config revalidation. Regressions prove that
  a configured `core.fsmonitor` is not executed, repository-local includes are
  rejected, and a Darwin extended ACL fails closed. Migration provenance now
  records the actual paused interval: the old source and installation are gone,
  while replacement private sync remains future work.
- A host-level source-transport run through `/opt/homebrew/bin/python3.13` is
  non-counting because that executable's group-writable ancestor correctly
  fails the transport authority contract. Re-running through the repository's
  owner-controlled Python 3.13.12 copy passes the source-transport suite
  101/101; the affected history subset passes 62/62; the exact focused security
  regressions pass 4/4; and the module-boundary suite passes 19/19.
- Final Python 3.13 discovery covers all 1,621 tests exactly once. Shards 0
  through 3 pass 385/385 in 1,285.612 seconds, 432/432 in 985.168 seconds,
  444/444 in 1,098.940 seconds, and 360/360 in 1,058.989 seconds. Ruff lint,
  changed-file formatting, both workflows under `actionlint`, the official
  OpenAI skill validator, CI/skill contracts 11/11, and `git diff --check` are
  clean on the same working tree.
- The fresh-context review of signed PR head `30cd6e40` found two history-read
  gaps: commands reopened the admitted repository by its mutable absolute path,
  and ordinary Git stdout/stderr capture had no aggregate byte ceiling. The
  superseding implementation runs every post-admission Git command through the
  held repository descriptors and the shared bounded process runner. Clean-tree
  proof now compares exact HEAD/index snapshots with two descriptor-relative
  physical worktree commitments, including root and child identity, content,
  ownership, group, mode, and ACL policy. It accepts benign timestamp churn but
  rejects object replacement, content drift, unsafe policy, ignored/untracked
  files, symlinks, unsupported objects, torn snapshots, and owner-execute drift.
- History blob reads first bind the declared object size and then use a
  size-derived output ceiling. The physical scanner shares one absolute
  30-second deadline across Git and filesystem phases, bounds entries, paths,
  depth, per-file bytes, and aggregate bytes, and derives its 256 MiB per-file
  ceiling from the retained-artifact authority rather than the retired 64 MiB
  implementation limit.
- The final history-security matrix passes 21/21 in 22.909 seconds; the module
  boundary suite passes 19/19 with exact branch inventory 8,805; CI contracts
  pass 6/6; and Ruff 0.13.2 lint/format, `actionlint`, the installed skill
  validator, project-journal validation, and `git diff --check` pass. Current
  discovery is 1,639 tests. Local four-way and two-way full-suite attempts are
  non-counting because the host volume reached `ENOSPC`; no assertion failure
  was observed, every interrupted process group was drained, and no repository
  worktree was deleted to manufacture capacity. The exact committed head must
  therefore obtain its complete four-shard result from hosted CI before merge.
- Hosted CI passed all four shards for signed head `69918828`, but that evidence
  became stale when its fresh-context Codex review found that automation
  cutover authenticated each `automation.toml` through one unbound pathname
  read. The old head is not mergeable evidence.
- Automation file authentication now has one bounded descriptor owner in
  `automation_cutover_files.py`. It retains the physical automation root, each
  stable-ID directory, and both records through cutover publication; checks
  owner, mode, link count, and absence of extended ACLs; performs two bounded
  content reads; and revalidates both stable IDs immediately before writing the
  authenticated cutover record. Same-inode same-length mutation, truncation,
  file replacement, directory replacement, and Darwin extended ACLs fail
  closed, while timestamp-only churn remains benign.
- The superseding local matrix passes the complete v2 CLI/cutover class 49/49
  in 64.308 seconds, module boundaries 19/19 with exact branch inventory 8,843,
  CI contracts 6/6, and two production-marker integration tests 2/2 in 41.282
  seconds. Ruff lint and formatting plus `git diff --check` are clean on the
  implementation files. Current discovery is 1,645 tests, partitioned exactly
  once as 390, 440, 448, and 367; complete final-head execution remains a
  hosted-CI prerequisite before merge.
- A fresh-context review of signed head `da7fc8e` found three additional
  cutover-contract defects: mode and RRULE checks were not closed, descriptor
  cleanup inferred a primary failure from the ambient exception context, and
  Darwin/BSD write-delete restriction flags were absent from the automation
  access-policy binding. Its otherwise-green admission and hosted CI are stale
  after the required fixes and do not count toward merge readiness.
- The review fix parses the one canonical isolated launch into exact tokens,
  rejects duplicate, conflicting, or equals-form mode arguments, and admits
  only a closed daily/weekly RRULE component set with unit interval, no
  termination condition, and at most one bounded time/day selector. Descriptor
  owners now receive the current operation's primary exception explicitly, so
  an outer `except` block cannot suppress a successful-path close failure while
  a local primary still retains cleanup failure as secondary evidence.
- Automation root, stable-ID directory, and record identities now include the
  BSD write/delete restriction mask and reject any nonzero restricted state on
  initial validation or revalidation. Tests cover initial directory and file
  flags, final descriptor flag drift, ambiguous modes, low-frequency or
  terminating RRULEs, ambient-exception close failure, and local-primary close
  precedence.
- The review-fix implementation passes its focused regressions 3/3, the full
  v2 CLI/cutover class 52/52 in 64.407 seconds, module boundaries 19/19 with
  exact branch inventory 8,860, CI contracts 6/6, and production-marker
  integration 2/2 in 42.271 seconds. Ruff 0.13.2 lint/format and `git diff
  --check` pass. Current discovery is 1,648 tests, partitioned exactly once as
  390, 440, 450, and 368; complete final-head execution remains a hosted-CI
  prerequisite before merge.
- The fresh-context review of signed head `9be24f25` found two remaining
  production-boundary gaps. An equals-form `--publisher-gpg-program` could
  override the authenticated standalone argument, and relative publisher paths
  were resolved from ambient working-directory state. Three shared cleanup
  owners also inferred their primary failure through `sys.exception()`, so an
  unrelated outer `except` could suppress a successful-path close failure.
- Production prompt validation now recognizes both publisher-argument forms,
  rejects duplicates and equals-form overrides, and requires the one canonical
  standalone value to be an absolute normalized path. Executable, repository,
  history-worktree, ACL, atomic-create, and rollback cleanup chains capture and
  pass only their local operation primary; all cleanup attempts still run, a
  local primary receives bounded secondary evidence, and a close-only failure
  remains actionable even inside an unrelated outer exception handler.
- The current implementation passes focused regressions 5/5, the complete CLI
  class 52/52 in 62.964 seconds, safe I/O 45/45, publication invariants 30/30,
  durable publication 86/86 in 2,836.580 seconds, legacy history worktree 4/4,
  module boundaries 19/19 with exact branch inventory and cap 8,861, and CI
  contracts 6/6. Ruff 0.13.2 lint/format, both workflow files under
  `actionlint`, the official OpenAI skill validator, project-journal
  validation, and `git diff --check` pass. Complete final-head execution and
  both Codex processors remain required before merge.
- Signed head `b97a2781` passed exact-secret admission and hosted CI, including
  all 1,648 tests partitioned exactly once as 390, 440, 450, and 368. Its
  fresh-context Codex review found one remaining public-CLI ambiguity:
  `argparse` accepted repeated `--publisher-gpg-program` values with
  last-value-wins behavior and allowed later working-directory normalization of
  a relative raw value. Those otherwise-clean head-bound results became stale
  when the finding required a new commit.
- The parser boundary now owns publisher executable admission through one
  reusable action for both `doctor` and `start`. It rejects split-form and
  equals-form duplicates and requires the raw argument to be one canonical
  absolute path before any normalization or filesystem lookup. Regressions
  cover both commands and relative, non-normal, double-root, and duplicate
  inputs. The focused regression passes 1/1, the complete CLI class passes
  52/52 in 62.944 seconds, module boundaries pass 19/19 with exact branch
  inventory and cap 8,864, CI contracts pass 6/6, and Ruff 0.13.2 lint and
  formatting plus `git diff --check` pass.
- Signed head `fdfc4520` passed exact-secret admission and hosted CI, then its
  fresh-context Codex review found four remaining issues. The review gate used
  a mutable major-version Action reference; retained-output privacy checks did
  not share the complete extractor credential policy; cutover prompt parsing
  accepted a double-root publisher path that the CLI rejected; and export
  destination claims could persist before rejecting the active run or an
  incompatible existing target. That head's admission, CI, and review evidence
  became stale when these findings required a new commit.
- The review gate now pins audited Action commit
  `2a7f9d8cd98f90cb56dc1540bf54d9dc7484afc6`. Extractor redaction, retained
  safe-string validation, reviewed prose, report reread, and final retained
  validation share one complete credential detector covering service tokens,
  bearer values, JWTs, and generic token/secret assignments. CLI and cutover
  prompt admission share one raw canonical-absolute executable-path predicate.
- Export assembles one exact artifact map and stages or recovers it under the
  destination lock. Missing-sidecar recovery first reconciles the candidate
  with any full retained descriptor and persists that exact descriptor before
  strict claim recovery. Malformed, oversized, or conflicting targets cannot
  leave a claim, and callback failures cannot be misclassified as invalid
  targets. Legacy path-only claim behavior is physically isolated in a
  compatibility-only helper that the production export command cannot reach.
  Run ancestors and cleanup roots remain rejected before staging.
- Retained credential handling now shares one detector and one private-key
  boundary across extractor redaction, post-redaction, reviewed prose, report
  reread, and final retained validation. Complete and truncated private-key
  blocks, complete Authorization lines, GitHub token families, JWT-shaped
  service tokens, and other credential forms are consumed without retaining
  tail fragments. Independent credential and export-transaction audits both
  reached `No findings.` after the fixes.
- The main CLI remains at 1,998 lines; the four export helpers are 224, 244,
  210, and 67 lines; executable authority remains at its 350-line cap. Module
  boundaries pass 19/19 with exact branch inventory 8,874. The affected
  export, CLI, result, and publication modules pass 210/210 in 94.699 seconds;
  the final private-key audit module passes 17/17 and publisher-canary support
  passes 7/7.
- Final Python 3.13 discovery contains 1,662 unique tests partitioned as 395,
  444, 450, and 373. Shard 0 passes 395/395 in 1,360.653 seconds and shard 1's
  original 443 tests pass in 1,056.997 seconds. The only shard-2 failure was the
  superseded private-key expectation; after its test identifier moved to shard
  1, all 450 final shard-2 members had already passed, and the replacement test
  passes in the complete 17-test audit module. The only shard-3 failure was a
  15-second publisher canary under four-way host contention; the other 372
  members passed and the exact canary passes without contention in 0.624
  seconds, followed by the complete 7-test module. This disjoint composite
  covers every final test identifier exactly once. Earlier import-only and
  owner-runtime-rejected attempts remain explicitly non-counting. Ruff lint
  and formatting, both workflows under `actionlint`, CI contracts 7/7, skill
  contracts 5/5, the official OpenAI skill validator, project-journal
  validation, and `git diff --check` also pass on this tree.
- Signed head `1db57a45` passed exact-secret admission and all hosted CI shards,
  then its fresh-context Codex processor found one remaining retained-history
  privacy gap. The shared v2 detector did not recognize several credential
  assignment forms already handled by source extraction, including
  `client_secret`, `pwd`, `credential`, compact `refreshToken`, space-form
  `--token`, `rk-*` service tokens, and private-key labels such as DSA. That
  head's admission, CI, and review evidence became stale when the finding
  required a new commit.
- `privacy_locators.py` remains the sole v2 credential-policy owner, but now
  covers delimited and compact credential fields, assignment and narrative
  forms, space-form CLI arguments, `sk-*` and `rk-*` service tokens, and a
  bounded generic private-key label. Safe redaction placeholders and status
  values such as `missing`, `required`, and token-budget prose remain exempt.
  The same patterns drive extractor post-redaction, leak scanning, retained
  artifact assembly, artifact reread, and `report.md` validation.
- The exact credential regressions pass 2/2. Complete affected modules pass
  result validation 65/65 and export/reporting 66/66; the retained-result audit
  passes 17/17, module boundaries pass 19/19 with unchanged branch inventory,
  CI contracts pass 7/7, and skill contracts pass 5/5. Ruff lint and formatting
  plus `git diff --check` pass on the fix tree.
- The fresh-context review of signed head `6dc57b29` found one additional
  credential-boundary issue. A safe placeholder's closing delimiter was
  accepted as the terminal boundary without proving that the retained value
  ended there, so a suffix appended to `[REDACTED_CREDENTIAL]` could bypass all
  consumers of the shared detector. That head's review and other head-bound
  evidence became stale when the finding required a new commit.
- Safe credential states now parse either one bare reviewed status or one
  complete matching `[]`, `<>`, `()`, or `{}` envelope, then require a true
  outer value terminator. Placeholder-plus-suffix and unmatched-closer forms
  fail closed. Five adversarial suffix forms pass through extractor
  post-redaction with no retained tail and are rejected independently at
  artifact assembly, retained reread, and `report.md` validation. Complete
  affected modules remain green at 65/65, 66/66, 17/17, 19/19, 7/7, and 5/5.
- The fresh-context review of signed head `9f5ca96e` found one further variant:
  a safe placeholder or status followed by whitespace and credential material
  could still exempt the prefix while leaving the trailing value unredacted.
  That head's review and other head-bound evidence became stale when the
  finding required a new commit.
- Safe-value exemption now requires the complete remaining value to contain
  only its matching envelope, reviewed punctuation, and whitespace. Atomic
  separator and quote parsing prevents regex backtracking from moving the
  value boundary. A separate bounded suffix branch crosses ordinary, Unicode,
  vertical, and newline whitespace plus arbitrary punctuation to consume the
  first trailing material token; ordinary unsafe values still consume one
  token so later URL and path signals remain independently redacted.
- Adversarial regressions cover concatenated, quoted, spaced, vertical-tab,
  non-breaking-space, newline, and multi-punctuation suffixes across assignment,
  Authorization, Bearer, CLI, and narrative forms. Safe complete values with
  repeated or Unicode spacing and ordinary token prose remain exempt. The
  result and export modules each pass 66/66, retained-result audit passes
  17/17, module boundaries pass 19/19, CI contracts pass 7/7, and skill
  contracts pass 5/5. Ruff lint and formatting, `bash -n`, ShellCheck, and
  `git diff --check` pass.
- The first four-shard attempt was interrupted and is explicitly non-counting
  after static review found the Unicode-whitespace variant; all four deadline
  supervisors and test runners were then proved absent. The final frozen tree
  contains 1,663 unique tests partitioned exactly once. Shards 0 through 3 pass
  395/395 in 1,378.018 seconds, 445/445 in 1,086.661 seconds, 450/450 in
  1,200.665 seconds, and 373/373 in 1,178.999 seconds. All four runners exit
  zero and the retained log failure scan is empty.
- Signed head `d52c78fd` passed exact-secret admission and all four hosted and
  local test shards, then its fresh-context Codex processor found two remaining
  shared-detector issues. Quoted structured values stopped after the first
  whitespace-delimited word, while narrative status prose inherited the
  complete-value boundary used by assignments and headers. Those head-bound
  admission, CI, and review results became stale when the findings required a
  new commit.
- Structured assignment, header, and CLI values now parse matching single or
  double quotes as one value and consume the complete quoted content. A safe
  placeholder inside a quote is exempt only when the complete retained value
  ends safely; material inside or after the quote remains credential-shaped.
  Narrative `is`, `was`, and `set to` forms use a separate reviewed status
  grammar with explicit prose connectors, so ordinary statements such as a
  credential being required before deployment or missing during a dry run
  remain prose rather than secrets. A reviewed status followed directly by an
  unrecognized value remains credential-shaped and preserves the prior
  fail-closed regression.
- Focused adversarial coverage includes multiword and punctuation-only quoted
  passwords, safe-placeholder prefixes with those suffixes, outside-quote
  suffixes, and safe narrative continuations. Complete affected modules pass
  result validation 66/66, export/reporting 66/66, and retained-result audit
  17/17. Module boundaries pass 19/19, CI contracts pass 7/7, and skill
  contracts pass 5/5.
- Two intentionally retained concurrent full-suite attempts each completed
  1,662 of 1,663 test identifiers but exposed separate publisher-canary timing
  failures. The first real canary exceeded its 15-second budget under four-way
  host contention; its exact retry and complete seven-test support module then
  passed without contention. The second attempt showed that the synthetic
  inherited-pipe test's 0.5-second budget could expire before the fake Python
  GPG process created its child-PID receipt. Neither partial shard is counted
  as an all-green partition.
- The synthetic timeout test now allows five seconds for interpreter startup
  while its 60-second inherited child still forces the same deadline and
  process-group cleanup path; no production canary limit changed. The exact
  regression passes 1/1 in 5.028 seconds and the support module passes 7/7 in
  6.995 seconds. On the final production tree, shards 0, 1, and 3 pass 395/395
  in 1,169.001 seconds, 445/445 in 877.733 seconds, and 373/373 in 950.457
  seconds. The only test modified after those partitions belongs to shard 2;
  its complete final-tree partition passes 450/450 in 890.352 seconds. This
  disjoint composite covers all 1,663 stable test identifiers exactly once;
  hosted CI must still rerun all four partitions on the signed commit.

- Signed head `4050e02c` passed exact-secret admission and all four hosted CI
  partitions, then its fresh-context Codex processor found three remaining
  shared-privacy-detector issues. An unsafe quoted value stopped at its first
  closing quote and could leave a same-shell-word suffix, any supported private
  key `END` label could close a different `BEGIN` label, and reviewed compound
  narrative states such as `not required` were rejected as credential
  material. The lane's postvalidation repeated the exact 25-commit graph and
  local-config receipts, the trusted manifest, skill, and guard digests stayed
  unchanged, and the identity-bound private review workspace was removed.
- Quoted assignment, header, CLI, and narrative values now consume adjacent
  quoted and unquoted shell fragments, including escaped whitespace and
  multiline quoted content. Private-key redaction walks normalized boundary
  labels, tracks same-label nesting, accepts only the corresponding `END`, and
  redacts through end of input when no matching boundary exists. The narrative
  grammar explicitly permits only the reviewed `not required`, `not present`,
  and `not available` compounds at a true terminator or before a reviewed prose
  connector; an unknown following value remains credential-shaped.
- Exact adversarial coverage includes every value context, adjacent quoted and
  bare fragments, escaped and multiline shell values, mismatched, missing,
  different-label nested, and same-label nested private-key blocks, safe
  compound prose, and compound-status credential suffixes. Complete affected
  modules pass result validation 68/68, export/reporting 66/66, retained-result
  audit 17/17, and module boundaries 19/19 with exact branch inventory 8,881.
  Ruff lint and formatting pass on every edited Python file.
- One four-shard run was deliberately interrupted and is non-counting because
  the same-label nesting regression was added after those runners started; all
  four obsolete runners were proved absent before retry. The frozen code tree
  contains 1,665 unique tests partitioned exactly once. Shards 0 through 3 pass
  397/397 in 1,121.424 seconds, 445/445 in 841.169 seconds, 450/450 in 940.666
  seconds, and 373/373 in 904.847 seconds. Every runner exits zero and the
  retained logs contain no failure summary.
- Signed follow-up `a9124829` implements the three findings, and signed
  fixture-only follow-up `da8a2346` constructs private-key-shaped adversarial
  test values from non-secret fragments so exact-secret admission remains an
  independent production-tree gate. Exact-secret admission for
  `a3836660..da8a2346` is clean with complete temporary cleanup.
- The fresh-context Codex processor for `a3836660..da8a2346` found one final
  retained-privacy gap: an exact credential value ending in punctuation-only
  material after a safe redaction marker could evade the trailing-material
  detector once its field context was removed. Postvalidation reproduced the
  exact 27-commit, 26-edge graph and local-config receipts, trusted control
  digests remained unchanged, and the identity-bound reviewer workspace was
  removed.
- The detector now treats a nonempty pure non-word suffix extending to the
  absolute end of the retained value as credential material while preserving
  the existing complete-placeholder and reviewed punctuation terminators.
  Exact assignment, Authorization, CLI, and narrative regressions cover both
  extractor redaction and retained-artifact assembly/reread. The result module
  passes 69/69, export/reporting passes 66/66, retained-result audit passes
  17/17, and module boundaries pass 19/19 with unchanged exact branch inventory
  8,881. Ruff lint and formatting pass for all three edited Python files.
- Full-suite attempts started on the superseded `da8a2346` tree were
  deliberately interrupted after this finding and are non-counting; their
  runner processes were proved absent. The superseding signed head must rerun
  the four exact partitions before final delivery.
- Signed head `f424d646` closes the punctuation-only suffix gap. Its local
  Python 3.13 partitions pass 397/397 in 1,066.093 seconds, 446/446 in 807.337
  seconds, 450/450 in 900.799 seconds, and 373/373 in 870.166 seconds. Hosted CI
  passed the same four partitions and aggregate gate, and exact-secret
  admission was clean with complete temporary cleanup. The fresh-context Codex
  processor then found two control-plane issues, so that head's otherwise-green
  evidence is stale for delivery: resumed runs could retain their old prompt
  digest while consuming new in-memory agent instructions, and the documented
  ambient/Homebrew Python entrypoint could fail the transport executable
  ancestor authority contract.
- The executable prompt, version, and resume validator now have one dedicated
  deterministic foundation module. Every checkpoint load and direct retained
  export validates the persisted self-digest plus the current prompt and policy
  contract; remote helper commitments remain governed by their separate
  run-owned snapshot and lease revalidation contract. The low-level state
  component receives the validator through its runtime context and does not
  import high-level orchestration services.
- Production coordination now uses the fixed owner-controlled copied runtime
  at `~/.codex/session-retrospective/runtime/bin/python3`, created by replacement
  sync with Python 3.13-or-newer `venv --copies`. `doctor` and `start`
  authenticate the exact isolated interpreter and its ancestor access policy;
  source transport, descriptor-bound Git, and remote-helper launches inherit
  that same `sys.executable`. Automation cutover records require the exact
  installed runtime path and reject ambient or non-isolated launch forms.
- Focused final-tree evidence passes the 11 new and adjacent regressions, CLI
  60/60, source transport 102/102, result-contract audit 17/17, publication
  marker transaction 1/1, and module boundaries 19/19. Ruff lint and formatting
  plus `git diff --check` pass. The final four disjoint repository partitions,
  signed replacement head, exact-secret admission, and fresh review processors
  remain the delivery gates.
- An intermediate four-shard attempt was deliberately interrupted and is
  non-counting after final review of the production runtime contract found that
  the coordinator still needed to compare `sys.executable` with the exact fixed
  installed path. All four deadline supervisors and test runners exited 130 and
  were proved absent before the final-tree checks resumed.
- The final runtime-path implementation authenticates that exact installed
  executable rather than only its Python flags and ancestry. On this frozen
  tree, the complete CLI module passes 60/60 in 87.306 seconds, source transport
  passes 102/102 in 24.655 seconds, and orchestration passes 114/114 in 212.957
  seconds. These focused results supersede the pre-tightening module runs.
- The final frozen tree contains 1,669 unique test identifiers partitioned
  exactly once as 397, 446, 451, and 375 tests. Shards 0 through 3 pass 397/397
  in 1,041.627 seconds, 446/446 in 787.938 seconds, 451/451 in 881.784 seconds,
  and 375/375 in 850.763 seconds. Every bounded runner exits zero, every shard
  reports `OK`, and the retained-log failure scans are empty.
- Signed head `4562670f` persisted the executable prompt digest and fixed
  copied-runtime launch contract. Its exact-secret admission was clean and its
  hosted/local test evidence began green, but the next fresh-context Codex
  processor found two remaining control-plane gaps; all head-bound evidence is
  stale. Resume validation did not bind every command to the same persisted
  coordinator-runtime authority, and the six executable prompts still omitted
  normative behavior that existed only in the operator reference. The topic
  reference also named the obsolete `topic_review_result_v2` schema.
- The follow-up stores a non-sensitive canonical-path binding digest and a
  separate executable identity/content/access-policy authority digest in the
  execution provenance and `configuration_root`. Every checkpoint read or
  transition reauthenticates the current runtime before consuming model work.
  Retained-history validation admits only the closed runtime receipt and never
  retains its local path.
- All six executable agent instructions now contain the normative redaction,
  review, adjudication, topic, and synthesis behavior and are byte-equal to six
  independently delimited reference blocks. Topic reduction names the actual
  `topic_reduction_result_v2` schema. Complete-envelope fit checks share the
  exact immutable-task builder with task creation and include the final job
  metadata; the hierarchy regression retains a 128 KiB artificial cap, well
  below the 512 KiB production cap while remaining above one indivisible topic
  result.
- Focused prompt/runtime regressions pass 4/4, source transport passes 102/102,
  export/reporting passes 66/66, and the exact hierarchy-cap regression passes
  after the shared envelope builder fix. The final affected modules, static
  gates, repository partitions, signed replacement head, admission, hosted CI,
  and both Codex processors remain required.
- The first final four-shard attempt after those fixes was deliberately
  interrupted and is non-counting when protected-property review found that the
  runtime path digest performed a second `realpath` observation after the
  executable authority receipt. The digest now consumes the already
  authenticated `authority.path`, preventing an authority/path receipt from
  combining two different filesystem observations. All four obsolete runners
  exited 130 and were proved absent before the final-tree rerun.
- A subsequent pre-final shard attempt was also interrupted and is non-counting
  after a test-only assertion was added to prove the same runtime mismatch
  blocks the direct retained-export path as well as ordinary checkpoint reads.
  Its four runners also exited 130 with no residual test process. Two optional
  dirty-tree read-only audits did not return a terminal artifact after bounded
  waiting and one conclude request; they were closed as transport-inconclusive
  and do not count toward the required signed-head Codex gate.
- The final Python 3.13 implementation/test tree contains 1,671 unique test
  identifiers partitioned exactly once. Shards 0 through 3 pass 397/397 in
  1,344.062 seconds, 447/447 in 1,025.943 seconds, 452/452 in 1,144.609
  seconds, and 375/375 in 1,098.442 seconds. All four deadline supervisors exit
  zero and every retained log contains an explicit `OK` terminal summary.
- The next fresh-context Codex processor found five related contract gaps: the
  native envelope exposed only a result-schema name, topic reduction copied
  deterministic inputs instead of validating semantic output, claim-size
  projection omitted final claim metadata, run provenance did not bind the
  coordinator source implementation, and the migration helper retained a
  second SSH/host implementation.
- Native jobs now receive complete closed JSON Schemas and exact worst-case
  claim projections. Topic reductions preserve validated recurrence, guidance,
  prompt-rewrite, skill-candidate, and open-work records through hierarchical
  reduction and retained history. Every resumed command reauthenticates the
  closed coordinator Python inventory, source bytes, and access policy.
  Production remote verbs delegate to the canonical `remote-host-context` CLI;
  the old probe remains only as a test fixture for migration compatibility.
- Focused final-tree evidence passes orchestrator 120/120, export/reporting and
  architecture contracts 93/93, and the six publication calendar-drift
  regressions 6/6. One four-way local shard attempt covered all 1,678 tests but
  exposed six publication test methods whose fixed July retention clock had
  become expired relative to the real August wall clock. The tests now bind
  CLI calls to their fixture clock while explicit expiry and GC use their
  separate later clocks; the exact serial rerun passes 6/6. A final all-green
  repository partition remains required before the replacement head is signed.
- The final implementation/test tree contains 1,678 unique test identifiers,
  partitioned exactly once as 398, 450, 448, and 382 tests. In the first
  four-process execution, shards 0 and 2 passed 398/398 in 3,016.097 seconds and
  448/448 in 2,418.716 seconds. Shard 3 encountered one bounded-signing canary
  failure under contention; its complete serial rerun passed 382/382 in
  2,372.443 seconds. Shard 1 encountered one attempt-lock scheduling timeout
  under the same contention; its complete serial rerun passed 450/450 in
  1,861.131 seconds and crossed the previously failing lock case. The two
  contended shard attempts are non-counting. The unchanged-tree composite
  evidence is therefore 1,678/1,678 with every selected partition terminating
  `OK`. Final skill, CI, and module-boundary contracts pass 31/31; Ruff lint,
  exact changed-file formatting, `git diff --check`, and the OpenAI skill
  validator also pass. Signing, admission, and review gates remain.
- Signed and pushed head `dc89489b` closed the executable agent-result
  contracts. Exact-secret admission and hosted CI were clean. A fresh-context
  Codex processor in a prior-trusted, independently materialized workspace then
  returned four actionable findings, so all head-bound readiness evidence became
  stale: legal child unions could exceed episode/topic parent result bounds;
  verbose per-item adjudication rows could make a legal result unrepresentable;
  recurrence claims were not bound to selected revision-level signals; and topic
  hierarchy task sidecars stored complete child results in both payload and
  metadata. Postvalidation was clean and the reviewer task root was removed.
- Hierarchical episode and topic parents now copy a compact recursive commitment
  containing immediate child hashes, leaf-result count, per-field item counts,
  and a canonical source-tree hash. Visible parent records are bounded verbatim
  multisets of child data; multiplicity cannot exceed source multiplicity. Topic
  outputs retain non-empty revision/episode/session lineage, exact risk union,
  recursive decisions, and confidence floors while the commitment makes every
  compacted source item explicit.
- Adjudication now uses exactly twelve candidate/field rows. Each row binds the
  candidate hash and reviewer slot and carries one closed decision code per item
  in source order. The compact shape remains representable for two candidates at
  every declared field maximum. Leaf recurrence validation now proves that every
  selected revision carries the named signal type and kind, intersects cited
  evidence, and maps to exactly the listed sessions. Hierarchical recurrences
  can only reuse a validated child record.
- Topic hierarchy task inputs now store child results only in
  `input_payload.child_topic_results`; metadata retains hashes and scheduling
  identities. A near-limit regression proves that the single representation
  fits while the retired duplicate representation exceeds the authenticated
  640 KiB sidecar bound. The result/episode, schema-audit, hierarchy-cap,
  sidecar, and module-boundary focused set passes 113/113. The complete
  orchestration module ran 121 tests in 555.879 seconds; 120 passed and one
  generic schema-example fixture rejected the new closed decision-code pattern.
  Its exact repaired test and the complete affected focused set pass. Final
  repository partitions, signed replacement head, admission, hosted CI, and the
  two required Codex processors remain required.
- The final dirty-tree inventory contains 1,682 unique Python 3.13 tests,
  partitioned exactly once as 401, 451, 449, and 381 tests. An initial
  four-process attempt lost every supervisor with no terminal summary when its
  tool sessions were closed; shard 3 had also reported one contended signing
  canary failure. That entire attempt is non-counting. A replacement durable
  four-process run wrote owner-only atomic status records and completed every
  partition with exit zero: shard 0 passed 401/401 in 2,060.454 seconds, shard 1
  passed 451/451 in 1,605.167 seconds, shard 2 passed 449/449 in 1,772.683
  seconds, and shard 3 passed 381/381 in 1,672.423 seconds. Every retained log
  contains an explicit `OK` terminal summary, including the signing canary that
  failed only in the discarded attempt.
- Signed head `5990f182` passed the then-current local and hosted gates, but its
  fresh-context Codex processor found five actionable contract gaps. Synthesis
  leaf validation compared a subset against the complete topic inventory;
  automation cutover admitted commands by substring instead of exact document
  equality; hierarchical parents could not derive complete signal commitments
  after compaction; the 128-item topic-hash array made larger valid runs
  unrepresentable; and rejected-result idempotency omitted the legal rejection
  reason. All head-bound delivery evidence is stale.
- Synthesis now uses an authenticated recursive lineage owner. Every leaf and
  parent carries a compact count-and-SHA-256 topic-result commitment, exact
  per-signal commitments, and bounded deterministic exemplars derived from its
  subtree. Only the final hierarchy root is compared with the complete accepted
  topic inventory, so legal leaf subsets and more than 128 topic roots remain
  representable without losing complete-union proof.
- Automation cutover now accepts only the exact seven-field TOML document and a
  byte-equal canonical production prompt. Prefixes, suffixes, leading
  whitespace, control characters, unknown fields or tables, and alternate
  command shapes fail closed. Rejected-result actions now use a versioned
  binding that commits the allowlisted reason; changing only that reason is an
  idempotency conflict.
- Focused post-fix evidence passes result/schema validation 91/91, automation
  cutover 15/15, the publication fixture 1/1, real hierarchical synthesis and
  rejection replay 4/4, and module boundaries 19/19. The module aggregate
  remains within its prior 3,050-line cap, and the new lineage owner has a
  separate 225-line ceiling. Final static checks, complete repository
  partitions, signed replacement head, admission, hosted CI, and both required
  Codex processors remain delivery gates.
- Two bounded read-only audits then found four additional edge cases before the
  replacement head was frozen. Ordinary accepted-result and failure replays
  incorrectly compared an absent rejection reason; canonical Unicode
  executable paths reached an ASCII-only constant-time string comparison;
  high-severity independent reviews in a sibling synthesis leaf were checked
  against an incomplete local topic subset; and Python numeric equality allowed
  Boolean or floating-point commitment counts to compare equal to integers.
  Replay validation now scopes reason equality to rejected payloads, prompt
  equality compares canonical UTF-8 bytes, review/topic union enforcement runs
  only after sibling synthesis subtrees rejoin at the final root, and commitment
  equality uses canonical type-preserving JSON.
- The first 1,684-test durable partition attempt after those audits was stopped
  deliberately and is non-counting because the additional findings changed the
  tree. All four supervisors and their remaining test process groups were
  terminated once, proved absent, and their owner-only logs and status files
  remain only as discarded-run evidence. The repaired real hierarchy test also
  exposed a test-fixture ordering bug: adjudication candidates must be rebuilt
  in manifest hash order rather than global review completion order. The exact
  path now passes five consecutive executions. Current-tree focused evidence
  passes 25/25 targeted contracts, 110/110 complete result/schema/module tests,
  and 63/63 CLI plus production-marker tests; changed-file and repository-wide
  Ruff lint, exact changed-file formatting, and `git diff --check` are clean.
- The final Python 3.13 tree contains 1,685 unique test identifiers partitioned
  exactly once as 403, 451, 448, and 383 tests. A new owner-only durable run
  completed every partition with exit zero: shard 0 passed 403/403 in 1,749.522
  seconds, shard 1 passed 451/451 in 1,370.213 seconds, shard 2 passed 448/448
  in 1,507.873 seconds, and shard 3 passed 383/383 in 1,443.955 seconds. Every
  retained log contains an explicit `OK` terminal summary. Signing, exact-secret
  admission, hosted CI, and the two required Codex processors remain delivery
  gates.
- Signed and pushed head `f015d6d4` closed the topic-lineage, cutover-document,
  typed-commitment, and replay gaps. Its fresh-context Codex processor found two
  further representability defects: global synthesis could emit at most twenty
  rewrites while retained export required one synthesis row for every
  high-impact turn, and hierarchy fit probes omitted the real synthesis turn-ref
  sidecar while task creation authenticated it under the 640 KiB bound.
  Postvalidation retained the exact range and trusted-control digests, and the
  independent reviewer workspace was removed after the terminal findings were
  accepted.
- Synthesis now derives every rewrite from accepted resolved episode reviews,
  commits the complete canonical rewrite set by count and SHA-256, and supplies
  at most twenty deterministic exemplars to each leaf and parent. Result
  validation rejects either a changed commitment or a changed exemplar set
  before acceptance. Retained export rebuilds the complete evidence from
  high-impact turn findings, verifies the same commitment, and treats synthesis
  rows as bounded exemplars rather than an impossible complete enumeration.
- Hierarchy sizing now serializes the exact immutable task sidecar, including
  the real partition reference, metadata, and complete allowed-turn set, before
  task creation. Synthesis leaf and parent turn refs are restricted to their
  authenticated topic/review subtree, so oversized legal runs partition instead
  of passing a trimmed probe and failing during materialization.
- Current-tree focused evidence passes result/export/schema/module checks
  179/179 in 13.775 seconds, the exact rewrite and sidecar regressions 5/5 in
  1.218 seconds, capacity and module checks 21/21 in 4.870 seconds, the two
  previously failing orchestration cases 2/2 in 3.028 seconds, and the complete
  orchestration module 123/123 in 451.942 seconds. The combined contract, CLI,
  Skill, result, and retained-history suite passes 1,164/1,164 in 405.078
  seconds. Ruff 0.13.2 lint and formatting, Python 3.13 byte compilation, and
  `git diff --check` are clean. Final repository partitions, signed replacement
  head, admission, hosted CI, and both required Codex processors remain the
  delivery gates.
- The final Python 3.13 implementation and documentation tree contains 1,688
  unique test identifiers partitioned exactly once as 404, 452, 449, and 383
  tests. A new owner-only durable run completed every partition with supervisor
  exit zero: shard 0 passed 404/404 in 1,754.507 seconds, shard 1 passed 452/452
  in 1,344.398 seconds, shard 2 passed 449/449 in 1,508.714 seconds, and shard 3
  passed 383/383 in 1,425.396 seconds. Every retained log contains its exact
  `Selected`, `Ran`, and `OK` terminal lines, and the combined failure/traceback
  scan is empty.
- Signed and pushed head `c5e9a472` passed exact-secret admission and all six
  hosted CI jobs. Its metadata-correct fresh Codex processor found one remaining
  capacity mismatch: review/topic merge grouping measured only the non-final
  run-input reference and metadata, while a one-group result is created with
  the longer root reference and final metadata. A boundary input could therefore
  pass grouping and fail only during authenticated task creation. The reviewer
  workspace passed postvalidation, the trusted control manifest remained
  unchanged, and the task root was removed.
- Review and topic reduction now build every candidate task from one exact
  domain-specific input builder. Greedy grouping requires both the intermediate
  and final serialized forms to fit, and creation repeats the exact selected-form
  check before staging. Separate episode and topic regressions simulate the
  boundary where only the non-final form fits; both split into non-final groups,
  and the existing complete hierarchy-cap test still converges. The two boundary
  regressions pass 2/2 and the combined focused set passes 3/3. Final full-tree
  tests, signing, admission, fresh review, hosted CI, and GitHub Codex evidence
  remain required for the replacement head.
- The replacement Python 3.13 tree contains 1,690 unique test identifiers
  partitioned exactly once as 404, 452, 450, and 384 tests. The final bounded
  run completed every partition with supervisor exit zero: shard 0 passed
  404/404 in 1,721.829 seconds, shard 1 passed 452/452 in 1,348.571 seconds,
  shard 2 passed 450/450 in 1,499.767 seconds, and shard 3 passed 384/384 in
  1,420.932 seconds. Every log contains exact `Selected`, `Ran`, and `OK`
  terminal lines, and the combined traceback/failure scan is empty. Signing,
  admission, fresh review, hosted CI, and GitHub Codex evidence remain.
- Signed and pushed head `59e05774` closed the final-vs-intermediate reduction
  sizing gap and passed exact-secret admission. Its fresh-context Codex
  processor found two remaining P1 representability defects: complete turn and
  episode-revision arrays were copied through every reduction level, so a legal
  large run could never converge to a bounded final sidecar; and adjudication
  plus initial topic leaves did not probe the exact sidecar later supplied to
  task creation. That head's review and CI evidence is stale.
- Complete reduction lineage is now represented by type-preserving canonical
  count-and-SHA-256 commitments, while task-visible turn and episode references
  are bounded projections of already accepted child results. Review, topic,
  adjudication, and synthesis task construction use shared exact input builders
  for both capacity probing and creation. A hierarchy may perform one bounded
  compaction when only the non-final shape fits, but an unchanged task count or
  a still-oversized final shape fails explicitly instead of looping.
- Current-tree regressions cover 3,000-member turn and episode lineages,
  near-boundary adjudication and topic-leaf sidecars, exact probe/create
  identity, bounded synthesis turn authorization, and hierarchy no-progress.
  Result and episode validation passes 76/76 in 1.427 seconds, module boundaries
  pass 19/19 in 1.979 seconds, and the complete orchestrator module passes
  129/129 in 490.965 seconds. Ruff lint and changed-file formatting plus
  `git diff --check` are clean.
- The final Python 3.13 tree contains 1,695 unique test identifiers partitioned
  exactly once as 405, 455, 449, and 386 tests. One durable four-process run
  completed every partition with supervisor exit zero: shard 0 passed 405/405
  in 1,639.689 seconds, shard 1 passed 455/455 in 1,274.751 seconds, shard 2
  passed 449/449 in 1,413.625 seconds, and shard 3 passed 386/386 in 1,340.130
  seconds. Every retained log contains exact `Selected`, `Ran`, and `OK`
  terminal lines, and the combined traceback/failure scan is empty. Signing,
  admission, fresh review, hosted CI, and GitHub Codex evidence remain delivery
  gates.
- Signed and pushed head `a6102a80` closed the recursive reduction-lineage and
  sidecar-capacity defects, passed exact-secret admission, and passed all
  hosted CI producers. Its fresh-context Codex processor then found two
  release blockers: the publication canary searched only the signing-key
  position in `VALIDSIG` and therefore rejected a valid signing subkey, while
  Ubuntu-only CI skipped the real Darwin ACL security contracts. The lane
  postvalidation reproduced its exact 36-commit graph and local-config
  receipts, the trusted control manifest remained unchanged, and the private
  reviewer workspace was removed. All head-bound evidence became stale.
- GPG status parsing now has one strict shared owner. Complete nine-field rows
  bind a primary signature directly; complete ten-field rows validate both the
  signing-subkey and primary fingerprints and return only the primary. The
  canary requires one exact primary match and fails closed on malformed or
  multiple rows. A realistic ten-field signing-subkey regression passes, and
  an independent read-only GPG audit returned `No findings.`
- CI now has a required `macos-15` producer under an owner-controlled copied
  Python 3.13 runtime. Ten ACL and Darwin access-policy tests carry one shared
  marker, are discovered from the complete unittest inventory, and must match
  one canonical policy tuple. Direct platform skips are forbidden by contract;
  skipped, expected-failure, partial, duplicate, missing, or extra inventory
  cannot pass the producer or aggregate job. The producer also verifies the
  active Python leaf's canonical path, regular-file type, owner, mode, and link
  count before test discovery.
- The first post-review full attempt is non-counting. A bounded read-only audit
  found that its initial Darwin runner admitted skipped tests, maintained only
  hand-copied inventories, and relied on Ubuntu to validate the macOS runtime.
  All four task-owned supervisors and their four orphaned test process groups
  were terminated once and proved absent before the fixes. A later optional
  final-tree audit returned no terminal artifact within ten minutes and was
  closed as transport-inconclusive; it supplies no review result.
- Final focused evidence passes CI contracts 11/11, the dynamically selected
  Darwin security inventory 10/10 in 60.655 seconds, and the combined GPG,
  CI, and module-boundary group 38/38 in 11.581 seconds. Ruff lint and changed
  file formatting, `actionlint`, the official OpenAI skill validator,
  project-journal validation, and `git diff --check` pass on the same tree.
- The final Python 3.13 tree contains 1,700 unique test identifiers partitioned
  exactly once as 405, 456, 452, and 387 tests. One owner-only durable run
  completed every partition with supervisor exit zero: shard 0 passed 405/405
  in 1,785.877 seconds, shard 1 passed 456/456 in 1,436.994 seconds, shard 2
  passed 452/452 in 1,574.257 seconds, and shard 3 passed 387/387 in 1,500.523
  seconds. Every retained log contains exact `Selected`, `Ran`, and `OK`
  terminal lines, and the combined traceback/failure scan is empty.
- A fresh-context Codex processor of signed head `5e030ff2` found four final
  control-boundary gaps. Source leases accepted caller-projected roots and host
  labels without binding the actual worker command; the public entrypoint put
  the repository `scripts/` directory on import resolution before source
  authentication; compact CamelCase credential fields could bypass retained
  privacy checks; and Retrospective duplicated the five-host registry instead
  of deriving it from `remote-host-context`. That head's review and prior
  head-bound evidence became stale.
- The authenticated `remote-host-context` helper is now the sole host-registry
  source. A bounded AST parser reads exactly one static `HOSTS` literal without
  executing helper code, normalizes canonical hosts and aliases, and freezes
  the inventory plus its helper commitment in every run. Resume, scheduling,
  publication, and remote execution reject inventory or helper drift. Local
  roots derive from the account database rather than ambient `HOME`; remote
  roots derive from the run-owned authenticated helper snapshot.
- Source transport lease v3 commits the exact execution argv prefix and lexical
  source root. The worker validates the actual OS argv, authenticated Python,
  route, host, and root before scanning. The remote relay revalidates legacy
  helper output and publishes only a locally rebound header; subagents still
  receive no SSH authority. The public v2 entrypoint is now an authenticated
  source-only bootstrap with a generated closed module manifest, while the CLI
  implementation lives inside that authenticated package. Retained credential
  assignment detection also covers bounded CamelCase secret/token suffixes.
- The first 1,721-test four-shard attempt is non-counting. Child subprocesses
  created bytecode in the authenticated source tree and two migrated fixtures
  still relied on ambient `HOME` to select a local Codex root. The shard runner
  now exports `PYTHONDONTWRITEBYTECODE=1` before discovery, with a real child
  import regression. Test-only scans use an explicit private root context;
  production continues to ignore ambient `HOME`. One later shard-0 attempt
  exposed the same stale assumption in the descriptor-to-accept CLI fixture;
  its failed 412/413 result is also non-counting. The complete adapter/CLI
  module then passed 11/11 in 50.903 seconds, including the exact repaired case.
- Final Python 3.13.12 evidence covers all 1,721 unique tests exactly once on
  the final tree: shard 0 passes 413/413 in 1,512.907 seconds, shard 1 passes
  459/459 in 1,271.819 seconds, shard 2 passes 456/456 in 1,415.460 seconds,
  and shard 3 passes 393/393 in 1,332.137 seconds. Every runner exits zero and
  reports `OK`. Ruff lint passes repository-wide; all 47 changed Python files
  pass formatting; the generated bootstrap manifest, both workflows under
  `actionlint`, the official OpenAI Skill validator, project-journal validator,
  `git diff --check`, and the no-bytecode source-tree check are clean.
- Signed head `44cda16f` passed exact-secret admission and started one fresh
  Codex processor, but hosted shard 0 exposed two bootstrap fixture failures.
  The fixture used ambient `tempfile` placement: Linux selected sticky
  world-writable `/tmp`, which the production implementation-authority chain
  correctly rejects, while the local Darwin temporary root was private. The
  processor was stopped without consuming partial output, its independent
  workspace postvalidated clean, and the task root was removed. Valid bootstrap
  fixtures now live under the owner-controlled repository root, and an explicit
  writable-ancestor regression preserves the fail-closed production property.
  The bootstrap module passes 7/7, CI contracts pass 12/12 under the exact real
  Python 3.13.12 executable, Ruff checks pass, and the new complete inventory
  contains 1,722 unique tests partitioned as 413, 460, 456, and 393.
- The next fresh-context Codex processor found two transport-authority gaps in
  the authenticated helper inventory. A helper could declare an alternate
  local label or root that the local scheduler would ignore, and executable
  code after the static `HOSTS` literal could mutate or alias that registry
  before the authenticated snapshot ran. The inventory now admits only the
  scheduler's exact `local` / `~/.codex` binding. Static helper use is closed
  to membership checks and two-level string-field reads; method mutation,
  unbound mutators, and container or row aliases fail before a run freezes the
  helper commitment.
- The inventory regressions pass 7/7, module boundaries pass 19/19, and CI
  contracts pass 12/12. The final Python 3.13.12 inventory contains 1,724
  unique tests partitioned exactly once: shard 0 passes 414/414 in 1,460.457
  seconds, shard 1 passes 461/461 in 1,128.260 seconds, shard 2 passes 455/455
  in 1,258.546 seconds, and shard 3 passes 394/394 in 1,177.375 seconds. Every
  runner exits zero with `OK`, and the combined failure and traceback scan is
  empty.
- Signed and pushed head `60f753a1` closed the static helper-registry mutation
  gap, but its fresh Codex processor found that the static projection was not
  rebound to the actual helper invocation. A follow-up read-only audit also
  identified three related boundaries: the in-process helper bootstrap must not
  be described as an arbitrary-Python sandbox, the backward-compatible relay
  supplied a component commitment and live `0755` path where its bootstrap
  required raw bytes and mode `0600`, and the installed helper does not yet
  declare the retrospective-specific commands. All evidence for that head is
  stale.
- The complete authenticated helper snapshot is now explicitly the semantic
  code trust root. Its static `HOSTS` data and top-level immutable
  `SESSION_RETROSPECTIVE_COMMANDS` capability manifest are derived without
  execution, runtime `HOSTS` is checked against
  a domain-separated commitment and replaced by immutable copies, and the
  binding is rechecked on ordinary return and `SystemExit`. This protects
  declared registry data from ordinary drift without claiming to sandbox
  arbitrary trusted Python reflection.
- Required `session-shards` and `source-transport` declarations are preflighted
  by `doctor`, `start`, and again before launch. A version-skewed run-owned
  helper produces the explicit `remote_host_context_transport_incompatible`
  source gap, distinct from remote unreachability and no activity. Snapshot
  authentication and ordinary helper execution failures remain hard failures.
  The legacy relay now copies exact helper
  bytes into a temporary owner-private `0600` snapshot, executes that raw
  digest, retains the component commitment only as provenance, and removes the
  snapshot after the bounded relay. This parent-only transaction no longer
  lives in a worker-reachable module.
- One final precommit read-only audit found five actionable classification and
  ownership gaps: authentication errors could be downgraded to compatibility,
  dead `add_parser` calls could pose as capabilities, `start` could bypass the
  doctor-only check, ordinary helper failures were mislabeled as registry
  authentication, and the legacy materializer remained worker-visible. The
  in-progress four-shard run was stopped as non-counting; all four verified
  supervisors and their four exact child process groups were terminated once
  and proved absent before edits. The fixes use one dedicated capability error,
  an immutable top-level manifest, start-time validation, distinct execution
  failure classification, and a parent-only relay owner.
- Current-tree focused evidence passes host inventory 9/9, source transport
  122/122 in 46.199 seconds, module boundaries 19/19, CI contracts 12/12,
  bootstrap 7/7, and Skill contracts 5/5. Ruff lint and changed-file formatting,
  both workflows under `actionlint`, the official OpenAI Skill validator,
  project-journal validation, generated bootstrap manifest check, and
  `git diff --check` are clean.
  The exact 16-module transport inventory is 8,681/8,690 lines and the branch
  proxy is 9,474/9,475.
- A final closure audit then found that the real relay discarded bootstrap
  failure classes and treated a missing `main` as HOSTS authentication failure.
  The four active 1,732-test supervisors were interrupted once; the bounded
  runners closed their process groups, and exact process queries found no
  matching survivor. That run is non-counting. The bootstrap now normalizes
  authenticated nonzero results, snapshot/runtime authentication failures, and
  helper entrypoint/execution failures to a closed status set. The relay raises
  separate typed errors, while the source worker catches only genuine
  unavailability. Six exact failure-class regressions pass in 1.598 seconds,
  including real relay authentication and execution paths; the complete source
  transport suite first passed 120/120 in 47.443 seconds and the updated module
  boundaries passed 19/19 in 2.328 seconds.
- Final diff inspection found that terminal stream-filter completion still ran
  before child status classification, so an execution failure after a valid
  prefix could be mislabeled as a protocol failure. The first 1,735-test shard
  run was stopped as non-counting, and exact process queries again found no
  surviving shard runner. Terminal filter completion now follows the closed
  child-status classification, and fixed bootstrap status survives diagnostic
  sink failure. Two exact regressions pass 2/2 in 0.035 seconds; complete source
  transport passes 122/122 in 46.199 seconds and module boundaries pass 19/19
  in 2.489 seconds on the resulting tree.
- The first complete 1,737-test partition run exposed one stale test fixture.
  The remote output-limit test still supplied the migration-only probe as the
  installed transport helper, so the new capability and inventory preflight
  correctly rejected it. Shards 0, 2, and 3 passed 416/416, 456/456, and
  399/399; shard 1 passed 465 tests and failed only that fixture assertion.
  The test now uses the dedicated current-contract remote-host-context helper
  fixture while the migration probe keeps its separate static-contract tests.
  The exact repaired test passes 1/1.
- The final frozen-tree Python 3.13.12 run passes all 1,737 tests with no
  failure or traceback markers: shard 0 passes 416/416 in 1,834.318 seconds,
  shard 1 passes 466/466 in 1,399.425 seconds, shard 2 passes 456/456 in
  1,572.511 seconds, and shard 3 passes 399/399 in 1,466.617 seconds. Signing,
  exact-secret admission, fresh local Codex processing, hosted CI, and
  current-head GitHub Codex remain.
- Signed head `b64a9e88` passed exact-secret admission, the fresh local Codex
  processor with `No findings.`, and complete hosted CI. The first GitHub Codex
  requests failed before review because the JoeyTeng GitHub identity was not
  connected to Codex. After that connection and an explicitly authorized
  same-head request, current-head GitHub Codex returned two actionable privacy
  findings and one branch-name finding. All clean evidence for that head is
  stale.
- Personal-identifier policy is now shared by the agent-output redactor and the
  independent retained validator. The retained scalar, reviewed prose, and
  rendered-report reread paths reject labeled names and IDs; grouped and
  compact `+` international phone numbers are detected only when they contain
  7 through 15 digits. Dates, Python versions, short numeric labels, and
  overlong grouped labels remain negative cases. The default-branch finding is
  not actionable: GitHub repository metadata, `origin/HEAD`, and PR base all
  identify `master`; `refs/heads/main` appears only as the separately owned
  retained-history target example.
- A pre-review negative probe then proved that a multi-token labeled value such
  as `employee name: Alice Smith` left the second token after redaction. The
  stale reviewer and hosted run were cancelled without accepting results. A
  labeled personal-data match now consumes the complete single-line field
  remainder, so the post-redactor cannot orphan later name tokens; focused
  agent-result and retained-boundary regressions cover the multi-token case.
  The exact three-case regression passes 3/3, the complete affected
  result-contract, retained-export, and episode suites pass 165/165 in 17.857
  seconds, and module boundaries remain 19/19 with the exact branch ceiling
  unchanged.
- The immediately preceding and current-head GitHub Codex reviews then exposed
  five more agent-output/retained-policy mismatches: UNC paths, the complete
  raw-ID label taxonomy, inline code fences, labeled internal hosts, and long
  hexadecimal identifiers outside the retained validator's old 32-64 range.
  The stale local reviewer and hosted run were stopped and cleaned without
  accepting results. Those exact regex policies now live only in
  `privacy_locators.py`; agent scanning/redaction and retained validation remain
  independent execution points over the shared closed policy. The complete
  closed-taxonomy scanner/redactor and retained-validator matrices pass,
  including 24-digit and over-64-digit identifiers; the complete affected
  suites pass 167/167 in 15.482 seconds, module boundaries pass 19/19 with an
  exact 9,474/9,475 branch inventory, and the CI, Skill, and bootstrap contract
  suites pass 24/24 under the real owner-controlled Python 3.13.12 executable.
  One earlier symlink-path invocation is non-counting because the CI contract
  correctly rejected `/opt/homebrew/bin/python3.13` before the exact rerun.
- The focused privacy and retained suites pass 164/164. The complete stable
  four-way partition executed all 1,739 test IDs: shard 0 passed 417/417 in
  2,063.272 seconds, shard 1 passed 467/467 in 1,617.616 seconds, shard 3 passed
  399/399 in 1,678.082 seconds, and shard 2 passed 455 tests before the exact
  branch-inventory assertion reported the intentional 9,465 to 9,472 policy
  increase. No production code changed after that run; the exact inventory was
  updated without relaxing its 9,475 ceiling, and the complete module-boundary
  suite then passed 19/19 in 2.125 seconds, closing the sole failed test ID.
- GitHub Codex then identified three remaining shared-policy gaps on signed
  head `3ff3eaca`: international numbers with a domestic trunk marker such as
  `+44 (0)...`, an unmatched opening code fence, and UUID forms outside
  versions 1 through 5. That head's local processor and hosted run were stopped
  as stale; the independent workspace postvalidated clean before removal. The
  shared policy now treats a bounded leading-plus candidate with 7 through 15
  digits as a phone number, consumes an opening code fence through its closing
  fence or end of text, and rejects every canonical hexadecimal UUID shape.
  Exact scanner/redactor and retained-validator regressions cover all three
  findings without changing the independent enforcement points. Four focused
  regressions pass 4/4 in 0.401 seconds; the complete affected result-contract,
  retained-export, and episode suites pass 167/167 in 13.939 seconds; module
  boundaries pass 19/19 in 2.183 seconds; and the CI, Skill, and bootstrap
  contracts pass 24/24 in 5.235 seconds. Ruff lint and formatting, project
  journal validation, and `git diff --check` are clean.
- The fresh whole-range Codex processor on signed head `1e696697` found one
  further P1: common UK domestic forms such as `020 7946 0958`,
  `(020) 7946 0958`, and `02079460958` still bypassed both enforcement points.
  That head's hosted run was cancelled and its reviewer workspace postvalidated
  clean before removal. The shared candidate policy now accepts bounded local
  formatting but requires 10 through 15 digits without a leading plus; the
  international branch retains its 7 through 15 digit bound. Dates, short
  numeric labels, and overlong numeric labels remain explicit negative cases.
  The first affected-suite run also proved that a domestic candidate could
  consume the numeric tail of a UUID; independent domestic boundaries now
  reject adjacency to identifier hyphens or underscores, preserving the raw-ID
  category. The exact corrected regressions pass 3/3 in 0.638 seconds and the
  complete affected suites pass 167/167 in 14.630 seconds. Module boundaries
  pass 19/19 in 1.867 seconds with the exact branch inventory at the unchanged
  9,475 ceiling; CI, Skill, and bootstrap contracts pass 24/24 in 5.339 seconds.
  Ruff lint/format and project-journal validation are clean.
- The fresh whole-range Codex processor on signed head `94e59f48` found two
  further P1 gaps. Durable-history graph reads did not disable repository
  commit-graph and multi-pack-index caches, and source-overlap validation did
  not treat values extracted from closed credential and personal-data labels
  as standalone sensitive tokens. The head's hosted CI and GitHub Codex
  request were cancelled and remain stale; the independent reviewer workspace
  postvalidated clean before removal.
- History authority, publisher, admission, and migration reads now consume one
  shared cache-disable argument contract, so repository-local cache settings
  cannot decide signature topology or retained publication ancestry. The
  result validator now expands source candidates with only the existing closed
  credential and personal-label taxonomies, preserves credential-redaction
  precedence, and applies the same expansion to leak scanning and deterministic
  post-redaction. Expansion is lazy and fails closed at a separate 512-item,
  1-MiB derived-candidate ceiling. Bare, quoted, prompt, and tool-output cases
  are covered while ordinary labels and safe credential statuses remain
  negative cases.
  Current-tree evidence passes the complete affected privacy/result set
  168/168, history Git cache/credential controls 2/2, authority correctness
  6/6, legacy descriptor-bound history checks 2/2, module boundaries 19/19,
  and CI, Skill, and bootstrap contracts 24/24. The exact engine branch
  inventory remains 9,475/9,475 without raising the ceiling; Ruff lint and
  formatting, the official Skill validator, project-journal validation, the
  generated bootstrap manifest check, and `git diff --check` are clean.
- Signed head `dfd83c2e` became stale when GitHub Codex rebound two unresolved
  current-range P1 findings: valid 7-9 digit domestic phone numbers could pass
  both privacy defenses, and a malformed explicit source timestamp could fall
  back to the rollout filename. Its fresh local processor was stopped without
  accepting partial output, the workspace postvalidated clean before removal,
  and the hosted run was cancelled as non-counting.
- Short domestic numbers are now recognized only under a closed phone-context
  label with bounded flexible horizontal whitespace; bare short numbers, dates,
  versions, and overlong labels remain negative cases. Credential, personal,
  and source-overlap redaction now preserve their priorities across label-only,
  separator-only, complete-source, and credential-context substitutions for
  both original prompts and tool output. A malformed present source-time field
  blocks stable locator fallback and produces `source_event_time_unavailable`;
  a genuinely missing field may still use the stable rollout filename. One
  four-shard run was stopped as non-counting after a precommit audit found the
  composition gaps; all exact shard processes were interrupted once and proved
  absent before edits. The final bounded read-only re-audit reports
  `No findings.` Focused evidence across the fix sequence passes result privacy 21/21,
  result/episode behavior 79/79, retained export 70/70, catalog 30/30, source
  transport 123/123, module boundaries 19/19 with the unchanged 9,475/9,475
  branch inventory, and CI/Skill/bootstrap contracts 24/24. Ruff lint and
  formatting are clean. The final frozen code-and-test tree passes all 1,747
  tests: shard 0 passes 418/418 in 1,576.025 seconds, shard 1 passes 470/470 in
  1,253.496 seconds, shard 2 passes 459/459 in 1,361.142 seconds, and shard 3
  passes 400/400 in 1,271.926 seconds.
- Signed head `6d5013a8` became stale when current-head GitHub Codex found that
  three-character values from closed sensitive labels were not retained as
  standalone source-overlap tokens. An explicitly authorized same-head review
  then found that the short-phone context omitted `Phone number` and
  `Telephone number`, while the personal-label taxonomy omitted closed address
  qualifiers such as customer, home, mailing, postal, residential, and
  shipping. The local Codex processor was stopped without accepting output;
  its independent workspace postvalidated clean, the trusted bundle digests
  remained unchanged, and the exact task root was removed.
- Source-overlap expansion now records provenance for normalized
  three-character values extracted from a sensitive label and applies the
  same Unicode token boundaries to leak scanning and deterministic
  post-redaction. Normalization maps every case-folded character back to its
  exact original source span, so expansions such as `\u00df` to `ss` redact
  the correct bytes without making `Bob` match `Bobby`. A bounded 96-character
  overlap preserves the complete closed label context across source windows.
  Short phone values are extracted only under the closed context and only with
  7 through 15 digits; dates, five-digit values, overlong numbers, and
  unlabeled three-character text remain negative cases.
- Precommit audits found and closed four composition gaps: source-window label
  splits, case folding after the minimum-length decision, missing short-token
  boundaries, and scan/redaction Unicode-semantic drift. A separate
  phone/address audit found that contextual phone evidence was lost once only
  its value reached agent output; the source index now retains that extracted
  value. Its exact re-audit reports `No findings.` One broader mapping audit
  ended transport-inconclusive and supplied no accepted finding or clean
  evidence. Three four-shard attempts were stopped as non-counting when newer
  findings invalidated their frozen trees; every exact runner was allowed to
  terminate or was interrupted once, and no stale test or reviewer process
  remained before edits resumed.
- Current-tree affected evidence passes result/episode behavior 80/80,
  result-contract audit 21/21, retained export/reporting 70/70, and orchestrator
  source-overlap behavior 7/7. Module boundaries pass 19/19 with the exact
  branch inventory reduced from 9,475 to 9,468 without raising its 9,475
  ceiling; CI, Skill, and bootstrap contracts pass 24/24. Ruff 0.13.2 lint and
  formatting, the official OpenAI Skill validator, the generated bootstrap
  manifest check, and `git diff --check` are clean.
- The final frozen code-and-test tree executes all 1,748 Python 3.13 tests
  exactly once across four deterministic shards: shard 0 passes 419/419 in
  1,576.422 seconds, shard 1 passes 470/470 in 1,249.070 seconds, shard 2 passes
  459/459 in 1,356.344 seconds, and shard 3 passes 400/400 in 1,268.206 seconds.
- Signed head `05419453` became stale when current-head GitHub Codex found three
  remaining retained-privacy gaps: personal-name labels omitted `full`, `first`,
  and `last` modifiers; the shared credential taxonomy omitted `passphrase`,
  `passcode`, and `PIN`; and reviewed prose did not reject explicit terminal,
  console, or shell output labels. Its local Codex processor was stopped without
  accepting partial output, the independent workspace postvalidated clean, and
  the exact task root was removed before implementation resumed.
- Personal labels now accept the closed spaced, underscored, hyphenated, and
  camel-case forms for account, customer, employee, person, and user names.
  Credential labels accept passphrases and passcodes, exact uppercase `PIN`, and
  prefixed camel-case `Passphrase`, `Passcode`, and `Pin` suffixes. Lowercase
  dependency or hardware uses such as `pin=GPIO17`, `--pin requests==2.32.5`,
  and `The pin is bent.` remain explicit negative cases. Retained reviewed prose
  rejects terminal, console, and shell output only when the phrase is used as an
  explicit `:` or `=` label, preserving ordinary summaries about output quality
  or formatting. Scanner/redactor, source-overlap, retained assembly, retained
  reread, and report validation share the closed implementation.
- A bounded precommit audit first found four camel-case and false-positive gaps;
  the corrected re-audit reports `No findings.` The affected result/episode,
  result-contract audit, and retained export/reporting suites pass 171/171.
  Module boundaries pass 19/19; CI, Skill, and bootstrap contracts pass 24/24;
  Ruff lint and formatting plus `git diff --check` are clean.
- Several early full-shard invocations are non-counting because they selected
  the physical Homebrew Framework Python below the other-user-writable
  `/opt/homebrew` ancestor. A single isolated failing history test exposed the
  exact `ExecutableAuthorityError`; no production change was made. Re-running
  through the repository's owner-controlled Python 3.13.12 copy created by
  `venv --copies` restored the executable-authority contract. The final frozen
  tree passes all 1,748 tests: shard 0 passes 419/419 in 1,633.108 seconds,
  shard 1 passes 470/470 in 1,300.820 seconds, shard 2 passes 459/459 in
  1,410.850 seconds, and shard 3 passes 400/400 in 1,322.127 seconds.
- Signed head `a3b3651d` became stale when current-head GitHub Codex found two
  remaining retained-privacy gaps: bare `Full name`, `First name`, and
  `Last name` labels without a subject prefix could pass both privacy defenses,
  and split `pass phrase` and `pass code` labels were absent from the shared
  credential taxonomy. The old hosted run was cancelled. One local processor
  attempt failed before review because its supplied Git prefix omitted required
  isolation metadata; a corrected attempt was stopped without accepting partial
  output after the GitHub findings invalidated the head. Both independent task
  roots postvalidated clean before removal.
- Bare personal-name labels now use a separate closed pattern with line-start,
  Markdown-marker, punctuation, and quoted structured boundaries, including
  escaped double- and single-quoted values. Split passphrase and passcode forms
  accept only horizontal space, hyphen, or underscore separators, so labels
  cannot join across lines. Scanner/redactor, source-overlap extraction,
  retained validation, and report validation share the implementation.
- Bounded precommit audits found and closed four composition gaps: ordinary
  whitespace false positives, cross-line credential matching, weak redaction
  assertions, and incomplete source-overlap coverage. Follow-up audits then
  closed structured-prefix, quoted-value, and escaped-quote truncation gaps;
  the final exact re-audit reports `No findings.` One earlier four-shard run was
  stopped as non-counting when those audits invalidated its tree. Its exact
  processes were interrupted once, proved absent, and the bounded temporary
  residue was removed before the final run.
- Final current-tree evidence passes the complete affected suites 172/172,
  module boundaries 19/19 with the exact branch inventory restored to the
  historical 9,475 ceiling, and CI, Skill, and bootstrap contracts 24/24.
  Ruff 0.13.2 lint and formatting, the official OpenAI Skill validator, the
  generated bootstrap manifest check, and `git diff --check` are clean. The
  final frozen Python 3.13 tree passes all 1,749 tests: shard 0 passes 419/419
  in 1,649.349 seconds, shard 1 passes 471/471 in 1,321.413 seconds, shard 2
  passes 459/459 in 1,429.073 seconds, and shard 3 passes 400/400 in 1,332.867
  seconds.
- Signed checkpoint `5c57a90c` became stale when its fresh whole-range Codex
  processor found three release blockers: the shared personal-data taxonomy
  omitted client, tenant, and organization names plus possessive name labels
  and common government/payment/account identifiers; shadow mode bypassed the
  fixed installed coordinator Python; and oversized rejected-result identity
  sampled only the first and last 64 KiB of a payload.
- The shared scanner/redactor, source-overlap extraction, retained validator,
  and report validator now use one closed expanded personal-data taxonomy,
  including quoted structured values. Shadow and production `doctor`/`start`
  both authenticate the fixed installed Python. Rejected payloads up to 1 MiB
  use the complete verified SHA-256 and the replayable v2 action; larger
  payloads use an explicit content-free v3 observation with
  `result_digest_exact: false` and cannot replay as an identity match.
- The exact reviewer-fix regressions pass 8/8. Complete affected modules pass
  102/102, 116/116, and 212/212; Darwin security contracts pass 10/10; CI and
  Skill contracts pass 17/17. The engine branch inventory decreases from 9,475
  to the new exact 9,472 ceiling. Ruff 0.13.2 lint and changed-file formatting,
  the generated bootstrap manifest, official Skill validator, project-journal
  validator, and `git diff --check` are clean. The final Python 3.13 tree passes
  all 1,752 tests exactly once: shard 0 passes 421/421 in 1,710.706 seconds,
  shard 1 passes 471/471 in 1,366.345 seconds, shard 2 passes 460/460 in
  1,485.831 seconds, and shard 3 passes 400/400 in 1,391.701 seconds.
- Signed head `77f37b13` became stale when its fresh whole-range Codex processor
  found three release blockers: the personal-data grammar omitted date of birth,
  possessive address, and Markdown label forms; oversized result classification
  closed and reopened the result between classification and hashing; and each CI
  shard independently discovered its own test inventory without a shared proof
  that every source and test ID was represented.
- The shared privacy grammar now recognizes closed DOB/date-of-birth, possessive
  address, and paired Markdown label forms across scanner/redactor,
  source-overlap, retained validation, and report validation. Canonical
  placeholders from the exact known set remain accepted only when no additional
  value follows. JSON-escaped quoted values, unquoted narrative prefixes, and
  trailing ASCII or Unicode data after a placeholder are independently decoded
  and extracted for source-overlap checks. Punctuation, quote, backtick,
  Markdown, escaped quote, structural, and smart-quote wrappers normalize to the
  same value without making ordinary address-book, status, policy, or
  pure-placeholder prose sensitive. The prior redacted-prefix lookahead was
  removed rather than retained as an unbounded backtracking path.
- Agent-result classification now binds one owner-only no-follow descriptor.
  Payload-sized and digest-sized files are read twice and compared on that
  descriptor while identity, size, stat access policy, and descriptor ACL policy
  are revalidated against the bound name. Files above the digest ceiling are not
  content-read and receive an explicit nonexact, nonreplayable observation after
  the same structural revalidation. Close failures preserve a prior safety error
  as primary evidence and fail independently only after an otherwise successful
  observation. The exact engine branch inventory is 9,473 under the unchanged
  historical ceiling of 9,475.
- CI now generates one bounded canonical manifest containing the complete sorted
  test-ID inventory and an independent `tests/**/test_*.py` path/module/SHA-256
  content inventory, transports it to every shard, and requires exact equality
  before selection. A closed loader enumerates real module and class
  dictionaries, rejects `load_tests`, module `__getattr__`/`__dir__`, custom
  module types, custom test metaclasses, wrapped async/generator methods,
  `runTest` fallback, and imported external test cases, and never delegates
  discovery to those hooks. Runtime instrumentation rejects non-`None` method
  results in ordinary shards and the separate Darwin security runner. One
  captured `(test_id, test)` ordering governs both verification and sharding;
  skipped, expected-failure, unexpected-success, partial, missing-source,
  changed-source, or replaced-ID execution cannot pass. The documented local
  loop clears stale manifests, fails immediately before shard execution, and
  still aggregates every shard result once execution begins.
- Final precommit privacy audits additionally closed embedded noncanonical
  placeholders, no-separator ASCII and CJK personal-value suffixes, eager
  overlap-source expansion, and a retained-validator parity gap. The agent
  result scanner and retained artifact assembly/reread validator now consume the
  same closed placeholder vocabulary. Final test-inventory audits closed
  wrapper-chain, `runTest`, non-`None` result, and Darwin-runner bypasses without
  broadening accepted test semantics.
- The final canonical Python 3.13 inventory contains 1,782 test IDs and 22
  authenticated source modules under manifest digest
  `78d630e684d7eafa44f10b8cea7db732d71844b7f4cd10e4eb7ae1c9d1856e80`.
  On the frozen implementation tree, shard 0 passes 426/426 in 1,949.531
  seconds, shard 1 passes 481/481 in 1,200.589 seconds, shard 2 passes 467/467
  in 1,695.955 seconds, and shard 3 passes 408/408 in 1,606.716 seconds. The
  separate Darwin security runner passes 10/10 in 99.030 seconds; affected
  module groups pass 134/134 and 176/176; final privacy and test-inventory
  precommit audits both report `No findings.`
- One earlier parallel execution of the same final manifest reported an
  isolated `INVALID_INPUT` instead of the expected interrupted-export
  `INVALID_STATE` in
  `test_export_retry_rejects_a_different_destination_before_staging`. It is
  retained as non-counting transient evidence rather than silently treated as
  success. The exact test passed in isolation, its eight-test adjacent order
  passed, the complete 481-test shard order passed, and 12 additional fresh
  random-fixture executions all returned the exact expected
  `invalid_state/run_transition_invalid` machine result. No production or test
  expectation was weakened.
- Signed head `5cbe2a6e` became stale when current-head GitHub Codex found three
  retained-privacy blockers: a field-boundary bare `Address` value, an
  unlabeled standard SSN, and an unlabeled payment-card number could bypass the
  shared personal-data locator. The in-flight local Codex processor was
  interrupted without accepting partial output, its independent workspace
  postvalidated clean, and its exact task root was removed. The obsolete hosted
  run was cancelled before further testing.
- The shared scanner, post-redactor, source-overlap index, retained assembly,
  retained reread, and report validator now recognize field-boundary physical
  addresses, bounded standard SSNs, and 13-19 digit Luhn-valid payment-card
  numbers. Address handling preserves ordinary postal commas and known
  `City`, `Postal Code`, `Apt`, and `Unit` continuations, stops before unrelated
  `, field:` boundaries, extracts complete and component overlap values, and
  excludes single or multi-component `0x` memory addresses. Explicit phone
  fields cover quoted, Markdown, JSON, camel-case, `no`, and compound contact
  aliases while unlabeled phone candidates remain independently bounded.
- The bounded precommit privacy audit found and closed comma truncation,
  memory-address false positives, phone/card substring overlap, missing
  left/right boundaries, explicit phone aliases, address continuation fields,
  quoted component normalization, and one- or two-character apartment/unit
  overlap. The final closure-only re-audit reports `No findings.` The final
  affected Python 3.13 modules pass 23/23, 83/83, 71/71, and 19/19; the exact
  engine branch inventory is 9,473 under the unchanged 9,475 ceiling.
- The final canonical Python 3.13 inventory contains 1,783 test IDs from 22
  authenticated source modules under manifest digest
  `cf72ad014462d540a3788d1de50ab00bb7f502ed1299ab7e519b7a913f4a1444`.
  Two shard tasks accidentally started against the pre-final manifest were
  cancelled once and are explicitly non-counting. The sequential final run
  passes every current-tree test exactly once: shard 0 passes 426/426 in
  1,577.065 seconds (task `01a0189c-11b8-78d1-ab62-a51038a5904c`), shard 1
  passes 481/481 in 1,225.093 seconds (task
  `01a018b6-0b70-7703-96fc-6f6816ceb719`), shard 2 passes 467/467 in
  1,344.018 seconds (task `01a018ca-f7ec-7763-9403-fa4bf837f005`), and shard
  3 passes 409/409 in 1,224.751 seconds (task
  `01a018e0-08f3-7f72-b36f-6b830fa22f39`). Every task exits zero with an
  explicit `OK` terminal summary. The independent Darwin security inventory
  passes 10/10 in 65.332 seconds.
- Signed head `d547cd53` became stale after the fresh local Codex processor found
  that narrative field assignments such as `customer's name is ...` bypassed
  the shared privacy locator and that one filesystem-flags test could skip in
  an ordinary shard. Current-head GitHub Codex independently found that valid
  unlabeled compact IBANs also bypassed the scanner, redactor, and retained
  validator. The replacement implementation adds closed `is`, `was`, and
  `set to` narrative connectors, compact and canonically grouped IBAN matching
  with mod-97 validation, and shared coverage across scanning, overlap
  extraction, post-redaction, retained assembly, and retained reread.
- The flags case is now an explicit Darwin security test. The canonical Darwin
  inventory contains 11 exact IDs, and the CI contract rejects ordinary
  `self.skipTest` calls or platform decorators outside that marked inventory.
  Two older chmod-dependent v1 assertions now fail closed instead of silently
  skipping. The final Darwin run passes 11/11 in 66.290 seconds; privacy and
  retained-result modules pass 23/23, 83/83, and 71/71; CI contracts pass
  33/33; module boundaries pass 19/19 with an exact branch inventory of 9,475;
  and the public skill contract passes 5/5.
- The final Python 3.13 test inventory remains 1,783 exact IDs from 22 source
  modules under manifest digest
  `b51cd66848c5172fe4487b003582aca5337055936bd222b4f60e88b953152119`.
  Source-only shard 0 passes 426/426 in 1,759.406 seconds (task
  `01a0194d-8506-7013-8e51-de8e9c0a7c1c`), shard 1 passes 481/481 in
  1,371.744 seconds (task `01a0194b-bbb3-7a31-a051-bd4078d4bcd6`), shard 2
  passes 467/467 in 1,475.423 seconds (task
  `01a0194b-cbce-7112-9699-aa78d6092b01`), and shard 3 passes 409/409 in
  1,657.454 seconds (task `01a0192c-b166-74e0-b211-3a9eb63cc1f1`). Every
  counted shard exits zero with a complete, untruncated `OK` summary.
- The first final-manifest shard 0-2 executions are retained as non-counting
  environment evidence: ignored bytecode caches created by earlier focused
  commands predated those tasks, so the source-authority and bootstrap tests
  correctly rejected import substitutes. The exact caches were removed, the
  source-only invariant remained stable, and the three complete shard reruns
  above passed without expectation changes. Four still-earlier pre-final
  tasks (`01a01916-0e3d-7d91-9b4c-247d37d8c9c8`,
  `01a01916-0e3d-7d91-9b4c-24890d21a939`,
  `01a01915-fc1a-7710-9fb6-233eaa89e89e`, and
  `01a01916-0629-7f71-a36b-3cb84b16f9b1`) were cancelled once the IBAN
  blocker made their tree stale. The Darwin/skip precommit audit reports
  `No findings.`; two bounded privacy-audit transports ended inconclusive, and
  no partial output from either was accepted as review evidence.
- Signed head `de95998a` became stale when its fresh whole-range Codex processor
  found three retained-privacy blockers: closed credential-field matching did
  not cover PascalCase forms, bare `Full`/`First`/`Last name` and `Address`
  narratives could bypass field detection, and grouped IBAN recognition was
  uppercase-only. The independent workspace postvalidated clean and was safely
  removed after the terminal findings were recorded.
- The shared scanner, redactor, source-overlap index, retained assembly, retained
  reread, and report validator now use one closed PascalCase credential taxonomy;
  bounded narrative value derivation; bare name/address assignment and narrative
  forms; and compact or canonically grouped, case-insensitive, country-length and
  mod-97-valid IBAN recognition. The country-length table was independently
  compared with all 89 records in the official SWIFT IBAN Registry Release 102
  (June 2026), rather than inferred from examples.
- Two bounded precommit privacy audits closed status-plus-value, punctuation,
  wrapper, comma-separated name, Markdown, malformed-Markdown, metadata, and
  source-overlap edge cases. Complete and malformed Markdown preserve distinct
  span semantics; unbalanced tails participate in sensitivity decisions; pure
  `required`/`missing`/`unavailable` status metadata remains nonsensitive; and
  single- or double-marker emphasis cannot hide a labeled value. The final
  closure-only audit reports `No findings.` Focused Python 3.13 contracts pass
  24/24, 83/83, 71/71, 19/19, 33/33, and 5/5; the exact engine branch inventory
  is 9,488.
- Exact-secret admission on signed heads `edcc5f03` and `3437dcb4` was
  inconclusive. Replacing newly added non-catalog credential-shaped values with
  role-specific synthetic-token catalog values removed the raw fixture
  ambiguity but did not complete admission. A read-only stage diagnostic then
  localized the remaining `generic-secret-assignment` opaque container to the
  new PascalCase audit fixture: dynamic f-strings could not supply stable raw
  assignment bytes, and one safe `missing` control could not prove its nested
  source-string boundary. The sensitive fixtures now use literal catalog values,
  while the safe control splits its field and status source fragments. Runtime
  test values are unchanged and production logic was not modified.
- The preceding complete runs under manifest digests
  `baf89b8dfba1e2924bb8d59bf1b344cc2d28e4de8fb9caaa68890f8aa530bc6c`
  and `f6832853b38ee92e817198cd3b93a1a95cf365914f9e0197d35d007084745c15`
  remain prior-tree evidence.
- The final canonical Python 3.13 inventory contains 1,784 exact test IDs from
  22 authenticated source modules under manifest digest
  `ec3779702e260c06a80680379cd4183955698bda184df6de52bb7e30a9970035`.
  Shard 0 passes 427/427 in 1,680.973 seconds, shard 1 passes 481/481 in
  1,303.504 seconds, shard 2 passes 467/467 in 1,397.660 seconds, and shard 3
  passes 409/409 in 1,332.653 seconds. Every bounded wrapper exits zero with an
  explicit `OK` summary. Four earlier pre-closure shard tasks were cancelled and
  remain non-counting. A mistaken Darwin `--help` probe ran tests without a
  pollable terminal receipt and is also non-counting; the formal bounded Darwin
  gate separately passes 11/11 in 77.519 seconds with exit zero.
- Signed head `54b4dca3` became stale when current-head GitHub Codex found three
  release blockers: middle-name labels were absent from the shared personal-data
  taxonomy, publication Git calls inherited repository FSMonitor hooks, and an
  attacker-controlled `gpg.conf` could redirect GnuPG writes before publication
  or verification. The shared scanner, redactor, source-overlap index, retained
  assembly, retained reread, and report validator now recognize closed
  middle-name field forms. Every publication Git topology call forces
  `core.fsmonitor=false`. GnuPG listing, canary, signing, and verification now
  use a fixed source-authenticated launcher that inserts `--no-options`, while
  binding and revalidating both the launcher and selected real GnuPG executable.
- The new adversarial regressions prove a malicious repository FSMonitor cannot
  execute, malicious GnuPG configuration cannot create its redirected marker,
  repository-local GPG program overrides cannot replace the bound launcher, and
  middle-name values are rejected across scan, overlap, redaction, retained, and
  report layers while ordinary status prose remains safe. One exact five-test
  publication run ended without a recoverable terminal receipt after its parent
  response stream disconnected and is non-counting; the same pollable argv then
  passed 5/5 in 279.504 seconds. Focused module/skill/publication contracts pass
  63/63, CI contracts pass 33/33, and the generated bootstrap manifest,
  `actionlint`, Ruff 0.13.2 lint/format, shell syntax and ShellCheck, the official
  OpenAI Skill validator, project-journal validation, and `git diff --check`
  pass. Validation used an owner-only copied Python 3.13.12 runtime because the
  ambient Homebrew Cellar ancestor was group-writable and therefore correctly
  rejected by executable-authority checks.
- The final current-tree Python 3.13 inventory contains 1,787 exact test IDs
  from 22 authenticated source modules under manifest digest
  `438fff1a0e4adaec52138122f0a7369e35b461af3fedbf6c0cbad672f62719cb`.
  The sequential closed run passes every test exactly once: shard 0 passes
  427/427 in 1,606.764 seconds, shard 1 passes 484/484 in 1,375.495 seconds,
  shard 2 passes 467/467 in 1,330.983 seconds, and shard 3 passes 409/409 in
  1,281.917 seconds. Every shard exits zero with an explicit `OK` terminal
  summary. The independent Darwin security inventory passes 11/11 in 75.705
  seconds.
- Signed head `b65cea58` became stale when its fresh whole-range Codex processor
  found that invisible control and Unicode default-ignorable characters could
  be inserted into model prose to evade source-overlap matching and could then
  survive into retained prose. The reviewer workspace was independently
  materialized and validated from trusted private release `f9e596f4`; its
  manifest, skill, and guard digests remained unchanged after review, the
  workspace postvalidated clean, and its task root was safely removed.
- The shared privacy owner now defines a closed C0, DEL/C1, and Unicode
  default-ignorable policy. Model-result keys reject every listed character;
  string values canonicalize whitespace controls before redaction and reject
  all remaining hidden characters. Source-overlap comparison applies the same
  whitespace canonicalization and removes the remaining hidden characters on
  both source and result sides, while retained safe strings, reviewed prose,
  bundle assembly, and bundle reread validation fail closed if any such
  character remains. The data and architecture contracts document the same
  boundary.
- The first 181-test affected-module run is non-counting: rejecting all control
  characters before redaction broke canonical multiline model output and ended
  with 12 errors and 2 failures. The corrected design normalizes whitespace
  controls before redaction while rejecting non-whitespace controls and
  default-ignorables. Exact old/new regressions then pass 9/9 in 21.096 seconds;
  affected result, export, and audit modules pass 181/181 in 81.902 seconds;
  module boundaries pass 19/19 in 1.866 seconds with an exact branch inventory
  of 9,498 under the unchanged 9,500 ceiling; CI contracts pass 33/33; and the
  public skill contract passes 5/5.
- The final Python 3.13 inventory contains 1,790 exact test IDs from 22
  authenticated source modules under manifest digest
  `2a958ce89869327bd60b6a7ca44730f13f11153a2afa6abf1639977c7f25cec7`.
  Shard 0 passes 428/428 in 1,719.827 seconds, shard 1 passes 484/484 in
  1,481.349 seconds, shard 2 passes 468/468 in 1,454.321 seconds, and shard 3
  passes 410/410 in 1,376.131 seconds. Every shard exits zero with an explicit
  `OK` terminal summary, for exact aggregate coverage of 1,790/1,790. The
  independent Darwin security inventory passes 11/11 in 68.430 seconds.
- The generated bootstrap manifest, Ruff 0.13.2 lint and changed-file format
  checks, both real workflows under `actionlint`, shell syntax and ShellCheck,
  the isolated official OpenAI Skill validator, and `git diff --check` pass.
  One actionlint invocation named a nonexistent workflow and one validator
  invocation used a local environment without PyYAML; both are recorded as
  non-counting command errors, and neither is substituted for the successful
  authoritative rerun.
- Signed head `dfa49fc5` became stale when its fresh whole-range Codex processor
  found that four bounded subprocess owners treated stdout/stderr EOF as process
  exit. A child could close both output streams, continue a required side
  effect, and be killed before that side effect completed. The affected owners
  were publication Git/GPG commands, retained-history authority commands, the
  publisher canary, and remote-host-context relay. The reviewer workspace was
  independently materialized and validated, postvalidated clean after the
  terminal finding, and safely removed.
- The four owners now share one unreaped-leader lifecycle contract. After output
  EOF they wait for terminal leader state under the original deadline while the
  unreaped PID still fences PID/PGID reuse; only then do they terminate the
  task-owned process group and reap the leader. The group-signal capability is
  retired before reaping, so exception cleanup cannot signal or probe a reused
  group identifier. Deterministic regressions cover post-EOF side effects,
  deadline expiry, descendant cleanup, and interruption after reap. Canary
  contracts pass 11/11 in 8.708 seconds, exact publication/authority regressions
  pass 2/2, exact remote regressions pass 3/3, the complete source-transport
  module passes 126/126 in 41.487 seconds, and module boundaries pass 19/19 with
  an exact branch inventory of 9,491 under the 9,500 ceiling.
- One earlier four-shard run and one sequential publication-module run were
  intentionally interrupted after later lifecycle audits changed or superseded
  their covered tree; both are non-counting. Focused invocations that bypassed
  the isolated repository runner, plus one prior response-stream-disconnected
  canary run without a recoverable terminal summary, are also non-counting and
  are not substituted for the successful isolated reruns above.
- The final Python 3.13 inventory contains 1,798 exact test IDs from 22
  authenticated source modules under manifest digest
  `41f15e21f70ae9f83db186d23f8ecac5f3505baed50deec2ae22948c75fdf824`.
  Shard 0 passes 430/430 in 1,650.747 seconds, shard 1 passes 485/485 in
  1,409.432 seconds, shard 2 passes 472/472 in 1,382.241 seconds, and shard 3
  passes 411/411 in 1,304.038 seconds. Every official shard exits zero with an
  explicit `OK` terminal summary, for exact aggregate coverage of 1,798/1,798.
  The independent Darwin security inventory passes 11/11 in 66.878 seconds.
  CI and public-skill contracts pass 38/38; the generated bootstrap manifest,
  Ruff lint and changed-file format checks, both workflows under `actionlint`,
  the isolated official OpenAI Skill validator, project-journal validation,
  and `git diff --check` pass.
- Signed head `e4029bf6` became stale when its fresh whole-range Codex processor
  found three remaining access-policy and cleanup gaps: source candidate and
  scan proofs omitted Darwin ACL policy, writable ACLs on otherwise admitted
  data-path ancestors could redirect creation, and the remote relay swallowed
  every process-group signal failure. The reviewer workspace was materialized
  and postvalidated at the exact 62-commit, 61-parent-edge range with graph
  digest `6598888e48a8cffc280b9679190bbd6b12cd61e29df97a130eb64a35dc067d93`
  and config digest
  `07990c1d83a78ea34a87e3f51883e3164c3098b21770082207e00a3a898ab24f`;
  the trusted release manifest, Skill, and guard digests remained unchanged,
  and the task root was safely removed.
- Source candidate schema v5 and every scan proof sample now bind the normalized
  descriptor ACL digest in addition to identity and selected BSD flags.
  Existing data-path ancestors are checked and revalidated through held
  descriptors: read-only and inheritance-only ACEs remain valid, while any
  allow ACE granting mutation authority fails closed. Remote cleanup preserves
  the unreaped leader fence, surfaces every non-`ESRCH` signal failure, and
  accepts Darwin's zombie-only `EPERM` case only after reap plus a non-signaling
  group-absence proof; a surviving or unverifiable group remains an explicit
  closure failure.
- The exact source-transport module passes 128/128 in 42.995 seconds, identity
  and safe-I/O tests pass 51/51, six exact remote lifecycle regressions pass
  6/6, module boundaries pass 19/19, CI contracts pass 33/33, and the public
  Skill contract passes 5/5. The independent Darwin security inventory expands
  to 14 exact tests and passes 14/14 in 78.501 seconds. One initial full-shard
  launch had unrecoverable terminal output after a task-context transition and
  is non-counting. Its replacement exposed the stale CI expectation of 11
  Darwin tests; that four-shard tree was intentionally interrupted and is also
  non-counting. The corrected closed inventory expectation is 14. Two optional
  read-only precommit explorer audits produced no terminal artifact within
  their bounded window and were shut down; no partial output was accepted and
  neither audit counts as review evidence.
- The final Python 3.13 inventory contains 1,802 exact test IDs from 22
  authenticated source modules under manifest digest
  `8677372f2c4d20c9e704d1960683f24b3793360f66a08babe3a352a37904f7af`.
  Shard 0 passes 430/430 in 1,679.632 seconds, shard 1 passes 485/485 in
  1,441.753 seconds, shard 2 passes 474/474 in 1,409.367 seconds, and shard 3
  passes 413/413 in 1,332.657 seconds. Every shard exits zero with an explicit
  `OK` terminal summary, for exact aggregate coverage of 1,802/1,802. Ruff
  0.13.2 lint and changed-file formatting, both workflows under `actionlint`,
  the generated bootstrap manifest, the isolated official OpenAI Skill
  validator, project-journal validation, source-tree bytecode exclusion, and
  `git diff --check` pass on the same implementation tree.
- Signed head `a795c781` became stale when its fresh whole-range Codex processor
  found that publication and retained-history subprocess owners swallowed
  process-group signal and reap failures. That could report a successful
  operation while task-owned descendants remained alive. The exact 63-commit,
  62-parent-edge reviewer workspace used graph digest
  `b7eebd56861d0430b5406be1eb14540c26258b2215ee46b40f3f31df310bcda7`
  and config digest
  `07990c1d83a78ea34a87e3f51883e3164c3098b21770082207e00a3a898ab24f`;
  it postvalidated clean, retained unchanged trusted-bundle digests, and was
  safely removed after the terminal finding.
- Remote relay, publication, and retained-history commands now use the same
  strict process-group closure owner. Only `ESRCH` proves ordinary absence;
  every other signal or reap failure is explicit. On Darwin, a zombie-only
  `EPERM` result is accepted only after the leader is reaped and a
  non-signaling group-absence probe succeeds. Signal authority retires before
  any potentially reaping operation, so cleanup cannot target a reused PGID.
  Four exact closure regressions pass 4/4 in 0.201 seconds, the complete source
  transport module passes 128/128 in 42.760 seconds, module boundaries pass
  19/19, and the Darwin security inventory passes 14/14 in 78.609 seconds.
  Direct non-isolated unittest invocations and one intentionally stopped
  publication-only probe are non-counting invocation-shape diagnostics.
- The superseding Python 3.13 inventory contains 1,804 exact test IDs from 22
  authenticated source modules under manifest digest
  `5923d8ba54aa14b32ff1de980f1c9ac1f0350e8de5dbc1de5e219cdd73c3cdf6`.
  Shard 0 passes 431/431 in 1,709.522 seconds, shard 1 passes 486/486 in
  1,474.314 seconds, shard 2 passes 474/474 in 1,446.785 seconds, and shard 3
  passes 413/413 in 1,367.375 seconds. Every shard exits zero with an explicit
  `OK` terminal summary. CI contracts pass 33/33 and the public Skill contract
  passes 5/5; Ruff 0.13.2 lint and formatting, both workflows under
  `actionlint`, the generated bootstrap manifest, the official OpenAI Skill
  validator, and `git diff --check` pass on the same implementation tree.
- Signed head `17460d36` became stale when its fresh whole-range Codex processor
  found two remaining process-closure reporting gaps. The publisher canary
  treated terminal-leader `EPERM` as sufficient without proving that the
  process group was absent, and an active primary error could hide a later
  process-group cleanup failure because the machine-facing CLI ignored
  exception notes. The exact 64-commit, 63-parent-edge reviewer workspace used
  graph digest
  `bd52b75567da9feb598b488078b1dce05335ebfbf7a75df4769558df20787adc`
  and config digest
  `07990c1d83a78ea34a87e3f51883e3164c3098b21770082207e00a3a898ab24f`;
  it postvalidated clean, retained unchanged trusted-bundle digests, and was
  safely removed after the terminal findings.
- The canary now delegates to the shared strict process-group closure owner.
  A terminal-leader `EPERM` retires signal authority and reaps the leader, but
  succeeds only when a subsequent non-signaling group probe proves `ESRCH`.
  Persistent cleanup failure marks the exception chain with bounded structured
  evidence. The CLI scans at most 16 cause/context links and emits the closed
  `process_group_cleanup_incomplete` security result without exposing raw
  exception details. Exact new regressions pass 3/3, the canary module passes
  12/12 in 7.975 seconds, focused publication lifecycle tests pass 4/4 in
  0.227 seconds, the CLI module passes 66/66 in 200.730 seconds, source
  transport passes 128/128 in 41.387 seconds, module boundaries pass 19/19,
  CI contracts pass 33/33, and the Darwin security inventory passes 14/14 in
  83.524 seconds.
- The final Python 3.13 inventory contains 1,807 exact test IDs from 22
  authenticated source modules under manifest digest
  `699e55f6ab69eb097fb41cc5fe328abf93cd5f37089d675e9a32f37a6d735e00`.
  Shard 0 passes 431/431 in 1,733.618 seconds, shard 1 passes 488/488 in
  1,492.735 seconds, shard 2 passes 475/475 in 1,469.669 seconds, and shard 3
  passes 413/413 in 1,370.200 seconds. Every shard exits zero with an explicit
  `OK` terminal summary, for exact aggregate coverage of 1,807/1,807. One
  direct focused invocation used a non-isolated module-loading shape and is
  non-counting; the isolated exact rerun supplied the counting evidence above.
  Ruff 0.13.2 lint and changed-file formatting, both workflows under
  `actionlint`, the generated bootstrap manifest, the isolated official OpenAI
  Skill validator, project-journal validation, source-tree bytecode exclusion,
  and `git diff --check` pass on the same implementation tree. One preceding
  `actionlint` invocation named a nonexistent stale workflow path and is
  non-counting; the exact current workflow invocation supplied the passing
  evidence.
- Signed head `c659738d` became stale when its fresh whole-range Codex
  processor found four remaining trust-boundary gaps. A successful `SIGKILL`
  path reaped only the leader without proving process-group absence; readiness,
  canary, and remote-gap fallbacks could downgrade a marked cleanup failure;
  selector construction or teardown after `Popen` could bypass process cleanup;
  and bounded single-label `account@host` identifiers could enter retained
  history. The first reviewer launch stopped before any Git read because its
  prompt omitted the complete sanitized Git prefix. That metadata-only attempt
  postvalidated clean and was safely removed. Its one permitted fresh retry
  used the exact 65-commit, 64-parent-edge range, returned the four findings,
  postvalidated clean, retained unchanged trusted-bundle digests, and was also
  safely removed.
- The shared process owner now retains one cleanup deadline across signal,
  leader reap, and non-signaling group-absence polling. `EPERM` after reap is
  never accepted as absence; only a later `ESRCH` proves closure. Every direct
  or secondary process-cleanup failure receives bounded structured evidence,
  and cleanup-only wrappers preserve the outer command primary classification.
  Resource owners construct selectors inside the process-owned boundary,
  attempt every selector/stream close, and always finish group cleanup.
  Readiness, canary, and remote availability fallbacks rethrow unproven cleanup
  as a dedicated security failure. Working-zone and retained privacy validation
  now classify RFC-shaped and bounded single-label `account@host` values as
  personal identifiers while preserving complete SCP-style locator precedence.
- The superseding Python 3.13 inventory contains 1,818 exact test IDs from 22
  authenticated source modules under manifest digest
  `355d7e1df66a099a868f197be6facfb9d9ef6aa59084667ea2c854f2ed53df09`.
  Shard 0 passes 433/433 in 1,633.951 seconds, shard 1 passes 492/492 in
  1,401.182 seconds, shard 2 passes 479/479 in 1,376.005 seconds, and shard 3
  passes 414/414 in 1,296.878 seconds. Every shard exits zero with an explicit
  `OK` terminal summary, for exact aggregate coverage of 1,818/1,818. One
  redundant affected-class run was intentionally interrupted before completion
  and is non-counting; the canonical four-shard inventory supersedes it.
  Darwin security contracts pass 14/14 in 66.297 seconds, CI contracts pass
  33/33, and public Skill contracts pass 5/5. Ruff 0.13.2 lint and changed-file
  formatting, both workflows under `actionlint`, the generated bootstrap
  manifest, the official OpenAI Skill validator, project-journal validation,
  source-tree bytecode exclusion, and `git diff --check` pass on the same tree.
  A repository-wide formatter diagnostic still identifies six unchanged
  inherited migration files; it is non-counting and did not trigger unrelated
  mechanical rewrites.
- Signed head `c73c7887` became stale when its fresh whole-range Codex
  processor found four release-control gaps. The installed production
  automation prompt stopped after an incomplete `start` command; the startup
  receipt omitted the executed entrypoint bytes; process cleanup treated signal
  retirement as proof of process-group absence; and retained-history Git
  admission did not reject pack-level `objects/pack/*.promisor` markers. The
  exact reviewer workspace was independently materialized from trusted release
  `f9e596f4`, postvalidated clean, retained unchanged trusted-bundle digests,
  and was safely removed after the terminal findings.
- That follow-up required one canonical seven-line production coordinator
  prompt that binds the Python, CLI, and GPG executables, supplies
  every production window/history/run input, and drives `doctor`, the complete
  status/accept/advance loop, `export`, and `finalize`. At that checkpoint,
  startup authority committed the executed `session_retrospective_v2.py` bytes
  and access policy without exposing that entrypoint as an importable module.
  Shared process cleanup separates irreversible signal retirement from a later
  non-signaling
  `ESRCH` absence proof, so an interrupted signal attempt can never signal a
  reused group identifier. Local history admission and every bound-command
  revalidation perform a bounded, stable, descriptor-relative pack-directory
  scan, reject non-ASCII pack names, and compare ASCII `.promisor` suffixes
  case-insensitively without approximating native Unicode filesystem aliases.
- Exact reviewer-fix checks pass: the two final lifecycle/promisor regressions
  pass 2/2, the complete publication invariant class passes 41/41, module
  boundaries pass 19/19, CI/Skill/Bootstrap contracts pass 46/46, and Darwin
  security contracts pass 14/14. Ruff 0.13.2 lint and formatting, both
  workflows under bounded `actionlint`, the official OpenAI Skill validator,
  and `git diff --check` are clean. A final read-only audit found one
  filesystem-alias gap in the first promisor implementation; the uppercase
  `.PROMISOR` and default-ignorable Unicode regressions close it before the
  full gate. The four shards already running on the superseded normalization
  approximation were interrupted, fully quiesced, and are non-counting. The
  same independent auditor re-read the portable-ASCII fix and returned
  `No findings.`
- The final Python 3.13 inventory contains 1,822 exact test IDs from 22
  authenticated source modules under manifest digest
  `aa7f2596594301058fb466ce1e5a307b42ea396f9e71aada14a3471dcdcfb456`.
  Shard 0 passes 435/435 in 1,658.325 seconds, shard 1 passes 493/493 in
  1,457.583 seconds, shard 2 passes 479/479 in 1,391.880 seconds, and shard 3
  passes 415/415 in 1,328.226 seconds. Every bounded shard exits zero with an
  explicit `OK` terminal summary and no failure, error, traceback, or skip, for
  exact aggregate coverage of 1,822/1,822. The final tree also passes Darwin
  security 14/14, the final promisor integration regression 1/1, publication
  invariants 41/41, module/CI/Skill/Bootstrap contracts 65/65, Ruff 0.13.2
  lint and changed-file formatting, bounded `actionlint` for both workflows,
  the official OpenAI Skill validator, project-journal validation, source-tree
  bytecode exclusion, branch inventory caps, and `git diff --check`.
- Signed head `ce394511` became stale when its fresh whole-range Codex
  processor found three remaining coordinator-control gaps: the installed
  prompt omitted exact provider-state and production-marker bindings, startup
  could execute old entrypoint bytes while later attesting a replacement path,
  and the prompt over-applied `$remote-host-context` to native local actions.
  Its detached reviewer workspace postvalidated clean and was removed.
- The public `session_retrospective_v2.py` is now a minimal installed
  descriptor launcher and explicit outer trust root. It captures and
  double-reads the separate `session_retrospective_v2_runtime.py`, transfers
  descriptor custody only after the runtime binds exact content, identity, and
  access policy into the startup receipt, and rejects direct runtime execution.
  A successful CLI response cannot precede an unreported runtime-descriptor
  close failure. The receipt requires exactly one runtime row and rejects any
  claim that the outer launcher was captured by that receipt.
- Production cutover now validates an eight-line byte-exact prompt. Both
  `doctor` and `start` bind the independently supplied canonical GPG program,
  default provider state, and default production marker. The authenticated
  cutover record and each automation-record reference HMAC-bind the same GPG
  path, so prompt text cannot select its own signer. Native source commands are
  executed exactly once and verbatim; `$remote-host-context session-shards` is
  used only when the exact run-owned action names it.
- Two bounded read-only precommit audits found five actionable omissions: the
  prompt-derived GPG expectation, remote-helper substitution in the CLI
  reference, insufficient canonical stage-binding tests, successful-exit
  descriptor-close handling, and an overbroad startup-receipt module grammar.
  All five were fixed before the final inventory. Three earlier four-shard
  starts were intentionally interrupted and fully quiesced after discovering
  launcher mode, fixture inventory, or precommit-audit defects; they are
  non-counting. A later non-isolated 68-test CLI probe produced only the
  expected runtime-authority errors and is also non-counting.
- The final Python 3.13 inventory contains 1,827 exact test IDs from 22
  authenticated source modules under manifest digest
  `1959ee1c66186e4b03fd2a983987af1ddea619f9b58ad39faf2b9736cf9fc3e6`.
  Shard 0 passes 436/436 in 1,652.268 seconds, shard 1 passes 494/494 in
  1,453.825 seconds, shard 2 passes 482/482 in 1,386.621 seconds, and shard 3
  passes 415/415 in 1,323.896 seconds. Every bounded runner exits zero with an
  explicit `OK` terminal, for exact aggregate coverage of 1,827/1,827. Ruff
  0.13.2 lint and changed-file formatting, both workflows under `actionlint`,
  the generated bootstrap manifest, the official OpenAI Skill validator,
  branch and module budgets, and `git diff --check` pass. The validator's first
  host-Python attempt lacked PyYAML and is non-counting; the official validator
  passed under `uv run --with pyyaml`.
- Signed head `5e3023ae` became stale after two independent review processors
  exposed three remaining contract gaps. The fresh local Codex processor found
  that non-shadow startup accepted copied provider-state and production-marker
  paths instead of the fixed production bindings, and that the canonical
  cutover example omitted the required `publisher_gpg_program`. Current-head
  GitHub Codex then found that the shared personal-data grammar omitted
  `Birthday`, `Birth date`, and `Birthdate` labels. The local reviewer workspace
  postvalidated clean, retained unchanged trusted-release digests, and was
  safely removed after its terminal findings.
- Non-shadow CLI, public engine, and direct lifecycle startup now reject every
  alternative provider-state or production-marker path before the engine can
  create a run. Shadow startup retains its explicitly isolated path contract,
  and malformed shadow-successor inputs retain their own closed validation
  precedence before production binding. The cutover reference supplies every
  required keyword in the live authority signature. The shared personal-data
  grammar now recognizes `birthday` plus controlled space, underscore, hyphen,
  compact, and camel-case `birth date` forms across source-overlap redaction,
  audit redaction, retained assembly, retained reread, and rendered-report
  validation, while policy/status prose remains accepted.
- The first 1,830-test production-binding shard group under manifest digest
  `ed580319df893bf5eed77b2e08078256ed94b741213e390a2d27e42278eafa97`
  was intentionally interrupted and is non-counting after the new GitHub P1
  invalidated its source tree. The next group exposed the deterministic
  shadow-successor error-precedence regression: shard 1 failed 1 of 495 tests,
  shards 2 and 3 passed on the stale tree, and shard 0 was interrupted. Direct
  non-isolated focused invocations that stopped at runtime authority are also
  non-counting; exact isolated reruns supplied the passing evidence.
- The final Python 3.13 inventory contains 1,830 exact test IDs from 22
  authenticated source modules under manifest digest
  `f1ab5f7af11db5504b3786c73e4bb200ab2f06f49f9bb2e68f5af21ed05d4261`.
  Shard 0 passes 436/436 in 1,631.108 seconds, shard 1 passes 495/495 in
  1,431.228 seconds, shard 2 passes 483/483 in 1,367.274 seconds, and shard 3
  passes 416/416 in 1,308.112 seconds. Every runner exits zero with an explicit
  `OK` terminal, for exact aggregate coverage of 1,830/1,830. The final tree
  also passes the three privacy-boundary focused regressions, the three
  isolated CLI ordering/binding regressions, module boundaries 19/19, CI
  contracts 33/33, Ruff lint and changed-file formatting, both current
  workflows under `actionlint`, the generated bootstrap manifest, the official
  OpenAI Skill validator, project-journal validation, and `git diff --check`.
  One earlier `actionlint` invocation named a nonexistent stale workflow path
  and is non-counting; the exact current workflow checks passed.
- Signed head `4d7442e0` became stale when the next fresh local Codex processor
  found one production authority defect: `doctor` and `start` authenticated the
  cutover marker only after resolving and potentially executing the
  caller-selected GPG program, and neither path compared that actual executable
  target with the marker's authenticated `publisher_gpg_program`. The review
  workspace postvalidated clean, all trusted bundle digests stayed unchanged,
  and the task root was removed after the terminal finding.
- Production startup now loads and authenticates the complete marker before
  publisher readiness, durable-history verification, or any GPG invocation.
  The new `orchestrator_startup_authority.py` owner compares canonical actual
  executable targets, permits only harmless aliases to the same target, and
  rejects a different target before creating run or history state. Publication
  fixtures now model an authenticated update on the fixed automation paths when
  a test intentionally selects a different GPG executable.
- The first 1,831-test attempt under manifest digest
  `e9a155b650693b0664ef9f73afcbcb0a1a3c73cf6a8a71c22f932b6ff4739944`
  exposed the stale publication fixture and was interrupted after all four
  shards reported the same marker-authority error. After that fixture fix, the
  next attempt under digest
  `f1f8ae72d9645c22c8edaa636afc80f30d04d28b4999994d22d9b7da30c8a523`
  exposed two expected `implementation_authority_invalid` failures in shard 3
  because the generated runtime source manifest did not yet include the new
  module; the other shards were interrupted. Both groups, a non-PTY focused
  run without a delivered terminal, and a focused invocation with an incorrect
  unittest class name are explicitly non-counting.
- The final Python 3.13 inventory contains 1,831 exact test IDs from 22
  authenticated source modules under manifest digest
  `f1f8ae72d9645c22c8edaa636afc80f30d04d28b4999994d22d9b7da30c8a523`.
  Shard 0 passes 436/436 in 1,630.139 seconds, shard 1 passes 495/495 in
  1,429.418 seconds, shard 2 passes 483/483 in 1,362.516 seconds, and shard 3
  passes 417/417 in 1,299.089 seconds. Every runner exits zero with an explicit
  `OK` terminal, for exact aggregate coverage of 1,831/1,831.
- The final tree also passes the production GPG authority regressions 10/10,
  module boundaries 19/19, CI contracts 33/33, bootstrap contracts 12/12,
  Ruff 0.13.2 lint and formatting, both current workflows under `actionlint`,
  the generated bootstrap manifest check, the official OpenAI Skill validator,
  source-tree bytecode exclusion, and `git diff --check`.
- Signed head `a71acca9` passed all hosted CI checks and a fresh local Codex
  processor returned `No findings.` from an independently materialized
  workspace. That evidence became stale when current-head GitHub Codex review
  `4981201468` found two remaining personal-data detector gaps: controlled
  surname, family-name, and given-name fields were not recognized, while date,
  time, and long dotted-version text could be misclassified as bare phone
  numbers. The local reviewer workspace postvalidated clean, retained unchanged
  trusted-release digests, and was safely removed.
- The shared personal-data grammar now recognizes controlled `surname`,
  `family name`, and `given name` labels across source-overlap scanning,
  post-redaction, retained assembly and reread, and rendered-report validation.
  Bare-phone filtering now excludes bounded 19xx/20xx date prefixes and
  four-or-more-component dotted numeric versions without weakening ordinary
  international, parenthesized, or compact phone detection. The exact four
  finding regressions pass 4/4 in 45.331 seconds, the three affected modules
  pass 182/182 in 95.263 seconds, and module boundaries pass 19/19 in 2.167
  seconds.
- The first current-fix 1,831-test group under manifest digest
  `5a100214c9afcd3d335f185e710feade8a524212da4e777b418b9ff775b37fec`
  is non-counting: shard 2 exposed the expected branch-total update, shard 3
  passed on the stale tree, and shards 0 and 1 were interrupted and proved
  quiescent. The final Python 3.13 inventory contains the same 1,831 exact test
  IDs from 22 authenticated source modules under manifest digest
  `5e5df32ccc896d59d96b8945b2c8c3626b369d831bb4553a86919d887740aede`.
  Shard 0 passes 436/436 in 1,703.799 seconds, shard 1 passes 495/495 in
  1,475.653 seconds, shard 2 passes 483/483 in 1,408.538 seconds, and shard 3
  passes 417/417 in 1,343.336 seconds, for exact aggregate coverage of
  1,831/1,831. Darwin security tests pass 14/14 in 70.362 seconds.
- The final current-fix tree also passes Ruff 0.13.2 lint and changed-file
  formatting, both current workflows under `actionlint`, the generated
  bootstrap manifest check, the official OpenAI Skill validator, source-tree
  bytecode exclusion, and `git diff --check`. A full-repository Ruff formatting
  probe identified six unchanged baseline files and is non-gating; no unrelated
  formatting changes were made.
- Signed head `70a75621` had clean exact-secret admission but became stale when
  its fresh local Codex processor found one P1 privacy gap: controlled `legal
  name`, `preferred name`, and `maiden name` fields were not recognized. The
  independent workspace postvalidated with the exact original graph and config
  receipts, the 30-file trusted bundle and Python digests remained unchanged,
  the reviewer closed, and the task root was removed through the bounded cleanup
  helper before source changes resumed.
- The shared closed name-field grammar now includes `legal`, `preferred`, and
  `maiden` modifiers for controlled space, underscore, hyphen, camel-case,
  Markdown, and narrative forms. Source-overlap extraction, scanner/redactor,
  retained artifact reread, audit, and rendered report validation all consume
  the same policy. The first three-test focused invocation exposed four
  misplaced bare-field expectations and is non-counting; after preserving the
  existing field-boundary semantics, the exact focused set passes 3/3 in 47.632
  seconds, the affected modules pass 182/182 in 96.824 seconds, and module
  boundaries pass 19/19 in 1.911 seconds.
- The final Python 3.13 inventory contains 1,831 exact test IDs from 22
  authenticated source modules under manifest digest
  `9e110ee8eb5e819e2b5a258e81d0fff3f30180ba5b8bf15a0c86ce89aebb34f6`.
  Shard 0 passes 436/436 in 1,692.399 seconds, shard 1 passes 495/495 in
  1,482.433 seconds, shard 2 passes 483/483 in 1,419.951 seconds, and shard 3
  passes 417/417 in 1,343.546 seconds, for exact aggregate coverage of
  1,831/1,831. Darwin security tests pass 14/14 in 68.027 seconds.
- The final tree also passes Ruff 0.13.2 lint and changed-file formatting, both
  current workflows under `actionlint`, the generated bootstrap manifest
  check, the official OpenAI Skill validator, and `git diff --check`.
- Signed head `61958060` became stale when current-head GitHub Codex found two
  remaining gaps. The shared personal-data grammar omitted controlled
  `nickname` and `display name` labels, and the publisher sign/verify canary
  allowed ambient temporary-directory selection to place its disposable files
  inside a retrospective source tree.
- The final privacy grammar separates subject-qualified and direct personal
  labels from ambiguous product prose. Direct `Nickname:` and `Display name:`
  assignments, controlled narrative boundaries, camel-case fields, Markdown,
  and comma-form names remain protected, while ordinary service display names
  and release nicknames remain ordinary product text. Name-component overlap
  extraction removes closed trailing metadata before splitting components, so
  status text is never promoted into the sensitive-value set.
- The publisher canary now uses a fixed owner-only root beneath `/tmp`, rejects
  both lexical and resolved overlap with the canonical local source before and
  after creation, and gives GPG a closed environment whose three temporary
  variables bind the exact disposable child. The secure-I/O cold capability
  probe also selects `/tmp` explicitly instead of consulting ambient temporary
  variables. Darwin's process-runtime-only `__CF_USER_TEXT_ENCODING` addition
  is the sole tested child-environment exception and cannot inherit its ambient
  value.
- Two bounded read-only precommit audits found and drove the final ambiguity,
  trailing-metadata, cold-probe, production-root, lexical-overlap, and actual
  child-environment regressions. The resulting affected modules pass 241/241
  in 119.463 seconds; CI contracts pass 33/33, module/bootstrap/skill contracts
  pass 36/36, and Darwin security contracts pass 14/14 in 68.661 seconds.
  The four-shard 1,833-test attempt under manifest digest
  `53b25db3ffad09d56ffcc2f22b79dc760f7d787d3c0547563d774a3ea73e7b9e`
  was intentionally interrupted after the audits invalidated its tree and is
  non-counting. A direct CI-contract invocation through the symlinked Homebrew
  launcher is likewise non-counting; the required owner-controlled copied
  Python 3.13 runtime supplied the passing 33/33 evidence.
- The bounded audit cutoff then produced five additional actionable findings,
  so the preceding 1,836-test result is stale for the superseding tree. Bare
  ambiguous name fields could still match dotted product qualifiers or a
  colon-delimited product narrative, quoted trailing status metadata could be
  split into a name component, and the canary root had a check-to-child-create
  replacement window. The same audit identified two remaining ambient
  temporary-root consumers in the legacy remote-helper snapshot and publication
  Git index.
- Ambiguous direct labels now exclude dotted qualification, ambiguous narrative
  labels require a line/list boundary or an explicit `observed`, `recorded`, or
  `reported` introducer, and the closed metadata suffix accepts quoted keys and
  assignment forms before name-component splitting. The exact reviewer examples
  remain protected or ordinary product text as intended.
- A shared descriptor-bound temporary-directory authority now owns fixed,
  purpose-specific canary, remote-helper, and publication-index roots. It creates
  each random child through a held root descriptor; binds root and child identity
  and access policy; verifies the actual resolved location before publication,
  around path consumers, and before cleanup; and removes only an inventoried
  matching object. Ambient `TEMP`, `TMP`, `TMPDIR`, and Python's cached temp root
  cannot select these locations. The adversarial parent-replacement regression
  fails before yielding a path and leaves the retrospective source unchanged.
- The first expanded affected run passes 126 of 128 tests and reports only the
  two deliberately exact static inventories changed by the new authority. After
  updating those measured contracts, the four exact boundary regressions pass
  4/4; the initial focused behavioral set passes 8/8 in 2.507 seconds. Full
  superseding-tree evidence follows below.
- On the pre-follow-up superseding tree, the affected orchestrator,
  result, and boundary modules pass 128/128 in 18.867 seconds; bootstrap and
  skill contracts pass 17/17 in 4.674 seconds; isolated source transport passes
  129/129 in 61.007 seconds; publication transactions pass 132/132 in
  5,252.573 seconds; export passes 72/72 in 105.082 seconds; result-contract
  audit passes 24/24 in 2.594 seconds; and CI contracts pass 33/33 in 2.166
  seconds. Darwin security contracts pass 14/14 in 71.210 seconds.
- That pre-follow-up Python 3.13 inventory contains 1,838 exact test IDs from 22
  authenticated source modules under manifest digest
  `252092f073fd3581786e3bd1742a9d1417e53f29301ad118b54c331ab55602c0`.
  Shard 0 passes 438/438 in 1,806.130 seconds, shard 1 passes 496/496 in
  1,592.075 seconds, shard 2 passes 486/486 in 1,523.450 seconds, and shard 3
  passes 418/418 in 1,461.025 seconds, for exact aggregate coverage of
  1,838/1,838. A final bounded privacy audit then made this result stale.
- That audit found five remaining composition and evidence gaps. Contextual
  personal fields did not accept dotted subject paths or a spaced subject plus
  camel-case field; ambiguous direct assignments did not accept explicit
  observation or sentence boundaries; structural product qualifiers could be
  lost after punctuation; quoted and escaped trailing metadata used different
  match-span and overlap grammars; and one canary regression fixture could write
  arbitrary inherited environment values while demonstrating a failure.
- The contextual name grammar now accepts subject-qualified dot, underscore,
  space, and camel-case combinations. Ambiguous direct and narrative labels
  share explicit observation and sentence-boundary rules while retaining parent
  product qualifiers, and one shared quoted or escaped metadata grammar governs
  both redaction spans and overlap extraction. The canary fixture persists only
  environment keys, fixed safe values, and a boolean synthetic-canary result.
  The first two-test focused invocation exposed four incorrect expected outputs
  and is non-counting; after correcting those expectations, the exact tests pass
  2/2 in 2.135 seconds. The affected modules pass 23/23, 86/86, 72/72, and
  24/24, module boundaries pass 19/19, and the follow-up read-only audit reports
  `No findings.`
- The final Python 3.13 inventory contains 1,838 exact test IDs from 22
  authenticated source modules under manifest digest
  `5262f57c841f882d8e3360d42cb77bda34b55be49ca111f7734d83b5a435adb7`.
  Shard 0 passes 438/438 in 1,728.045 seconds, shard 1 passes 496/496 in
  1,496.264 seconds, shard 2 passes 486/486 in 1,428.447 seconds, and shard 3
  passes 418/418 in 1,380.751 seconds, for exact aggregate coverage of
  1,838/1,838.
- The final tree passes Ruff 0.13.2 lint and changed-file formatting, both
  current workflows under bounded `actionlint`, the generated bootstrap
  manifest check, the official OpenAI Skill validator, project-journal
  validation, source-tree bytecode exclusion, and `git diff --check`.
- Signed head `2b09e19e` had clean exact-secret admission but became stale when
  its fresh local Codex processor found one P1 raw-evidence gap: the remote
  transport output spool and both session-shards spools still delegated their
  placement to ambient `TEMP`, `TMP`, `TMPDIR`, or Python's cached temp root.
  The independent workspace postvalidated with its original graph and config
  receipts, the trusted bundle and Python digests remained unchanged, and the
  reviewer task root was removed through the bounded cleanup helper.
- The three spools now use separate fixed roots under the shared
  descriptor-bound temporary-directory authority. Every file receives an
  explicit admitted directory, is descriptor-hardened before raw bytes are
  written, and remains enclosed by directory revalidation and inventoried
  cleanup. Real poisoned-environment regressions spy on the real temporary-file
  factories and bind every explicit `dir` to an owner-`0700` random child of the
  purpose-specific root; they also prove that source trees remain byte-identical
  and the roots are empty after success. The source worker's closed module
  manifest includes the new authority dependency; its reachability contract and
  the four isolated snapshot regressions pass 5/5.
- The first 1,840-test P1-fix shard group is non-counting: a bounded precommit
  audit found that the initial poisoned-environment regressions observed only
  post-cleanup trees, which could not prove the placement of immediately
  unlinked anonymous files. All four process-group-bounded shard sessions were
  interrupted once, reached terminal exit 130, and were quiescent before the
  real factory-binding assertions were added. The corrected exact regressions
  pass 2/2. One affected-suite session then became unavailable before its
  terminal result could be collected and is non-counting. A replacement harness
  incorrectly applied a 4 MiB process-wide file-size limit, causing three
  fixture writes to fail with `EFBIG`; that harness result is also non-counting.
  Without that inherited limit, the complete affected source and session-shards
  transport modules pass 172/172 in 57.700 seconds.
- The final Python 3.13 inventory contains 1,840 exact test IDs from 22
  authenticated source modules under manifest digest
  `744f59832de0e0374bf5ab8feb358c81d2b12685200487613b4ebf6a945e747b`.
  Shard 0 passes 438/438 in 1,810.306 seconds, shard 1 passes 498/498 in
  1,580.265 seconds, shard 2 passes 486/486 in 1,514.090 seconds, and shard 3
  passes 418/418 in 1,450.248 seconds, for exact aggregate coverage of
  1,840/1,840. Darwin security tests pass 14/14 in 70.579 seconds. An earlier
  accidental Darwin invocation with an unretained session handle was terminated
  once and is non-counting; the counted run used a pollable process-group
  deadline and reached a complete terminal result.
- The final tree passes module boundaries 19/19 in 2.047 seconds, Ruff 0.13.2
  lint and changed-file formatting, both current workflows under bounded
  `actionlint`, the generated bootstrap manifest check, the official OpenAI
  Skill validator, project-journal validation, source-tree bytecode exclusion,
  and `git diff --check`. One direct isolated `python -m unittest` boundary
  invocation lacked the repository loader and produced only `_FailedTest`; it
  is non-counting, and the required closed loader supplied the passing 19/19
  result.
- Signed head `7250e302` had clean exact-secret admission but became stale when
  its fresh local Codex processor found one P1 helper-selection gap: the legacy
  relay derived the installed `remote_codex_probe.py` path through
  environment-sensitive `Path.home()` before launching the authenticated
  snapshot with the real account and SSH agent environment. The independent
  reviewer workspace postvalidated with its original 74-commit, 73-edge graph
  and config receipts; trusted bundle, Skill, guard, and Python digests remained
  unchanged; the agent closed; and the exact task root was removed.
- Remote helper selection and the sanitized relay child environment now share
  one POSIX account-database authority. It validates the account name, resolves
  the declared absolute home to an existing canonical directory, and derives
  both the helper path and child `HOME` from that result. A real legacy-relay
  regression places executable account and poisoned-home helpers side by side,
  proves only the account helper executes, and requires both snapshot and output
  spool roots to be empty afterward. Additional fail-closed cases cover invalid
  names, relative or malformed homes, and missing homes. Focused tests pass 3/3,
  the complete source-transport module passes 132/132 in 52.570 seconds, module
  boundaries pass 19/19 in 1.876 seconds, and Ruff lint/format plus
  `git diff --check` are clean. Full superseding-tree evidence follows below.
- The superseding Python 3.13 inventory contains 1,842 exact test IDs from 22
  authenticated source modules under manifest digest
  `883518f7535f66d1530215c2f13ce8b6e7fc3a51e8a6bbe660b06c5f029c398b`.
  Shard 0 passes 438/438 in 1,795.699 seconds, shard 1 passes 498/498 in
  1,573.032 seconds, shard 2 passes 488/488 in 1,505.547 seconds, and shard 3
  passes 418/418 in 1,438.351 seconds, for exact aggregate coverage of
  1,842/1,842. Darwin security tests pass 14/14 in 71.126 seconds.
- The superseding tree also passes module boundaries 19/19 in 2.055 seconds,
  Ruff 0.13.2 lint and changed-file formatting, both current workflows under
  bounded `actionlint`, the generated bootstrap manifest check, the official
  OpenAI Skill validator, project-journal validation, source-tree bytecode
  exclusion, and `git diff --check`.
- Current-head GitHub review then identified five independent gaps. Retained
  privacy validation missed a labeled street address, a bare private-style
  host and port, and a six-octet MAC address. Publication's temporary index did
  not override repository `core.splitIndex=true`. GPG's `--no-options` excluded
  `gpg.conf` but did not prevent `gpg-agent.conf` from redirecting agent logs.
  All five findings block the `7250e302` evidence and are fixed in the
  superseding tree.
- Shared privacy locators now recognize and redact labeled street addresses,
  strict six-octet MAC addresses with one consistent delimiter, and bounded
  hyphenated or private-prefix bare host/port tokens without treating ordinary
  timestamps, status codes, or versions as hosts. Report, agent-result, and
  retained-history validators consume the same detectors. Publication Git now
  forces `core.splitIndex=false`; its end-to-end regression proves no new
  `sharedindex.*` object appears even when the repository enables split index.
- Every publisher inventory, canary, sign, and verify operation now uses a
  config-free keyring snapshot. The source directory is held and revalidated by
  descriptor, and only `pubring.kbx`, optional `trustdb.gpg`, and bounded strict
  40-hex private-key files are copied. GPG configuration, sockets, and unrelated
  entries are excluded. Agent shutdown uses one bounded Assuan `KILLAGENT`
  exchange, and cleanup accepts only fully bound GPG lock files whose complete
  link inventory remains inside the snapshot. External hard links fail closed.
  A process-local readiness cache is bounded to eight entries and keyed by the
  exact selected-key commitment plus executable authority; configuration-only
  changes may reuse a successful readiness result, while selected keyring or
  GPG executable changes force revalidation. Actual sign and verify operations
  remain uncached.
- One deliberately interrupted redundant publication-module invocation exposed
  a retained GPG lock snapshot. It is non-counting. The exact retained object
  was recovered through descriptor-bound lock validation and cleanup, and the
  fixed `/tmp/csr501` snapshot parent was verified empty afterward. Host-level
  Python probes that failed executable-authority or isolation admission are also
  non-counting; all counted tests use the owner-controlled Python 3.13.12
  runtime with `-I -B -S`.
- The first complete 1,850-test run found six stale fixture assumptions rather
  than product failures. Shard 0 ran 441 tests with one failure in 1,767.253
  seconds, shard 1 passed 500/500 in 1,612.229 seconds, shard 2 ran 489 tests
  with four failures in 1,473.081 seconds, and shard 3 ran 420 tests with one
  error in 1,423.025 seconds. The six publisher fixtures had empty keyring
  homes, an ambient unsafe temporary ancestor, or a nonexistent GPG substitute,
  so the new snapshot admission correctly preempted their intended downstream
  assertions. That aggregate is non-counting.
- The fixtures now construct the smallest admitted keyring, use the fixed
  trusted GPG substitute, clear the readiness cache between distinct mocked
  outcomes, and assert that GPG reads the isolated snapshot rather than the
  source home during an ABA exercise. The exact six regressions pass 6/6 in
  0.748 seconds. The complete publication-invariant and orchestrator classes
  pass 177/177 in 526.951 seconds. The complete source-transport module passes
  132/132 in 56.221 seconds, including poisoned ambient `HOME` coverage.
- The final Python 3.13 inventory contains 1,850 exact test IDs from 22
  authenticated source modules under manifest digest
  `5d7a48f46008e0bb968a910ce6585d0dda9e61d1a61512aeecaa5675e4b4629a`.
  Shard 0 passes 441/441 in 1,697.732 seconds, shard 1 passes 500/500 in
  1,547.084 seconds, shard 2 passes 489/489 in 1,420.324 seconds, and shard 3
  passes 420/420 in 1,376.397 seconds, for exact aggregate coverage of
  1,850/1,850. The independent Darwin security inventory passes 14/14 in
  60.241 seconds.
- The final tree passes module boundaries 19/19 in 1.961 seconds, CI contracts
  33/33 in 2.279 seconds, Ruff 0.13.2 lint and changed-file formatting, both
  current workflows under `actionlint`, the generated bootstrap manifest check,
  and `git diff --check`. One repository-wide formatting probe reported six
  unchanged baseline files and is non-counting; changed-file formatting is
  clean. One `actionlint` invocation named a nonexistent stale workflow path
  and is also non-counting; the two current workflow files pass together.
- Two final bounded precommit audits found eight additional issues before the
  delivery head was frozen. The transport/privacy audit found an unredacted
  camel-case `streetAddress` label, an account-snapshot split between helper
  selection and launch, prefix-only MAC matches, ambiguous `Node:20` and
  `Server:2025` host/port matches, and a source-snapshot regression that did not
  prove which helper file executed. The GPG audit found a readiness-cache ABA
  between two independent keyring snapshots, a per-byte Assuan timeout that
  multiplied the intended bound, and a private-key inventory copied without a
  closing enumeration and byte reread. All eight issues were fixed before the
  final manifest was generated.
- The relay now captures one validated account tuple and uses it for helper
  selection, snapshot materialization, launch environment, and execution. The
  privacy grammar consumes camel-case street-address labels, bounds six-octet
  MAC tokens against embedded or extra-octet identifiers, and requires a real
  host signal before treating a labeled host/port value as sensitive. The
  source regression proves the content-addressed helper snapshot, rather than
  the live installed helper, executed without changing the installed helper's
  identity, bytes, or mode.
- Publisher readiness now opens one descriptor-held configuration-free keyring
  snapshot and binds both its cache commitment and validation to that same
  receipt. Assuan shutdown uses one monotonic deadline across the complete
  exchange and socket disappearance, and private-key copying closes its
  inventory with a second enumeration plus a second exact read of every
  selected object. The direct new regressions pass, publication invariants pass
  49/49 in 2.453 seconds, source transport passes 132/132 in 56.810 seconds,
  and module boundaries pass 19/19 in 1.949 seconds.
- Two intermediate invocations are explicitly non-counting. One used an
  incorrect isolated-import module shape and produced eight import errors. A
  later 225-test affected-module run exposed six stale compatibility-export
  fixtures; the exact compatibility tests and the complete source-transport
  module passed after those exports were repaired.
- The superseding Python 3.13.12 inventory contains 1,853 exact test IDs from
  22 authenticated source modules under manifest digest
  `a1da7d4f23d067ffe550845b0b09cb50781866030b4042932beb8359e325aed6`.
  Shard 0 passes 442/442 in 1,708.395 seconds, shard 1 passes 501/501 in
  1,557.650 seconds, shard 2 passes 490/490 in 1,440.213 seconds, and shard 3
  passes 420/420 in 1,392.431 seconds, for exact aggregate coverage of
  1,853/1,853 on one frozen code-and-test tree.
- The superseding documentation tree passes the independent Darwin security
  inventory 14/14 in 62.954 seconds, CI contracts 33/33, skill contracts 5/5,
  Ruff 0.13.2 lint and changed/new-file formatting, both current workflows
  under `actionlint`, the generated bootstrap manifest check, the isolated
  official OpenAI Skill validator, project-journal validation, source-tree
  bytecode exclusion, and `git diff --check`.
- The fresh local Codex processor over signed head `0f9fdc45` found two
  actionable gaps. Remote source leases froze helper bytes but did not carry
  the scheduler-time account/home authority into the independent worker, and
  the shared privacy grammar did not recognize strict dotted hardware
  addresses such as `0011.2233.4455`. That review workspace postvalidated with
  its original 75-commit, 74-edge graph and config receipts; the trusted bundle
  digests remained unchanged, the agent closed, and the exact task root was
  removed. The head's clean exact-secret admission and prior test evidence are
  stale for delivery because the findings require a substantive successor.
- `transport_remote_account.py` now owns a closed canonical account binding.
  Scheduling commits account name and UID/GID plus the canonical home object's
  device/inode/generation, mode/owner/group, masked mutation-policy flags, and
  exact bounded ACL digest in the authenticated command and lease. The worker
  re-resolves and compares the
  binding immediately before launch and passes that same snapshot explicitly
  to the relay environment. Account-record changes, same-path home replacement,
  and access-policy changes stop before `Popen`; timestamp-only home churn is a
  tested benign transition. The installed helper remains a separate run-owned
  content snapshot.
- The shared MAC grammar now covers strict colon/hyphen octets and strict
  three-by-four dotted groups while rejecting embedded, short, mixed, and
  extended shapes. MAC substitution precedes generic personal-number
  substitution, and extraction scan, deterministic redaction, retained-value,
  and complete `report.md` validation use the same owner. Nine exact focused
  regressions pass 9/9. A 249-test affected-module run exposed only two stale
  test-contract assertions; after those were repaired, their exact regressions
  plus timestamp churn pass 4/4. Full successor-tree evidence follows below.
- The first four-shard attempt after these fixes was stopped once per shard and
  is non-counting: shard 0 immediately proved that the generated startup
  manifest did not yet include the new worker module, while the other shards
  were still running. The generated manifest was refreshed through its
  canonical writer and its three exact bootstrap regressions pass 3/3 before
  the counted run began.
- An intermediate counted Python 3.13.12 inventory contains 1,855 exact test
  IDs from 22
  authenticated test modules under manifest digest
  `0586747e7012683e3b167237c5e9a1c4a6eb8259609a041fb32c0d93f7bbbb56`.
  Shard 0 passes 443/443 in 1,751.808 seconds, shard 1 passes 502/502 in
  1,602.268 seconds, shard 2 passes 490/490 in 1,481.212 seconds, and shard 3
  passes 420/420 in 1,424.039 seconds, for exact aggregate coverage of
  1,855/1,855 on one frozen code-and-test tree. A subsequent final-diff audit
  narrowed home flags to the existing mutation-policy mask and explicitly
  rejected relative account-database homes, so this complete result is valid
  for its intermediate tree but stale for final delivery.
- That intermediate tree passes the independent Darwin security inventory
  14/14 in 62.226 seconds, CI contracts 33/33, skill contracts 5/5, Ruff lint
  and changed-file formatting, the canonical bootstrap-manifest check, both
  current workflows under `actionlint`, the isolated official OpenAI Skill
  validator, project-journal validation, source-tree bytecode exclusion, and
  `git diff --check`.
- The final Python 3.13.12 inventory contains 1,855 exact test IDs from 22
  authenticated test modules under manifest digest
  `f0a41401235b1c00aa5e1061fba2d041f33cf8c2a0e38e979ec6253145298a59`.
  Shard 0 passes 443/443 in 1,602.272 seconds, shard 1 passes 502/502 in
  1,461.888 seconds, shard 2 passes 490/490 in 1,347.049 seconds, and shard 3
  passes 420/420 in 1,296.144 seconds. The aggregate is 1,855/1,855 on the
  final frozen code-and-test tree; no interrupted or intermediate run is
  counted toward this result.
- The final tree also passes the independent Darwin security inventory 14/14
  in 59.404 seconds, CI contracts 33/33 in 2.258 seconds, Skill contracts 5/5,
  and Bootstrap contracts 12/12. Ruff 0.13.2 lint and changed/new-file
  formatting, both current workflows under `actionlint`, the generated
  bootstrap manifest check, the isolated official OpenAI Skill validator,
  project-journal validation, source-tree bytecode exclusion, and `git diff
  --check` are clean.
- The fresh local Codex processor over signed head `3b6f2749` found one P2
  documentation-contract mismatch: the normative architecture guide still
  described the pre-account-binding transport module count and line budgets.
  The lane postvalidated with its original 76-commit, 75-edge graph and config
  receipts; the trusted control bundle remained at digest
  `d12328d7a2da38c7c2edc58287a194faedbc4a37587ca047dbd48db34ac0a5b9`,
  the reviewer closed, and the exact task root was removed. The guide now
  mirrors the enforced 17-module, 9,124/9,150 aggregate and affected
  single-file baselines. Admission and review evidence for `3b6f2749` are stale
  for delivery because this correction creates a successor head.
- Signed head `67dacf78` passed its local full suite, exact-secret admission,
  fresh local Codex processor, and hosted CI, but current-head GitHub Codex
  found three retained-privacy precision gaps. Quoted RFC-style email local
  parts such as `"john doe"@example.com` bypassed the shared detector, ordinary
  slash compounds such as `input/output` were treated as relative paths, and
  dotted code or filename text such as `json.loads`, `config.toml`, and
  `foo.bar` was treated as a bare FQDN. Those head-bound results are stale.
- The shared privacy owner now accepts bounded quoted email local parts,
  including escaped quotes. Relative paths require an explicit dot prefix, a
  file extension, or a controlled repository/path root. Bare FQDNs require a
  controlled public suffix unless an explicit port or path supplies host
  syntax; closed host labels preserve fail-closed handling for internal names
  with unknown suffixes. Scanner, redactor, retained assembly and reread, and
  rendered-report validation consume the same grammar. The complete affected
  result and export modules pass 159/159 in 116.488 seconds.
- Two four-shard attempts were deliberately stopped and are non-counting after
  review showed that their intermediate path and FQDN grammars remained too
  broad. Every exact runner was interrupted once and proved absent before the
  final tree was frozen. The final canonical Python 3.13 inventory contains
  1,856 exact test IDs from 22 authenticated source modules under manifest
  digest `ad3f2d97af1adbebad47c36064614dce605824d94ee10cdbe85ce09c30573d65`.
  Shard 0 passes 443/443 in 1,602.341 seconds, shard 1 passes 503/503 in
  1,459.892 seconds, shard 2 passes 490/490 in 1,348.476 seconds, and shard 3
  passes 420/420 in 1,301.493 seconds, for exact aggregate coverage of
  1,856/1,856 on one frozen code-and-test tree.
- The same tree passes the independent Darwin security inventory 14/14 in
  68.466 seconds, CI contracts 33/33, and module, Skill, and Bootstrap
  contracts 36/36. Ruff 0.13.2 lint and changed-file formatting, both current
  workflows under `actionlint`, and the isolated official OpenAI Skill
  validator are clean. The final signed head, exact-secret admission, fresh
  local Codex processor, hosted CI, and current-head GitHub Codex evidence
  remain required before merge.
- Signed head `f82edf1a` had clean exact-secret admission, then its fresh local
  Codex processor found one P1 retained-privacy gap: the email grammar admitted
  alphabetic domain suffixes but not an IDNA A-label such as `xn--p1ai`.
  Ordinary and quoted-local punycode email addresses could therefore bypass
  scanning, deterministic post-redaction, and retained validation. The exact
  78-commit, 77-edge workspace postvalidated with graph digest
  `18bda83a7538290b21e94791eaa01832b80ecc7cea568f634d0b0451c48c9673`;
  trusted bundle digests remained unchanged, the reviewer closed, and the task
  root was removed through the bounded cleanup helper.
- Email domains now reuse the shared closed FQDN suffix grammar, including
  bounded IDNA A-labels. Ordinary and quoted-local punycode cases are covered
  across scanner, post-redaction, retained assembly and reread, and rendered
  report validation. The result module passes 87/87, export/reporting passes
  72/72, and module boundaries pass 19/19.
- The superseding Python 3.13 inventory contains 1,856 exact test IDs from 22
  authenticated source modules under manifest digest
  `aba584ef02578ca84d423d6431e52a395e3996186e34555651beca50e26912c6`.
  Shard 0 passes 443/443 in 1,598.527 seconds, shard 1 passes 503/503 in
  1,453.245 seconds, shard 2 passes 490/490 in 1,341.446 seconds, and shard 3
  passes 420/420 in 1,290.600 seconds, for exact aggregate coverage of
  1,856/1,856. Signing, exact-secret admission, the replacement fresh local
  Codex processor, hosted CI, and current-head GitHub Codex evidence remain
  delivery gates.
- The superseding tree also passes the independent Darwin security inventory
  14/14 in 83.515 seconds, CI contracts 33/33, and module, Skill, and Bootstrap
  contracts 36/36. Ruff 0.13.2 lint and changed-file formatting, both current
  workflows under `actionlint`, the generated bootstrap manifest, the official
  OpenAI Skill validator, and project-journal validation are clean. A direct
  invocation of the Darwin marker module selected zero tests and is explicitly
  non-counting; the canonical Darwin runner supplied the result above.
- The fresh local Codex processor over signed head `ea906546` found one P1
  retained-privacy gap: bare FQDN recognition still depended on a manually
  enumerated suffix subset, so an assigned root-zone name such as
  `api.customer.technology` could bypass scanning, post-redaction, retained
  assembly/reread, and report validation. The exact 79-commit, 78-edge
  workspace postvalidated with graph digest
  `54dd5bb1e3c2c107f0cb9a48a7d46086630bd8139e3077c545f5591363a31192`
  and config digest
  `07990c1d83a78ea34a87e3f51883e3164c3098b21770082207e00a3a898ab24f`.
  Trusted bundle digests remained unchanged, the reviewer closed, and the task
  root was removed through the bounded cleanup helper.
- Bare FQDN classification now consumes the embedded IANA Root Zone TLD
  snapshot version 2026082000. Its 1,438 unique sorted suffixes are bound to
  canonical digest
  `aa0a75a9860b2cba07d7fe8172f4546d981be3674bf6764fb0d5f39a45940d25`
  and fail closed at import if the count, ordering, uniqueness, or digest
  drifts. Explicit port/path forms and closed reserved/private suffixes remain
  covered. An assigned-suffix token is exempted only when every label belongs
  to the closed metasyntactic identifier set and an immediate code-usage
  context is present, preserving `foo.bar attribute` without allowing
  `customer.technology method` to escape. Focused cross-layer tests pass 4/4
  in 65.400 seconds, the full result/reporting modules pass 160/160 in 118.001
  seconds, the privacy contract audit passes 25/25, and module boundaries pass
  19/19.
- The final Python 3.13.12 inventory contains 1,857 exact test IDs from 22
  authenticated source modules under manifest digest
  `6b6b4f5d740e7565a1c4b429199d9bed6153d5cb3143e514386909fc0159040c`.
  Shard 0 passes 444/444 in 1,608.435 seconds, shard 1 passes 503/503 in
  1,462.892 seconds, shard 2 passes 490/490 in 1,342.134 seconds, and shard 3
  passes 420/420 in 1,298.136 seconds, for exact aggregate coverage of
  1,857/1,857 with an empty combined error scan.
- The same tree passes the independent Darwin security inventory 14/14 in
  59.321 seconds and the CI, Skill, and Bootstrap contract matrix 50/50. Ruff
  0.13.2 lint and changed-file formatting, both workflows under
  `actionlint`, the generated bootstrap manifest check, the isolated official
  OpenAI Skill validator, project-journal validation, source-tree bytecode
  exclusion, and `git diff --check` are clean. One temporary focused runner
  used a removed private test-inventory helper and failed before selecting a
  test; the canonical isolated focused runner supplied the counted 4/4 result.
  One bootstrap probe passed an unsupported `--check` flag and is likewise
  non-counting; the supported no-argument check passed.
- The fresh local Codex processor over signed head `413c7bc4` found two
  temporary-lifecycle gaps. Abnormal exit could retain publisher key snapshots
  and live GPG processes indefinitely because startup had no stale recovery;
  separately, an operation error plus temporary cleanup failure remained only
  an exception note and could be reported as retryable. The exact reviewer
  workspace postvalidated and was removed; all head-bound evidence is stale.
- The follow-up adds one persistent owner-only recovery lock, bounded N+1 root
  and snapshot inventories, exact `g-<64 lowercase hex>` names, descriptor-bound
  stale-child recovery, strict known-socket policy, and bounded
  `SCD KILLSCD` followed by `KILLAGENT`. Unknown entries, replacements, policy
  drift, or cleanup uncertainty retain the object and block a new snapshot.
  The root lock now covers only inventory, child creation, and final deletion;
  each in-use child holds a separate owner-only `.active.lock` lease. Recovery
  skips a proved busy lease and reclaims an unlocked crash-retained child, so
  independent publisher operations can overlap without losing stale-recovery
  authority.
  Sensitive cleanup failures now produce a content-free, non-retryable
  `temporary_cleanup_incomplete` CLI result while preserving only allowlisted
  primary metadata.
- Focused recovery tests pass 10/10 in 0.344 seconds, including two real
  overlapping snapshot processes and a symlinked-lease rejection. The three
  exact tests that previously collided under the lifecycle-wide root lock pass
  3/3 in 94.512 seconds. Module-boundary tests pass 19/19. The
  production recovery path also reclaimed the exact crash-retained
  `/tmp/csr501/g-*` snapshot exposed by the interrupted canonical run: its bound
  GPG-agent and scdaemon terminated, the stale child disappeared, and the fixed
  root retained only `.recovery.lock`. Earlier direct-import and pycache-drift
  attempts selected no valid canonical suite or changed their source authority
  and are explicitly non-counting. Final canonical shard and review evidence
  follows on the frozen successor tree.
- The first four-shard run after stale recovery is also non-counting: shards 0
  and 1 passed 447/447 and 505/505, while shards 2 and 3 reported three exact
  config-free keyring failures caused by holding the recovery root lock across
  the complete snapshot lifetime. Sequential reruns passed because they did not
  exercise that concurrency. The active-lease design above closes the root
  cause.
- The first complete durable-publication run after the active-lease change is
  non-counting: 89/91 tests passed and two tests exposed a shutdown race where
  the bound GPG agent removed an optional socket between inventory and
  revalidation. Recovery now accepts disappearance only for a socket whose
  identity was already bound during that shutdown attempt; an unknown socket
  or an observed replacement remains blocking. Both exact failed tests pass
  2/2 in 150.136 seconds after the correction.
- The final Python 3.13.12 inventory contains 1,869 exact test IDs from 22
  authenticated source modules under manifest digest
  `f7865302894620aa7c149f1ae9b2667f24350c134ef32e67ec5713b2b6ba53e4`.
  Shard 0 passes 447/447 in 1,729.066 seconds, shard 1 passes 506/506 in
  1,585.872 seconds, shard 2 passes 495/495 in 1,461.386 seconds, and shard 3
  passes 421/421 in 1,412.890 seconds, for exact aggregate coverage of
  1,869/1,869. All four bounded supervisors reached terminal exit zero.
- The same tree passes the independent Darwin security inventory 14/14 in
  62.297 seconds, module boundaries 19/19, CI contracts 33/33, Skill contracts
  5/5, and Bootstrap contracts 12/12. Ruff 0.13.2 lint and formatting for all
  13 changed or new Python files, both workflows under `actionlint`, the
  generated bootstrap manifest check, the isolated official OpenAI Skill
  validator, project-journal validation, source-tree bytecode exclusion, and
  `git diff --check` are clean. A whole-repository format probe identified six
  unchanged baseline files and is non-counting; none is modified by this
  workstream. Signing, exact-secret admission, the replacement fresh local
  Codex processor, hosted CI, and current-head GitHub Codex evidence remain
  delivery gates.
- The fresh local Codex processor over signed head `34f094c0` found one P1
  recovery gap: when specialized publisher-snapshot finalization could not
  reacquire root coordination or prove publisher-agent cleanup, it marked the
  primary error but the outer generic temporary-directory context still
  removed the sensitive snapshot tree. The exact 81-commit, 80-parent-edge
  workspace used graph digest
  `a7791180954fe013a79284bbe568596d4ca0302540f7a08e23d9ce1c44a13781`
  and config digest
  `07990c1d83a78ea34a87e3f51883e3164c3098b21770082207e00a3a898ab24f`.
  It postvalidated clean, the trusted bundle digests remained unchanged, the
  reviewer closed, and the task root was removed through the bounded cleanup
  helper. All head-bound evidence for `34f094c0` is stale.
- A bound temporary directory now has one explicit, mutable recovery-retention
  decision. Publisher-snapshot finalization sets that decision before returning
  to the generic context. The generic owner closes held descriptors but skips
  recursive removal, preserving the exact child and active lease for a later
  root-lock holder's bounded stale recovery. A retention request without an
  active primary fails closed rather than returning success. Exact regressions
  cover both root-coordination and publisher-agent failures, prove the key
  directory and active lease survive the failed operation, and prove the next
  startup recovers the same retained tree. The focused retention set passes
  4/4 in 0.231 seconds, the publisher-canary path contracts pass 4/4, and module
  boundaries pass 19/19.
- The final Python 3.13.12 inventory contains 1,870 exact test IDs from 22
  authenticated source modules under manifest digest
  `de3f825d6789c0a6ab9ec1487d9467b7637a30a058df0f791d2805c7fc6c0f1b`.
  Shard 0 passes 448/448 in 1,724.884 seconds, shard 1 passes 506/506 in
  1,578.021 seconds, shard 2 passes 495/495 in 1,460.118 seconds, and shard 3
  passes 421/421 in 1,412.093 seconds, for exact aggregate coverage of
  1,870/1,870. Every bounded supervisor reached terminal exit zero.
- The same frozen tree passes the independent Darwin security inventory 14/14
  in 59.399 seconds, module boundaries 19/19, CI contracts 33/33, Skill
  contracts 5/5, and Bootstrap contracts 12/12. Ruff 0.13.2 lint and
  changed-file formatting, both current workflows under `actionlint`, the
  generated bootstrap manifest check, the isolated official OpenAI Skill
  validator, project-journal validation, source-tree bytecode exclusion, and
  `git diff --check` are clean. Two malformed focused selectors failed before
  selecting the intended tests, and one unquoted bytecode glob failed before
  scanning; each is explicitly non-counting. Signing, exact-secret admission,
  the replacement fresh local Codex processor, hosted CI, and current-head
  GitHub Codex evidence remain delivery gates.
- Signed head `48e90fd8` passed exact-secret admission, then its fresh local
  Codex processor found one P1 recovery gap. When the primary `S.gpg-agent`
  socket refused a connection but an independently listening `S.scdaemon`
  socket remained, stale recovery treated the snapshot as listener-free,
  unlinked every socket, and could delete the tree while leaving the auxiliary
  process and smart-card session alive. The exact 82-commit, 81-parent-edge
  workspace used graph digest
  `ba097f72c26fc09d39d697e9dc78dcffabe4371fc3174ec950a075516dda4e7d`
  and config digest
  `07990c1d83a78ea34a87e3f51883e3164c3098b21770082207e00a3a898ab24f`.
  It postvalidated clean, the trusted bundle digests remained unchanged, the
  reviewer closed, and the task root was removed through the bounded cleanup
  helper. All head-bound evidence for `48e90fd8` is stale.
- Stale recovery now connection-probes every identity-bound known agent socket
  under one monotonic deadline when the primary refuses a connection. A live,
  timed-out, unreadable, replaced, or otherwise unprovable auxiliary listener
  retains the complete snapshot and blocks the new operation. The socket
  removal owner repeats the complete listener-absence proof before unlinking
  any member, then revalidates each identity immediately before removal. Real
  Unix-socket regressions prove that a live `S.scdaemon` survives both startup
  recovery and direct pre-unlink cleanup while an ordinary stale primary remains
  recoverable. The focused recovery set passes 4/4 in 0.176 seconds, the full
  publication invariant class passes 62/62 in 3.031 seconds, and module
  boundaries pass 19/19.
- The final Python 3.13.12 inventory contains 1,872 exact test IDs from 22
  authenticated source modules under manifest digest
  `6be0958f1237e20580a63488130aab324cbb3d2bc05536d342282f71b74a7f45`.
  Shard 0 passes 448/448 in 1,623.840 seconds, shard 1 passes 507/507 in
  1,480.513 seconds, shard 2 passes 496/496 in 1,365.717 seconds, and shard 3
  passes 421/421 in 1,321.138 seconds, for exact aggregate coverage of
  1,872/1,872. Every bounded supervisor reached terminal exit zero.
- The same frozen tree passes the independent Darwin security inventory 14/14
  in 59.488 seconds, module boundaries 19/19, CI contracts 33/33, Skill
  contracts 5/5, and Bootstrap contracts 12/12. Ruff 0.13.2 lint and
  changed-file formatting, both current workflows under `actionlint`, the
  generated bootstrap manifest check, the isolated official OpenAI Skill
  validator, project-journal validation, source-tree bytecode exclusion, and
  `git diff --check` are clean. One direct isolated unittest selector failed
  before import because it bypassed the repository loader, and the first direct
  pre-unlink fixture exceeded Darwin's AF_UNIX path limit before exercising
  production code; both are explicitly non-counting. Signing, exact-secret
  admission, the replacement fresh local Codex processor, hosted CI, and
  current-head GitHub Codex evidence remain delivery gates.
- The replacement fresh local Codex processor over signed head `3c10105e`
  found a deeper P1 in the listener-probe correction. `ECONNREFUSED` proves
  only one instant: the same bound Unix socket can begin listening without an
  inode, mode, or owner change after the final probe and before unlink. The
  exact workspace contained 83 commits and 82 parent edges under graph digest
  `c087f2915ddb6ad80e7be38852fa98ca4b76f3e708e058cdbe22efd5c6ceafcd`
  and config digest
  `07990c1d83a78ea34a87e3f51883e3164c3098b21770082207e00a3a898ab24f`.
  It postvalidated clean, the trusted bundle digests remained unchanged, the
  reviewer closed, and its exact task root was removed. All head-bound
  evidence for `3c10105e` is stale.
- Recovery no longer converts a refused or absent socket into deletion
  authority. Without prior proof, a stale snapshot must complete the real
  bounded Assuan shutdown and observe every bound socket disappear. Normal
  cleanup and successful recovery remove GPG locks, confirm the empty socket
  inventory, then create exact owner-only `.agent-cleanup.proved` bytes through
  the held child descriptor and durably re-read them. A valid marker permits a
  later root-lock holder to remove a cleanup-complete retained tree. Missing,
  malformed, symlinked, replaced, unreadable, or access-policy-drifted proof
  blocks recovery, as does a pre-agent crash with neither a marker nor a socket
  that can complete Assuan shutdown. A publisher-agent cleanup failure never
  emits the marker. Real regressions prove that a refused bound socket can
  begin listening after recovery fails without being unlinked, while a live
  scdaemon and every unproved snapshot remain retained.
- The final Python 3.13.12 inventory remains 1,872 exact test IDs from 22
  authenticated source modules under manifest digest
  `bbdd0cffe527ea884b2857ce70104d17eb1a6dca47a3d083c1010a6395ca20fe`.
  Shard 0 passes 448/448 in 1,643.871 seconds, shard 1 passes 507/507 in
  1,492.648 seconds, shard 2 passes 496/496 in 1,374.246 seconds, and shard 3
  passes 421/421 in 1,327.314 seconds, for exact aggregate coverage of
  1,872/1,872. Every bounded supervisor reached terminal exit zero. The
  focused publication invariant class passes 62/62, including five cleanup
  proof variants, and module boundaries pass 19/19.
- The same tree passes the independent Darwin security inventory 14/14 in
  60.427 seconds, CI contracts 33/33, Skill contracts 5/5, and Bootstrap
  contracts 12/12. Ruff 0.13.2 lint for `scripts/` and `tests/`, changed-file
  formatting, both current workflows under bounded `actionlint`, the generated
  bootstrap manifest check, the isolated official OpenAI Skill validator,
  source-tree bytecode exclusion, and `git diff --check` are clean. One direct
  CI-contract invocation omitted `-I` and exercised only the entrance guard;
  one initial Darwin run lost its caller session ID and was allowed to terminate
  before the bounded replacement started. Both are explicitly non-counting.
  Project-journal validation, signing, exact-secret admission, the replacement
  fresh local Codex processor, hosted CI, and current-head GitHub Codex evidence
  remain delivery gates.
- The replacement local Codex processor over signed head `82e03e4d` found one
  P2 readiness mismatch. Shadow `doctor` reported an explicitly supplied
  provider cache as not applicable, while shadow `start` validated the same
  cache against durable history and failed when it was missing, stale, or
  malformed. The exact 84-commit, 83-parent-edge workspace used graph digest
  `92c2764b9fae9b1df0fdba782542a5488c8ab7674b23ed16151e24b7c732c0d0`
  and config digest
  `07990c1d83a78ea34a87e3f51883e3164c3098b21770082207e00a3a898ab24f`.
  It postvalidated clean, the trusted bundle digests remained unchanged, the
  reviewer closed, and its exact task root was removed through the bounded
  cleanup helper. All head-bound review evidence for `82e03e4d` is stale.
- Shadow provider state remains optional, but `doctor` now validates every
  explicitly supplied provider cache with the same durable-history binding as
  `start`. An omitted shadow provider retains the established not-applicable
  result; production still requires one. The paired stale-provider regression
  proves both entry points fail closed through the same validator. The focused
  pair passes 2/2 in 0.740 seconds, and the complete 133-test orchestrator
  module passes in 548.788 seconds. Canonical discovery now contains 1,873
  exact test IDs from 22 sources under manifest digest
  `79de0299d076fb3d98d69aa4a4d1a1bd036f909ee78c1cd6d98b2a2887134ee3`.
  The final tree also passes module boundaries 19/19, CI contracts 33/33,
  Skill contracts 5/5, Bootstrap contracts 12/12, Ruff lint and formatting for
  both changed Python files, the generated bootstrap-manifest check,
  project-journal validation, source-tree bytecode exclusion, and
  `git diff --check`. One bootstrap-manifest invocation incorrectly supplied
  an unsupported `--check` option and is non-counting; the documented default
  check then passed. Signing, exact-secret admission, the final local Codex
  processor, hosted CI, and current-head GitHub Codex evidence remain delivery
  gates.

## Follow-up Work

1. Register `Joey-Tools/codex-session-retrospective` in `codex-workspace` after
   the standalone source PR merges.
2. Extend and release the canonical `remote-host-context` transport with the
   exact `session-shards` and `source-transport` declarations before enabling
   remote retrospective runs. That integration belongs to its owning
   repository and is not implemented by this standalone source PR.
3. Design and review replacement private sync and installed-release
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
