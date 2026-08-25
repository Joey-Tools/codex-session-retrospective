# Session Retrospective v2 Data Contract

The coordinator and all local transport workers require the same fixed
owner-controlled copied Python 3.13-or-newer runtime. Production does not use
ambient interpreter resolution.
The public entrypoint remains parseable under the Python 3.9 grammar solely so
older runtimes can emit the closed unsupported-runtime result before loading the
engine package; that parse path does not add runtime support.

## Source Transport Authority

A source cell is accepted only when all of these independently bound objects
agree:

- an identity-authenticated transport lease issued by the coordinator;
- the exact leased worker/engine program commitment and, for remote work, the
  run-owned `$remote-host-context` helper snapshot commitment;
- a closed source transport stream with an authoritative inventory terminal;
- an authenticated transport receipt binding the lease, manifest, independently
  derived source snapshot, transcript commitment, and terminal proof;
- exact raw bytes from the sealed stream or exact `session-shards` requests and
  streams that reassemble to that same transcript.

Arbitrary `eof_proof`, `terminal_receipt_ref`, path strings, or self-hashed
snapshots are not coverage evidence. Truncation, byte/count mismatch, program
replacement, helper replacement, and terminal mutation fail before the source
cell or cursor changes.

The transport program commitment uses a closed allowlist for every executable
Python module in the local v2 package, including package initialization,
catalog, contracts, identity, transport, and the worker entrypoint. The actual
package-tree `.py` inventory must equal that allowlist; a missing or unexpected
module fails closed. Each component is opened relative to an fd-anchored package
directory with `O_NOFOLLOW`, must be a bounded regular file, and is hashed only
after matching `fstat` and no-follow name identities before and after the read.

Before a remote lease is committed, the parent opens the installed
`$remote-host-context` helper and prepares its exact bytes for an owner-only,
content-addressed snapshot below that run's `raw-inputs` tree. The source
commitment derived from that same descriptor-bound read must equal the run's
frozen helper provenance before snapshot preparation or lease creation. The
installed helper location and the relay child's `HOME`, `USER`, and `LOGNAME`
share one POSIX account-database authority. The account home is resolved from
`getpwuid(getuid())` to an existing canonical absolute directory; ambient
`HOME` cannot select helper bytes or the child account context. A remote lease
also commits an exact closed-schema account binding: account name and UID/GID,
canonical home path, home object device/inode/generation, mode/owner/group,
masked mutation-policy flags, and the bounded ACL digest. The independent worker
parses that authenticated argv
binding, re-resolves the account and home immediately before helper launch, and
uses only the frozen account for `HOME`, `USER`, and `LOGNAME`. Account-record,
home-object, or access-policy drift therefore fails before SSH credentials or
configuration can be consumed; timestamp-only home churn is not mutation. The
transport-program bootstrap default is an owner-only cache beneath the fixed
`/tmp/codex-session-retrospective-<uid>` tree and never comes from `TEMP`,
`TMP`, `TMPDIR`, or Python's cached temp-root selection. The transport-program
snapshot, remote-helper snapshot, bound empty transport output, and candidate
checkpoint are capacity-checked and staged as one transaction;
none of those files is materialized before the candidate checkpoint fits. The
worker receives only the snapshot path and SHA-256 commitment. Its isolated
`-I -B` bootstrap opens the snapshot with no-follow descriptor checks, verifies
regular-file identity, owner, mode, link count, byte count, and digest, then
compiles exactly those retained bytes. Replacing the installed helper after
scheduling cannot change the program that executes, replacing it between leases
cannot mix helper versions within one run, and source acceptance revalidates the
same run-owned commitment.

The complete authenticated helper snapshot is a semantic code trust root. A
bounded AST pass separately derives the static `HOSTS` literal and one
top-level literal-tuple `SESSION_RETROSPECTIVE_COMMANDS` capability manifest
without executing the helper. The canonical helper builds its parser
registration from that same immutable manifest. The bootstrap compares the
runtime `HOSTS` value with that exact domain-separated commitment and replaces
it with immutable row and outer proxies before `main`. These checks reject
ordinary registry drift and accidental runtime mutation; they are not a Python
sandbox and do not claim to contain arbitrary reflective behavior from already
trusted helper bytes. Missing `session-shards` or `source-transport`
capabilities fail both `doctor` and `start` before run creation. If an older
run-owned snapshot reaches worker preflight, source transport records the
version skew as `remote_host_context_transport_incompatible`; only the
dedicated missing-capability error may take that path. Snapshot authentication,
binding, or execution failures remain hard failures and are never reclassified
as remote unreachability, no activity, or compatibility gaps. The bootstrap
normalizes its outcome into a closed status set: authenticated helper nonzero
results mean transport unavailable, while snapshot/runtime authentication and
helper entrypoint/execution failures retain separate typed relay errors. The
worker catches only the unavailable type when producing a coverage gap.

`session_index` and `history` use bounded metadata JSONL transport. Active and
archived rollouts use bounded rollout JSONL transport. Remote execution is always
delegated to `$remote-host-context`; v2 contains no SSH command, host table, or
generated remote program.

The `session-shards` adapter validates authoritative descriptor EOF, derives the
exact records-mode request, validates request/resume bindings and conservation,
and reassembles fragments before acceptance. One oversized logical JSONL record
retains one stable source/turn identity regardless of transport fragment count or
local shard packing. Transcript bindings cover exactly the `source_ref` values
that contain consumed candidates. Excluded-only source refs stay in catalog
accounting and require no raw transcript.

