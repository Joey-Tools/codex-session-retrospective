# Migration Provenance

This repository is the new canonical owner of the complete
`codex-session-retrospective` skill.

## Source

- Source repository: `Joey-Tools/codex-workflow-hygiene`
- Original delivery base: `db0991dc549da5c29cd2cc34695979d1a875c079`
- Closed original PR #67 head: `c358b9507de4b19a8c733ee3266be75ab6288814`
- Closed replacement PR #69 head: `f1b5c71f581d511e4b96944e6bcd432bae2b80e1`

The remote branches and signed source commits remain available. They were not
rewritten or deleted. Follow-up fixes that were still in the #69 owner worktree
are carried into this repository and become reviewable only through this
repository's own signed commit history.

## Ownership Boundary

This repository owns the skill, deterministic engine, CLI, schemas, tests, and
Retrospective-side transport contracts. It does not own:

- the `remote-host-context` SSH registry or host implementation;
- the append-only retained history repository;
- the private overlay source lock, generated overlay, or installed release;
- removal of legacy files from `codex-workflow-hygiene`.

Those integrations are intentionally deferred until the standalone
implementation is complete. Legacy removal will be delivered by a separate PR
after installation has been verified, so there is no interval with no canonical
source.
