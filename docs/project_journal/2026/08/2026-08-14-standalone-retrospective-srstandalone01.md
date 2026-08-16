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