Descriptor pagination binds one stable source object, frozen byte end, record
coordinates, and domain-separated full-prefix commitment in every closed resume
cursor. Later appends cannot extend that descriptor snapshot. Continuation pages
must repeat the requested source token, frozen byte end, byte offset, and record
index exactly. Each page stops before its derived records stream would exceed
1,024 data frames, using the closed `max_record_data_frames` continuation reason.
A retained transcript stores every descriptor page first, followed by one exact
records stream per page. The adapter validates and closes the complete descriptor
chain before lazily replaying those contiguous records requests into the
coordinator. Abandoning any records iterator closes its replay immediately even
while the outer segment iterator remains live. Descriptor pages alone are
discovery metadata and never authorize retained raw evidence.

The `session_shards_source_v2` token binds device, inode, mode, owner, group, and
the platform generation and birth-time fields when they exist. On a filesystem
that supplies neither generation nor birth time, a same-inode replacement with
byte-identical frozen content cannot be distinguished from the prior object;
this is an explicit platform non-guarantee, not an identity proof. Every
records-mode request separately scans and hashes the complete frozen prefix into
an owner-only temporary spool beneath a fixed descriptor-bound root that ignores
ambient temporary-directory selection before emitting its first frame. Content
mutation anywhere in that prefix therefore rejects the stream even on the
fallback platform, while the spool retains only the requested byte range and
closes on every terminal path.

Remote descriptor and record streams are incrementally validated before spool.
Every frame is either consistently wrapped and bound to the exact requested
host and rollout, or consistently legacy-unwrapped and wrapped locally with
those exact values; missing wrappers at the adapter boundary, mixed wrapper
mode, and cross-host or cross-rollout replay fail closed. Record relay output is
bounded from the requested byte range plus compact metadata allowance, with
per-frame size, coordinates, fragments, hashes, counters, and terminal
conservation checked before the complete output can be retained.
Fragment continuation also repeats the logical record byte range, record-index
range, delimiter width, encoding, and complete-record commitment; drift in any
one field rejects the relay before retained output exists.

## Accounting, Shards, And Jobs

Every discovered source unit ends in exactly one accounting class:
`consumed_candidate`, `structurally_excluded`, or `explicit_gap`. Duplicate active
and archived copies retain distinct physical-file occurrence coordinates. An
archived record is excluded only by the closed canonical-equivalence rule when
there is exactly one equivalent active record; multiple active files never
collapse. Source discovery walks the complete active-rollout year/month/day
hierarchy through descriptor-relative no-follow opens under global entry and
candidate ceilings. It therefore includes old still-active sessions; exhausting
either ceiling produces an explicit coverage gap instead of a partial catalog.
Before a complete or no-activity terminal, the worker reopens every traversed
active directory through its anchored identity chain and requires the bounded,
type-aware entry snapshot to remain exact. A replacement or entry-set change is
an explicit enumeration gap rather than an incomplete success.
Archived discovery remains window-bound, and filesystem mtimes never prefilter
candidates. Resume positions use the closed
`source_transport_resume_v5` schema. They carry a public
`accepted_prefix_commitment` transition chain plus the exact trailing probe
range and content commitment; the chain is authoritative only because the
incoming position is carried by the authenticated durable checkpoint, lease,
and exact stream header and the outgoing position is independently reconstructed
by capture before the receipt is issued. `source_token` and public stat fields
never create or replace that authentication.

The `source_transport_stream_v3` inventory carries two closed, sorted identity
arrays. `direct_session_commitments` binds the zero, one, or two identities
parsed directly from the current row. `locator_session_commitments` carries the
same locator's accumulated state: zero for unknown identity, one for a unique
identity, or two as a permanent ambiguity witness. Neither array contains a raw
session identifier. Capture independently reparses each consumed payload and
requires its direct array to match, then requires the locator state to remain
unchanged or move monotonically from unique to ambiguous within the same source
locator. A new candidate starts from empty state. Current-row selection uses the
direct array whenever it is non-empty, including direct ambiguity, and inherits
the locator state only for an ID-less row. This lets an ID-less rollout record
after a bounded page break retain the commitment established by its earlier
`session_meta` without letting a cursor identity leak into the next rollout or
letting a direct multi-ID row fall back to the cursor target. Durable v4
continuations and v2 streams fail closed and require a new source-catalog run
rather than silently resuming without these commitments. Catalog schema v3 and
transport manifest v2 copy both arrays into each record's closed
`session_identity` witness. The catalog snapshot and authenticated transport
receipt therefore bind that witness independently of the mutable `source_ref`
label supplied at acceptance. Every uniquely identified source session derives
its stable Session reference from that selector commitment in every run mode;
the raw source identifier is never an alternate identity input.

Each invocation may spend at most three 64 KiB internal reads on resume probes;
budget exhaustion is the explicit `source_resume_probe_budget_exhausted` gap.
The worker rereads the current page separately to prove page stability, freezes
the original source size so later appends are not admitted to that snapshot, and
retains only the bounded trailing bytes needed to construct the next probe. It
never rescans `0..byte_offset` to continue. Without an immutable source snapshot,
this O(page) continuation detects only mutation intersecting the bounded
prior-prefix probe; it does not detect or claim to detect arbitrary mutation deep
in already accepted history. Every enumerated candidate is scanned or represented
by an explicit bound/transport gap, and stable event time, cursor, and window
classification happens only after the bounded read. Logical turn sequencing
preserves each physical file's
`byte_start` order before digest tie-breakers while deterministically merging
different files. Session mode consumes only records matching `session_target`,
records discovered for other sessions remain structurally accounted without
retained raw payload, and a submitted non-target consumed record is rejected.
An identity-unresolved record retains its content commitment and canonical
`(host_ref, content_commitment)`-derived unresolved session reference. Acceptance
re-derives every Session-mode source reference from the receipt-bound witness.
An unresolved witness must remain an exact source-transport explicit gap, and a
unique known non-target witness must remain a source-policy exclusion. A witness
matching the exact Session selector may never use `session_target_mismatch`, the
generic source-policy exclusion, or the unresolved-identity gap. Coordinated
relabeling of `source_ref` and accounting class therefore fails closed before
source acceptance.

