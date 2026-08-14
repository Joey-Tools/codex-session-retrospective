# Repository Guidelines

- Explanations and summaries use Simplified Chinese. Code, comments,
  identifiers, commit messages, and Markdown code blocks use English.
- The repository root is the canonical `codex-session-retrospective` skill
  directory. Keep `SKILL.md` procedural; put detailed contracts in
  `references/` and deterministic implementation in `scripts/`.
- Retrospective source access is read-only. Never add a path that mutates Codex
  session data, remote hosts, or archived session state.
- Python 3.13 is the supported development and CI runtime. Launch repository
  tests with `-B -S`; do not commit bytecode or runtime cache files.
- Preserve stable source, turn, episode, topic, run, and publication identity
  contracts. A missing or unverifiable source must become an explicit gap,
  never silent exclusion or inferred no-activity.
- Redaction and retained validation are separate defenses. Retained history
  must not contain raw prompts, tool output, paths, internal URLs, credentials,
  personal data, or raw source identifiers.
- `remote-host-context` owns host registry and SSH transport. This repository
  owns only the retrospective-side request, receipt, and bounded shard
  contracts.
- Do not add private sync mappings or modify `codex-private-workflows` until the
  standalone implementation has completed its own delivery gate.
