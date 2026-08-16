# Codex Session Retrospective

`codex-session-retrospective` is the canonical source repository for Joey's
read-only, cross-host Codex collaboration retrospective skill.

The repository owns:

- the explicit-invocation Codex skill and agent metadata;
- the deterministic v2 coordinator and its closed CLI/schema contracts;
- bounded local and remote source transport adapters;
- extractor, episode, topic, and global map-reduce job contracts;
- redacted reporting, append-only history export, and publication recovery;
- the migration-only v1 helper used for shadow comparison until cutover.

Retained reports are published separately to
`Joey-Tools/codex-session-retrospective-history`. Remote source collection is
provided by the installed `remote-host-context` transport; this repository does
not own SSH host registry or private overlay installation.

## Installed Entry Point

After a future private sync integration, the supported installed coordinator
path will be:

```bash
python3 -I -B -S "$HOME/.codex/skills/codex-session-retrospective/scripts/session_retrospective_v2.py" --help
```

The coordinator requires Python 3.13 or newer. See
[`references/v2-cli.md`](references/v2-cli.md) for the machine-readable loop and
[`references/v2-engine-architecture.md`](references/v2-engine-architecture.md)
for ownership boundaries.

Production and shadow readiness require one explicit absolute
`--publisher-gpg-program`. Its executable identity, bytes, and ancestor access
policy are committed into each run and reused without a `finalize` override.

## Development

Run the repository contract first, then the complete Python 3.13 suite:

```bash
python3.13 -I -B -S -m venv --copies .codex-tmp/python
chmod 0755 .codex-tmp/python/bin/python3
.codex-tmp/python/bin/python3 -B -S -m unittest discover \
  -s tests -p test_ci_contract.py
.codex-tmp/python/bin/python3 -B -S -m unittest discover -s tests
```

The tests are intentionally standard-library-only. CI creates owner-controlled
Python 3.13 virtual environments, disables bytecode writes, and runs four
stable, disjoint test-ID shards under explicit job timeouts.

## Migration State

The implementation was extracted from the closed
`Joey-Tools/codex-workflow-hygiene` PRs #67 and #69. The superseded source was
removed from that repository after extraction, and the prior installed and
scheduled copy was retired. This repository is now the only canonical source;
a new private sync and installed entry point remain a separate future phase. See
[`docs/migration-provenance.md`](docs/migration-provenance.md).