- Extractor shard: at most 20 turns and 480 KiB.
- Agent input: at most 512 KiB, including its control envelope.
- Job identity: HMAC-derived from immutable inputs, role, schema, prompt, policy,
  and retry ordinal.
- Attempt identity: unique to one fresh launch and never reused as evidence
  identity.
- Task-cache metadata conserves every deterministic task lookup: one miss per
  created task, one hit/reuse per returned existing task, and the sum of
  per-task reuse counts. These counters and agent attempts are retained in run
  provenance.
- Claim identity: a bounded dispatcher lease over one attempt. Heartbeat extends
  only the matching unexpired claim; expiry permits safe takeover on the same
  attempt with a new envelope and output sink. Result acceptance binds the exact
  active, unexpired claim. Each fresh attempt permits exactly two claim
  generations: the initial claim and one expired-lease takeover. Further takeover
  or an over-limit result sink records `agent_claim_budget_exhausted` and closes
  that attempt through the ordinary retry/explicit-gap state machine without
  counting an agent result or accumulating more claim files.
- Every new claim, heartbeat, accepted result, and rejected-result disposition
  serializes the actual candidate checkpoint before commit. If either the task
  bound or the 512 KiB terminal reserve would be consumed, the coordinator
  restores the prior task/claim state, clears only the candidate envelope, sink,
  or result-sidecar staging it owns, and persists a content-free
  `checkpoint_capacity_exhausted` blocker from the reserve. A byte-identical
  replay that makes no state change needs no new reserve; replay-time migration
  of a legacy inline job manifest does and is blocked before that migration can
  consume the terminal reserve.
- A rejected-result action whose complete payload fits the 1 MiB rejection-hash
  ceiling uses the closed `agent_result_payload_rejection_action_v2` binding.
  Its identity commits the exact job, attempt, claim, result reference, complete
  payload SHA-256, and allowlisted rejection reason. An exact replay is
  idempotent; reusing the same attempt and payload with a different legal reason
  is a conflict and cannot mutate state. A payload beyond that ceiling is not
  sampled: the coordinator records a fresh content-free observation token in the
  closed `agent_result_payload_rejection_action_v3` binding together with
  `result_digest_exact: false`. That non-exact disposition is deliberately
  non-replayable, so a repeated command conflicts instead of treating two
  unknown payload middles as identical.
- Accepted agent results live in canonical owner-only sidecars under
  `agent-sinks/results`. The checkpoint stores only a closed descriptor that
  binds the task reference, canonical result hash, byte count, SHA-256 content
  commitment, and content-addressed run-relative path. Every consumer
  authenticates the descriptor and exact canonical payload before use. Existing
  checkpoints with a legacy inline result remain read-compatible, but every new
  acceptance stages the sidecar and its exact checkpoint revision as one
  transaction; a failed checkpoint commit rolls back only the newly created,
  identity- and content-matching sidecar.
- Immutable agent-task inputs live in canonical owner-only sidecars under
  `agent-sinks/task-inputs`. The checkpoint keeps only their authenticated
  descriptor plus bounded scheduling summaries; hierarchy inputs, turn metadata,
  candidate results, framing, and payloads remain sidecar-only. Each sidecar is
  capped at 640 KiB and every checkpoint task is capped at 16 KiB. Hierarchical
  partitioning probes the exact immutable sidecar bytes and the complete 512 KiB
  execution envelope before task creation; neither probe uses trimmed metadata.
  Synthesis leaves and parents carry only turn refs reachable from their exact
  topic/review subtree, so a large run partitions before sidecar materialization.
  child results occur exactly once in the immutable input payload; metadata keeps
  only their hashes and scheduling identities instead of embedding a second copy.
  Attempts retain
  only the deterministic job reference and manifest digest; claim and replay
  reconstruct the full manifest and require the digest to match before returning
  an execution envelope. A legacy attempt may carry the full manifest instead of
  its digest, but never both: the coordinator requires an exact reconstruction,
  migrates it to the digest form, and rejects every ambiguous or changed legacy
  representation before every active claim mutation, first result disposition,
  or terminal claim-budget replay. A migration-only transition consumes the same
  terminal checkpoint reserve as a new mutation; insufficient reserve restores
  the original inline representation and records the blocker. Replaying an
  accepted result also reauthenticates its result sidecar instead of trusting
  checkpoint status alone.
- Reassembled extracted turns live in one canonical owner-only,
  content-addressed sidecar under `agent-sinks/derived`. Its 96 MiB cap is
  independent of the 32 MiB checkpoint cap, and the checkpoint retains only a
  descriptor binding its schema, turn count, byte count, SHA-256 commitment, and
  run-relative path. Every consumer authenticates the complete canonical mapping
  and each turn reference. Legacy inline extracted-turn mappings remain
  read-compatible; new non-empty writes always use the sidecar.
- One run admits at most 1,500 deterministic agent-task cache misses. Exactly
  1,000 are reserved for extractor-redactor tasks and exactly 500 for episode
  review, adjudication, topic reduction, and global synthesis. Cache hits do not
  consume another task slot. Partition counters are authenticated checkpoint
  state and are reconstructed from legacy task state before a new miss is
  accepted. Before any task input, envelope, or shard is published, the
  coordinator serializes the exact candidate checkpoint and requires it to fit
  below the 32 MiB checkpoint bound with a 512 KiB terminal reserve. Scheduling
  exhaustion restores the prior state and records an explicit repairable blocker
  without staging files; claim and result transitions additionally remove their
  not-yet-committed candidate artifacts. These limits reserve the complete
  downstream pipeline before raw materialization and keep the conservative
  cleanup inventory at no more than 261,844 entries under its fixed 300,000-entry
  ceiling.
- Accepted source records and raw-payload indexes live in canonical, owner-only,
  content-addressed sidecars under `raw-inputs/source-acceptances`; authenticated
  checkpoint state stores only bounded descriptors and a compact manifest summary.
  Before segmented transport is consumed, the target host/source cell must have
  room below its 64-segment ceiling and the candidate batch must fit the
  run-global source capacity while reserving the complete 64 MiB per-segment
  acceptance-sidecar ceiling. These conservative proofs happen before streaming
  is enabled, the segment iterator advances, or a spool path is created; the
  same boundary returns an already-authenticated accepted lease replay directly
  from its durable action binding without consuming the supplied transport. The
  checkpoint transaction later repeats the cell check and uses the sidecar's
  exact canonical byte count for its final capacity check against the current
  state.
  Accepted bytes then stream into one deterministic
  lease-derived, owner-only, descriptor-held spool under
  `raw-inputs/source-spool-v1`. A persistent owner-only lock serializes retry;
  after acquiring it, the next process authenticates and removes only the same
  orphan spool. Exact byte and record caps are checked before every write. Only
  one bounded record is retained in memory; the coordinator keeps compact
  offsets, byte counts, content commitments, and final paths, so the legal 4 GiB
  corpus is never assembled in the Python heap. The spool is not retained
  evidence and is removed on replay, rejection, rollback, and successful
  materialization.
  Checkpoint capacity is proved before any final raw file or acceptance sidecar
  is created. A rollback receipt ledger is fully allocated before the first
  create and stores no payload bytes. Those files and the exact next checkpoint
  revision are then staged
  under one checkpoint lock: a proved unchanged old revision rolls back only
  identity- and content-matching files, an exact committed new revision retains
  them, and an unreadable or inconsistent disposition fails closed with explicit
  retained-file evidence. Rollback revalidates the held file's identity,
  single-link state, owner-only access policy, and exact content through two
  bounded descriptor reads before unlink. A same-schema checkpoint that still
  carries the legacy full manifest or inline payload index remains readable; the
  next accepted continuation validates conflicts and migrates that index into
  the new sidecar before clearing the inline copy. A run accepts at most 64
  continuation segments per host/source cell, 1,280 segments and 100,000 records
  in total, 4 GiB of source bytes, and 256 MiB of acceptance-sidecar bytes.
  Transcript and acceptance digests derive from the compact per-record
  descriptors. Materialization reads each accepted segment once, merges payload
  indexes in place, and sorts only the final aggregate; accepting a later segment
  never reloads earlier sidecars. The coordinator rejects an over-limit segment
  before final-file staging, leaving coverage unresolved rather than committing
  an incomplete aggregate.
- Raw sharding uses two bounded ordered passes over the authenticated source
  payload sidecars. The first pass retains only shard/gap manifests and rejects
  more than 1,000 shards before raw-shard I/O. A catalog record whose declared
  byte or turn count exceeds its processing budget becomes an explicit gap before
  its payload file is read. The second pass reads one source
  payload at a time, emits one shard at a time, and requires every emitted
  manifest plus the complete canonical manifest to match the first pass. Its
  working data is bounded by one source record, that record's fragments, the
  current shard, and one maximum-sized serialization buffer; the legal 4 GiB
  source corpus is never assembled in memory. Newly created shard files and the
  manifest are staged with the candidate checkpoint revision. A checkpoint
  failure performs descriptor-authenticated exact-file rollback, while an
  existing byte-identical artifact remains idempotent and is never claimed as a
  newly created rollback target.
- Every newly created staged file returns an object-identity receipt binding its
  parent identity, file identity, owner-only access policy, exact byte count, and
  SHA-256 content. A caller-owned receipt slot is allocated before I/O and is
  populated while the descriptor-held file still has only its deterministic
  pending name, before publication links the final name. The same receipt binds
  the pending and final names and can roll back the proved one-name pending,
  two-name commit, or one-name final state after any unwindable `BaseException`;
  an extra hard link or any identity/content/policy mismatch fails closed. All
  atomic creates in one directory share one persistent directory lock, so two
  target names cannot bypass each other's transaction boundary. Rollback
  reacquires that lock and performs two descriptor-bound content and policy
  samples before unlinking. Parent or leaf replacement, same-inode content
  mutation, unreadability, or policy drift fails closed and retains the path.
  Child-entry churn that does not change the protected parent identity is benign.
  The receipt excludes `SIGKILL`, `os._exit`, and a non-cooperating malicious
  same-UID writer from its guarantee; it proves the cooperating unwind and
  recovery boundary rather than claiming an atomic unlink-by-FD primitive the
  platform does not provide. Independent receipts and staging groups continue
  rollback after one retained mismatch; a close failure after a proved unlink is
  secondary evidence and cannot reverse the known disposition or replace the
  original primary failure.
- Exact cleanup inventory rejects non-regular leaf objects from descriptor-held
  parent metadata before opening them. Every subsequent file open uses
  `O_NOFOLLOW | O_NONBLOCK`, so a regular-file-to-FIFO replacement cannot block
  the cooperative traversal deadline before type and object identity are
  revalidated. Nonblocking open does not claim a hard I/O deadline for ordinary
  files or network/File Provider storage.
- Legacy inline cleanup claim v4 authentication binds the original field-present
  wire representation before semantic normalization; a missing legacy
  `content_commitment` and an explicit null are not interchangeable without a
  new valid claim reference. After quarantine rename, a missing durable progress
  marker still requires the complete planned relative-path set. Only a verified,
  fsynced marker permits a strict identity/content/policy-matching subset as
  evidence of monotonic cleanup progress.
- Raw run directory: mode `0700`; every file: mode `0600`. On Darwin, each
  owner-only directory and file must also have no extended ACL. Newly created
  objects clear inherited ACLs through their held descriptors before use;
  existing objects with an ACL fail closed rather than being repaired. Every
  existing ancestor is checked through its held descriptor: read-only and
  inheritance-only ACL entries remain admissible, while any allow ACE granting
  write, append, add, rename/delete, attribute/security mutation, or ownership
  change fails closed. The ancestor ACL policy is revalidated around each child
  open, so a late grant cannot redirect the descriptor walk.
- Every CLI command rejects a run directory whose lexical or resolved path is
  inside, contains, or aliases either canonical local `sessions/` or
  `archived_sessions/` source root. `start` performs this check before creating
  checkpoint, lock, raw-input, or sidecar state. A sibling owner-private run
  cache beneath
  `/absolute/canonical/account-home/.codex/session-retrospective/` remains
  valid.
- `doctor`, CLI `start`, and the public `start_run` facade apply the same
  bidirectional lexical and resolved-path separation to the durable history
  repository before readiness can pass or run state can be created. A history
  repository inside, above, or aliased into either source root is rejected; a
  sibling repository remains valid. Production defaults and exact bindings use
  the account-database-derived canonical home rather than ambient `HOME`, so
  environment poisoning cannot redirect this comparison.
- Successful publication removes raw shards. Blocked raw state expires within
  seven days and remains an explicit recoverability/coverage outcome.

Extractor validation receives bounded original prompt/tool-output material or
safe fingerprints directly from the sealed raw shard. It rejects ordinary raw
overlap before retained state is written; raw material never leaves working
retention. Each reassembled record is streamed through a strict UTF-8 and JSON
token parser. The parser validates literals and numbers with a closed grammar;
an invalid primitive cannot consume a following string. Object keys,
non-string primitives, exact per-field low-risk classifier values, and semantic
timestamps are not source-prose candidates. Unknown classifier values, model and
schema identifiers without an exact allowlisted value, instance-bearing IDs,
host and cwd values, typed references, digests, and commitments always remain
source candidates. Every other decoded string value, including long
escaped values and surrogate pairs, is case-folded, whitespace-normalized, and
split into overlapping bounded windows; no long prose value is skipped. The
overlap normalizer canonicalizes whitespace controls and removes non-whitespace
C0, DEL/C1, and Unicode default-ignorable codepoints before matching, so a
retained hidden character cannot hide a source excerpt. Agent-result strings
canonicalize whitespace controls before redaction and persist only the
normalized value; non-whitespace controls and default-ignorable characters,
plus every such field-name character, fail at the envelope boundary. The
normalizer accumulates one-character parser emissions in fixed-size chunks and
keeps the active window in a bounded deque rather than repeatedly copying a
growing string. The
result-side projection contains only the extractor's schema-authorized
`turns[].generalized_working_text`, both before and after deterministic
post-redaction. Source values from 4 through 11 normalized characters use
Unicode token-boundary matching, so a value such as `Acme` is removed from
derived prose without treating `Acmeology` as the same source token. Bare
domain locators are redacted when they carry an explicit port or path, end in
the digest-bound IANA Root Zone TLD snapshot version 2026082000, use a closed
reserved or private suffix, or appear in controlled host, domain, or endpoint
context. A no-port token with an assigned root suffix remains reviewable only
when every label belongs to the closed metasyntactic identifier set and an
immediately following closed code-usage label identifies it as a code symbol;
unassigned ambiguous dotted tokens also remain reviewable. Protocol URLs,
private locators, paths,
and bare hosts retain distinct deterministic precedence. Ambiguous slash-word
compounds remain
reviewable prose; relative paths require an explicit dot prefix, a common path
root, or a filename extension. Absolute, home, drive, and UNC locators consume
spaced intermediate components plus legal apostrophe and comma punctuation so
redaction cannot leave a residual directory suffix. POSIX absolute paths retain
their path classification with multiple leading separators; a multi-separator
start immediately after a colon remains owned by URI classification. Windows
extended and device namespace drive or UNC roots are path locators under the
same shared scan, redaction, and retained-validation policy. Hardware addresses
cover only strict six-octet colon/hyphen forms with one delimiter or strict
three-group dotted forms such as `0011.2233.4455`; embedded, shortened, mixed,
or extended tokens remain outside that grammar. MAC redaction precedes generic
personal-number redaction so every accepted hardware-address shape uses the
same deterministic placeholder. RFC-shaped email addresses with dot-atom or
bounded printable quoted local parts, including IDNA A-label domains, and
bounded single-label `account@host` identifiers are personal identifiers.
Every syntactically valid IPv4-shaped four-part dotted token is an address even
when nearby prose says `version` or `release`; retained version prose must use
an unambiguous form such as `v1.2.3.4`, a schema-constrained field, or a
placeholder instead of a natural-language exception.
Retained prose also treats package-shaped `name@tag` values as personal
identifiers; structured package coordinates must use schema-constrained fields
or placeholders instead of natural-language exceptions. Labeled medical
record numbers (`medical record number`, `MRN`, and controlled snake/camel
forms) use the shared personal-identifier policy;
subject-qualified `identifier` fields such as `customer identifier` and closed
camel-case equivalents use that same policy. Controlled `prompt`, `input`, and
`request` labels, including their `user`-qualified forms, are source-payload
markers only when followed by `:` or `=`; unlabeled derived prose remains
reviewable.
an immediately following colon keeps the complete SCP-style locator under the
higher-priority URL rule. Typed references and hashes
are exempt from source-literal
replacement only in result-side schema fields that are independently format- and
allow-list validated; the same bytes in retained prose are rejected. Fixed enum,
status, outcome, and object-key strings are not treated as retained source-derived
prose. Window batches have independent
item and aggregate-character bounds while preserving enough overlap to detect a
query split across windows or transport fragments.

The complete export input is stored as one owner-only, content-addressed
`retained-inputs` sidecar. Authenticated run state retains only its descriptor.
The descriptor binds canonical byte count, SHA-256 commitment, and the one
allowed relative filename; loading reads no more than that exact byte count and
revalidates the canonical payload, digest, run, mode, and window. Existing
same-v2 checkpoints with the exact legacy embedded `{run_state, review_data}`
shape remain readable, but new writes always use the sidecar. The sidecar is a
fixed authenticated cleanup root and is never retained in durable history.
Idempotent replay of each authenticated published, shadow, or expired terminal
cleanup clears any legacy embedded retained input after revalidating the
terminal receipt.

Before retained artifact assembly or staging, the CLI canonicalizes the ignored
output path and rejects every destination equal to or below `raw-inputs`,
`raw-shards`, `agent-sinks`, or `retained-inputs` for the current run. This keeps
shadow cleanup from deleting the bundle that the same command just exported.
Component comparison applies NFD before and after Unicode case folding, so
case-insensitive filesystem aliases are rejected conservatively on every
supported filesystem.

Export destination binding uses three immutable records so new and legacy CLI
writers cannot split one run across outputs. `cli-export-v2.json` remains the
legacy final-descriptor location. A new writer first occupies that location with
a closed v3 reservation, which prevents a not-yet-committed legacy writer from
later publishing a final descriptor there. `cli-export-destination-v2.json` is
the destination claim and `cli-export-result-v3.json` is the completed result.
An exact legacy final descriptor remains authoritative and is promoted to the
same claim before retry comparison. If an already-started legacy writer publishes
its no-replace claim after the reservation but before the new claim, that claim
becomes the effective destination; the conflicting invocation stops before
artifact assembly and an exact retry can finish it. Final receipt persistence
reauthenticates the effective claim and any legacy final descriptor. The result
continues to bind the bundle digest, publication role, and retention deadline.

## Partial And Backfill Lineage

Controlled missing-host authority uses the closed reasons
`missing_host_holdout` for production and `shadow_missing_host_holdout` for
shadow runs. Its authenticated aggregate receipt binds the partial run, host,
window, every required source kind, and every accepted source transport receipt.
It requires a later backfill and cannot authorize extraction, review, reduction,
malformed JSON, processing-budget, authentication, or transport gaps.

A backfill binds the controlled-gap receipt, `backfill_of`, the exact durable
backlog reference, prior episode revisions, episode-head root, and stable anchor
membership. A stable match must append one successor revision. An unmatched
episode from the exact controlled missing host may create one new initial
revision; session-only fallback matching is forbidden and every unrelated prior
head remains unchanged. The full proposed head projection is durable state, while
only changed or new revisions enter the review workset.
The authenticated run checkpoint revalidates the controlled-gap receipt and its
partial-run, canonical-host, window, and shadow bindings before the single-host
matrix exception is granted. Formal publication repeats the same shared
validation before deriving any durable cursor transaction. The history
snapshot's cursor rows are the only authority for every `before` cursor; each
proposal is derived from terminal source cells. The formal durable state must
then equal those proposed rows plus the exact source snapshot refs,
`backfill_of`, episode-head root, and complete episode-head list. A production
backfill must consume the durable backlog and matching controlled-gap/head-set
commitments; a shadow successor may derive only its authenticated run-local
equivalent.

Only an ordinary Daily run with `allow_partial=true` may publish source gaps.
Its gap-host set must exactly equal its authenticated `controlled_holdouts` set,
every source kind for each held host must be a gap with the receipt's exact
transport references and reason, and every referenced transport receipt body
must independently authenticate against the checkpoint source receipt inventory.
Comparing only receipt references is insufficient. At least one other host must
remain complete. Weekly gaps, mixed gap/complete cells, cross-host receipts, and
a complete run carrying a stale holdout are rejected. An ordinary run cannot
clear a non-null durable backlog; only the matching backfill lineage can do so.
For shadow backfill, every checkpoint read revalidates the closed successor HMAC
and its exact partial-run, gap, host, history, provenance, window, revision,
coverage, cleanup, and export-digest bindings.

A publication retry validates this authenticated run authority and its
persistent claim before adapter recovery. It re-inventories every present local
bundle and requires exact identity, content, and access-policy equality with the
stored inventory before any adapter side effect. Direct abort recovery repeats
the claim validation before release. While target CAS has not occurred, the
retry also re-derives the complete journal plan from the current retained
inventory, history base, provider cache, cursor vector, and episode update. Once
the exact target CAS is reachable, recovery is authorized by the bound adapter
attempt and signed durable-history projection; the expected history advance and
a legally collected, exactly absent local bundle are not treated as
prepublication inputs.

The sole exception is a direct shadow successor derived from a completed Daily
partial by `--shadow-successor-of`. Its authenticated shadow gap derives an
exact run-local backlog reference without changing durable history. This
exception is unavailable to production, cannot enter `finalize`, and cannot
advance or suppress production host coverage.

Extractor control metadata binds each goal, workstream, evidence, and span
reference to one logical turn. A turn cannot borrow another turn's references
from a shard-wide union. After validation, the coordinator resolves goal and
workstream continuity in canonical session order from the closed
`goal_change`/`workstream_change` decisions. Backfill predecessor matching
requires a stable turn or goal anchor; a session-default workstream alone is
never a semantic predecessor.

A successor review receives payload material for every member turn, including
all turns inherited from its prior durable head. If any prior validated payload
cannot be restored from the current sealed extraction material, the coordinator
records `episode_turn_material_gap` with an exact missing-ref commitment and
blocks before creating a partial review input. A prior turn reference without
its validated material is never treated as coverage.

Oversized episode reviews use validated hierarchical children. Every parent
copies an exact recursive commitment containing immediate child-result hashes,
leaf-result count, per-field source-item counts, and a canonical tree hash. The
visible parent lists are bounded verbatim multisets of child items: they may
compact an otherwise unrepresentable union, but may not invent, alter, or copy an
item more times than the children supplied. Risk flags remain the exact union;
escalation/conflict decisions remain recursive ORs; confidence cannot exceed the
lowest child confidence. Omission is therefore explicit in the commitment rather
than silently reported as complete coverage.

Episode adjudication additionally carries both validated candidate results and
an ordered `candidate_item_decisions` trace. Exactly twelve compact rows cover
the six item fields for the primary and secondary candidates. Each row binds the
candidate hash and reviewer slot, while `decision_codes` supplies one closed code
per source item in original order for selected, duplicate-merged, or explicitly
rejected disposition. Downstream topic input
embeds and revalidates that complete candidate context; an adjudicator cannot
silently erase candidate-unique content.

## Automation Cutover Authority

`automation_cutover_snapshot_v2` is captured before the capability call and
identity-authenticates the exact stable-ID inventory, canonical record paths,
and either the absent state or verified existing record digest.
`automation_update_result_v2` then contains exactly the available
`automation_update` capability, that snapshot ref, and one successful
`register` or `update` operation for each stable ID:
`daily-session-retrospective` and `weekly-session-retrospective`. Registration
is admissible only for a snapshot-proven absent ID and requires a null previous
digest. Update is admissible only for a snapshot-proven existing ID and requires
its exact distinct previous digest. The internal authority derives the result
commitment after validating installed bytes. Missing capability, opaque result
refs, stale or forged pre-state, and every extra or unrelated ID fail closed.

`automation_cutover_record_v2` binds the owner identity, installed release
commit, exact installed v2 CLI path, operation lineage, and current SHA-256 plus
identity-derived reference for both fixed `automation.toml` paths. The engine
reads those records with bounded no-follow I/O and requires owner ownership,
non-group-writable paths, and the exact closed TOML document with only
`version`, `id`, `kind`, `name`, `prompt`, `status`, and `rrule`. The active
mode-specific prompt must be byte-equal to the canonical
`build_production_prompt` output: one `shlex.join` command using the exact
authenticated Python, `-I -B -S`, installed CLI, `start --mode`, and one
absolute canonical `--publisher-gpg-program`, wrapped by the fixed production
sentence. Prefixes, suffixes, control characters, unknown fields or tables,
boolean versions, reference-only text, v1 paths, shadow, holdout, and partial
production controls all fail closed. The production marker embeds the complete
authenticated cutover record and must include its release commit.

## Publication Signing Isolation

Every publisher-key inventory, sign/verify canary, signed commit, and durable
history verification uses an owner-only configuration-free keyring snapshot.
The source publisher home is descriptor-bound, and only a bounded stable
`pubring.kbx`, optional `trustdb.gpg`, and 1-16 canonical owner-`0600`
private-key files are copied. GPG configuration files, agent sockets, and all
other source-home entries are excluded. The short fixed snapshot root is outside
retrospective source trees, snapshot paths are unpredictable, and successful
cleanup requires Assuan agent shutdown under one monotonic deadline spanning
connect, greeting, `KILLAGENT`, response, and `S.*` disappearance. After copy,
the private-key inventory is enumerated again and every admitted private-key
object is read and compared again through its held descriptor. Any source-
binding, inventory, copied-byte, access-policy, agent, or cleanup uncertainty
fails closed.
Interrupted GPG lock cleanup is a separate closed exception: only strict
`.#lk...` names and the fixed agent-spawn sentinel are eligible, every object
must be a bounded owner-controlled regular file without an ACL, and its link
count must equal the complete descriptor-bound in-snapshot alias set. External
hard links, malformed locks, identity drift, or deletion uncertainty retain the
snapshot.
Within one coordinator process, repeated readiness views may reuse a successful
parsed publisher identity only under an exact cache key containing the
configuration-free selected-key commitment, canonical source path, expected
fingerprint and UID, and GPG executable authority digest. Each lookup rebuilds
one descriptor-held configuration-free snapshot receipt and uses that same
receipt for both the cache commitment and inventory validation; an independently
rebuilt second snapshot cannot satisfy the lookup. Failure results, startup
canaries, signing, and verification are never cache-authoritative.

Publication uses a separate descriptor-bound temporary Git index and forces
`core.splitIndex=false` for every publication Git command. A repository that
enables split-index therefore cannot create or reuse `sharedindex.*` as part of
the publication transaction.

## Retained Bundle

Every published run contains exactly:

```text
manifest.json
coverage.json
episodes.jsonl
turn_findings.jsonl
topics.jsonl
trend_report.json
report.md
summary.json
```

The retained bundle contains summaries, findings, strengths, reviewed prompt
rewrites, typed metrics, confidence, opaque references, and pre-tree provenance
only. Episode rows retain the exact revision ordinal, superseded revision,
review-result hash, reviewer, and attempt lineage. High-impact turn rows retain
the validated `problem_statement`, `cause`, `rewritten_prompt`,
`expected_effect`, `confidence`, and opaque evidence references. These four
reviewed text fields are the only retained prose exception and remain subject to
ASCII, length, locator, credential, control-character, and Unicode
default-ignorable scans. The bundle never contains raw or
quoted original prompts, excerpts, tool output, source paths, raw IDs, internal
URLs, bare FQDNs, secrets, credentials, customer data, personal data, or
proprietary code.

Retained prose is also content-validated, not merely field-name validated.
Original/verbatim prompt markers, tool or command output markers, role
transcripts, direct source-request shapes, code/shell/key-value payloads, UUIDs,
opaque internal IDs, and exact source-derived prompt/tool payload overlap are
rejected. A useful generalized `rewritten_prompt` remains admissible when it
does not reproduce those source forms.

`manifest.json` retains the complete non-sensitive execution contract: actual
model/provider/closed parameters, prompt digest/version, schema and transport
bindings, component versions, coordinator-runtime authority, configuration
root, coordinator-implementation source authority, and every agent job's
declared result contract, result, retry, reviewer, and
issued/claimed/completed timing provenance. Runtime authority contains only a
digest of the canonical executable binding plus a digest over executable
identity, bytes, and ancestor access policy; it never retains the local path.
Both digests are included in the configuration root and are recomputed before
any resumed command may consume or advance a checkpoint. An opaque
configuration commitment cannot replace these fields. Implementation authority
uses a schema-v2 startup receipt that binds the closed coordinator Python
inventory, captured exact source bytes, and file and ancestor access policy.
Resumed commands validate that immutable receipt before comparing it with run
provenance; they execute the captured bytes rather than rereading a live source
path. Local source paths are not retained.
Agent execution provenance includes the exact deterministic task-cache
hit/miss/reuse conservation alongside every job, result, retry, reviewer, and
issued/claimed/completed timestamp.

Trend rates use all meaningful turns or episodes as denominators and are reported
per 100. Incompatible model/policy/configuration eras are rendered separately and
never compared as direct improvement or regression.

Topic-reducer output uses a closed result schema. Its semantic recurrence,
guidance, prompt-rewrite, skill-candidate, and open-work records are
agent-produced, evidence-bound outputs; the deterministic fields prove exact
episode/session membership, child lineage, and cross-session measures. Global
synthesis consumes those validated aggregations rather than a byte-equal copy
of reducer input.

Topic inputs are partitioned from bounded episode reviews before the 64 KiB
result-contract validator is called. The durable partition index commits every
expected episode revision and leaf input hash; reducers then combine only
validated bounded children through the hierarchy. Each topic parent uses the
same recursive child-tree commitment and emits only a bounded multiset subset of
child records, while retaining a non-empty episode/revision/session lineage and
the exact child risk union. The coordinator never first constructs or validates
one oversized topic input.

Leaf topic recurrences bind revision-level provenance, not just topic-wide
membership. The recurrence must name exactly the sessions owning its selected
episode revisions; every selected revision must contain the same signal type and
kind and must support at least one cited evidence reference. Hierarchical parents
can retain only recurrence records already validated by a child.

Global synthesis requires a bijection between durable topic-input roots and
accepted final topic tasks: every expected root appears exactly once, with no
duplicate or extra root, before any dictionary reconstruction. Hash-key
overwrite cannot collapse duplicate results. Each synthesis task carries one
compact `topic_result_commitment` over the sorted canonical result-hash
multiset; every validated result hash already commits its bound topic root. The
commitment binds the exact item count and SHA-256 digest without imposing a
128-root representation ceiling. A leaf commitment may cover only that leaf's
assigned subset; recursive parent lineage authenticates each child commitment,
and only the final commitment is compared with the complete accepted topic
inventory.

Global synthesis represents each exact canonical topic-signal union with a
SHA-256 commitment and count plus at most 64 deterministic exemplars, selected
high-severity-first and then by canonical order. Every hierarchy level derives
the same fields from its authenticated subtree; a model cannot reconstruct or
replace them after compaction. The signal commitments and compact topic-result
commitment prevent omitted non-exemplar signals or topic roots from
disappearing. Cross-source preservation of high-severity independent-review
signals is checked only at the final root, after the complete topic and review
subtrees have rejoined; a legal intermediate leaf is not required to contain
its sibling leaf's support. Retained compilation verifies the finding
commitment against topic rows and writes the complete canonical
finding/evidence union to `summary.json`, not just the bounded exemplars.

The coordinator separately derives every high-impact prompt rewrite from the
accepted resolved episode reviews. Each synthesis subtree receives a complete
count/hash commitment and at most 20 deterministic exemplars; the model must
copy both exactly. Retained compilation rebuilds the same complete source from
`turn_findings.jsonl`, verifies the commitment, and treats synthesis rewrites as
bounded exemplars rather than requiring a representation that cannot exceed 20
items.

Durable episode, topic, and global records use closed per-finding objects. Every
object preserves the exact finding kind, confidence, optional severity, and
non-empty opaque `evidence_refs` that justified that finding. Topic findings are
the exact canonical union of their member episode findings, and global findings
are the exact canonical union of the retained topic findings. Counts cannot
replace these records, and evidence references cannot be dropped or rewritten
during reduction. The existing privacy rules still reject prose, raw content,
paths, identifiers, URLs, secrets, and any non-opaque evidence reference.

## Calibration And Durable Authority

Calibration receipts bind the exact corpus commitment and configuration root.
Precision, recall, and F1 use bounded integer numerator/denominator pairs;
missing denominators fail. The signed private Git publication chain is durable
authority. The owner-local HMAC production marker records completed cutover, and
the provider cache is initialized only by a request that proves
`expected_revision=0` exactly, independently of the current durable-history
projection revision, and then derived from each newly validated history commit.

Production cutover binds exactly `daily-session-retrospective` and
`weekly-session-retrospective` to the installed v2 CLI path. The internal
authority API admits either a verified update of an existing record or an exact
first registration of those stable IDs. Unrelated IDs, unavailable
`automation_update`, a reference-only template, or a different executable path
cannot establish production authority.

Episode heads form an append-only revision chain. A successor advances the
ordinal by exactly one, names the exact predecessor revision, and preserves the
predecessor's `session_ref` byte for byte. Session reassignment requires a new
episode identity and cannot be hidden in a superseding revision.

## Durable Guidance Threshold

AGENTS.md, Skill, and automation candidates require evidence from at least three
episodes across at least two sessions. One independently reviewed high-severity
safety issue may qualify as an exception. Every candidate carries a closed list
of exact `{episode_ref, session_ref}` pairs. Each pair must match validated topic
lineage and retained episode lineage; unrelated episodes or a real episode paired
with the wrong session fail closed.
