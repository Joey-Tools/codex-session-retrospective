# Session Retrospective v2 Engine Architecture

## Coordinator model

The v2 engine is a deterministic coordinator. `RetrospectiveOrchestrator` owns
the authenticated checkpoint store, identity, run directory, clock, and shard
limits. Its capability classes are stateless and have no constructors. They
operate on that single coordinator context and do not import one another:

| Module | Responsibility |
| --- | --- |
| `session_retrospective_v2.py` | Minimal installed descriptor launcher and bootstrap trust root |
| `session_retrospective_v2_runtime.py` | Descriptor-captured coordinator runtime and startup source authority |
| `cli.py` | Authenticated entrypoint-loaded CLI implementation and stable command API |
| `orchestrator.py` | Stable facade, coordinator context, and CLI-compatible exports |
| `orchestrator_support.py` | Source-frame consumption, shared contracts, and runtime readiness |
| `orchestrator_state.py` | Authenticated checkpoint identity and state access primitives |
| `run_state_contracts.py` | Closed run-authority schemas, host references, and common guards |
| `run_state_cursors.py` | History-bound cursor starts and terminal-source cursor derivation |
| `run_state_holdouts.py` | Formal Daily holdout and shadow-successor authorization |
| `run_state_lineage.py` | Controlled-gap, backfill, backlog, and episode-head lineage validation |
| `run_state_authority.py` | Shared formal source-matrix, cursor, lineage, and durable-state composition |
| `orchestrator_projection.py` | Read-only status, metrics, references, and next actions |
| `orchestrator_jobs.py` | Agent attempt, claim, sink, and envelope lifecycle |
| `orchestrator_reduction.py` | Catalog materialization and episode/topic/synthesis hierarchies |
| `synthesis_lineage.py` | Authenticated synthesis-subtree commitments and compact signal projection |
| `orchestrator_history.py` | Result validation and retained history projection |
| `orchestrator_source.py` | Source transport admission and leased agent result handling |
| `orchestrator_lifecycle.py` | Run creation, publication claims, retention, and raw cleanup |
| `source_capacity.py` | Run-global source, sidecar, and cleanup-capacity accounting |
| `source_acceptance.py` | Input normalization and compact accepted-payload accounting |
| `source_spool.py` | Lease-bound spool locking, exact pre-write limits, and crash recovery |
| `agent_capacity.py` | Extractor/downstream task partitions and cache-miss reservations |
| `agent_claim_projection.py` | Worst-case final claim metadata and exact envelope-size projection |
| `agent_result_contracts.py` | Complete closed JSON Schemas supplied to native agent jobs |
| `agent_checkpoint_capacity.py` | Claim/result checkpoint-reserve rollback transactions |
| `agent_task_inputs.py` | Authenticated immutable task-input sidecars and checkpoint summaries |
| `agent_results.py` | Authenticated accepted-result sidecars and checkpoint-coupled staging |
| `agent_raw_artifacts.py` | Sealed raw-artifact projection and envelope loading |
| `extracted_turns.py` | Authenticated derived-turn sidecar preparation and loading |
| `implementation_authority.py` | Coordinator startup-receipt and fallback source authority validation |
| `raw_shard_staging.py` | Two-pass source-payload streaming and raw-shard rollback ownership |
| `source_staging.py` | Preallocated receipt ledger and atomic final-file staging |
| `orchestrator_scheduler.py` | Stage transitions, task creation, and bounded envelope scheduling |

Publication uses an explicit side-effect boundary:

| Module | Responsibility |
| --- | --- |
| `finalize.py` | Stable publication facade |
| `publication_transaction.py` | Durable publication state machine and recovery |
| `publication_git.py` | Constrained local Git provider facade and effect ordering |
| `publication_git_capacity.py` | Request-bound capacity ledger and legacy migration |
| `publication_git_storage.py` | Staging, retention-sidecar, and cleanup ownership |
| `publication_git_commits.py` | Signed Git object, reachability, and ref operations |
| `publication_claims.py` | Authenticated checkpoint-claim context and replay validation |
| `retained_export_coordination.py` | Checkpoint/sidecar identity, locking, expiry, and GC classification |
| `retained_export_binding.py` | Exact publication-plan binding through the narrow sidecar protocol |
| `publication_state.py` | Durable publication state and transition validation |
| `publication_contracts.py` | Side-effect protocols and injected adapter contracts |
| `publication_support.py` | Immutable contracts, anchored I/O, and pure validation |
| `executable_authority.py` | Shared executable path, content, and access-policy binding |
| `git_safety.py` | Shared local-only Git environment, repository admission, and revalidation |

`retained_inputs.py` owns authenticated export-input sidecars, while
`source_overlap.py` owns strict streaming JSON token decoding, deterministic
control-field classification, prose normalization, bounded overlap windows, and
short source-token matching. `privacy_locators.py` owns working-zone bare-host
and effective IPv4/IPv6 detection. Working-zone redaction, retained safe
strings, reviewed prose, and final report validation consume that same locator
policy. It also owns the closed control/default-ignorable character policy used
by agent-envelope validation, source-overlap normalization, retained safe
strings, reviewed prose, and final report validation. Protocol locators accept
every syntactically legal scheme length and
rely on the result field's existing character ceiling rather than a privacy-only
scheme cap. Their shared left boundary excludes every legal ASCII scheme
character and every Unicode alphanumeric character instead of relying on a
case-folded word boundary. A locator after `_` is detected, while the scanner
cannot restart inside a longer ASCII scheme or an invalid Unicode-prefixed word.
Empty authority remains a locator and is rejected conservatively. The retained
boundary still applies its stricter field and prose grammar.
Keeping these deterministic policies outside the coordinator capabilities
prevents lifecycle and result-validation modules from growing a second copy of
either state machine.

Remote helper execution has two separate owners. Parent-only
`transport_remote_snapshot.py` materializes the installed
`$remote-host-context` helper into the run-owned content-addressed snapshot
cache. Worker-visible `transport_snapshot.py` contains only deterministic path,
commitment, and isolated bootstrap logic for that external helper; the worker
manifest does not expose the parent materializer.
The installed helper selector and the sanitized relay environment use one
account-database binding. They resolve the current UID through `getpwuid`,
canonicalize the declared absolute home, and derive both the helper path and
child `HOME` from that result. Caller `HOME` therefore cannot redirect helper
selection before the descriptor-authenticated snapshot is created.
`transport_remote_account.py` serializes that account plus the home object's
identity and access-policy receipt into one canonical lease argument. The
worker revalidates the same account record, canonical home object, owner/mode/
group policy, masked mutation flags, and ACL digest immediately before relay
launch, then passes that
snapshot explicitly to the sanitized environment builder. This closes the
scheduler-to-worker account split without treating timestamps as identity or
policy evidence.
The bootstrap keeps the helper descriptor open through its bounded read and
revalidates object identity plus owner/mode/link/size policy before executing
the retained exact bytes. The same parent-only owner performs the legacy CLI
snapshot and relay transaction; worker-reachable modules cannot materialize the
live installed helper.
The authenticated helper snapshot remains the semantic code authority; the
bootstrap is not an arbitrary-Python sandbox. It binds the exact static `HOSTS`
data again at runtime, installs immutable copies for ordinary execution, and
rechecks the binding on every `main` return or `main` `SystemExit` path. One
top-level immutable `SESSION_RETROSPECTIVE_COMMANDS` manifest is the helper's
semantic capability contract and is also the canonical source used by its
parser registration. It provides a closed preflight for `session-shards` and
`source-transport`, so an older helper produces an explicit compatibility gap
before transport starts.
Both source-program bootstraps use no-follow, nonblocking descriptor opens and
compare the opened object with the named object before and after the bounded
read. They require a stable regular-file identity, owner/group/mode, single-link
state, and exact size; the owner-private snapshots additionally require mode
`0600`. FIFO, leaf-symlink, hardlink, access-policy drift, and same-path
replacement therefore fail before compilation or execution. The Python runtime
uses the same bounded reader with a root-or-current-user, non-writable policy.
The scheduler resolves that authenticated runtime to its canonical physical
path and records the complete argv in the lease. Status re-derives the exact
program commitment before projecting any command, and native source acceptance
reuses the same canonical argv0 rather than ambient `sys.executable`. Replacing
an interpreter alias after lease creation therefore cannot redirect execution.
These are point-in-time identity, content, and access-policy checks; they do not
claim to defeat an actively malicious same-UID replacement of the canonical
target after the final validation.
`transport_remote.py` launches the retained snapshot, never the live installed
path. Parent-only `transport_remote_snapshot.py` owns the backward-compatible
CLI relay: it first copies the live installed helper to an owner-private `0600`
content snapshot and passes the raw snapshot digest; the distinct component
commitment remains source provenance. This preserves the worker manifest's
no-parent-write boundary while closing the
commitment-to-execution replacement window. The parent derives the
live-helper source commitment from the same descriptor-bound read used to create
the snapshot and requires it to equal the run's frozen transport provenance, so
one run cannot mix helper versions across source leases.

The public coordinator script is a stdlib-only descriptor launcher and declared
bootstrap trust root. Before any engine code executes, it opens the separate
runtime without following links, validates the owner-controlled ancestor and
file access policy, double-reads one held regular-file descriptor, and
`compile`/`exec`s those exact bytes. The runtime receives that still-held
descriptor and source snapshot, revalidates its named object, identity, content,
and access policy, and uses that same snapshot for its startup receipt. A
replace-after-load race therefore cannot make old executing runtime code attest
new pathname bytes. Direct execution of the runtime file is rejected. The
launcher itself is intentionally the outer installed trust root bound by the
cutover's installed source identity; the runtime receipt does not overclaim that
Python descriptor-binds bytes already loaded for the launcher.

The captured runtime then descriptor-opens the complete generated package
manifest and root CLI helpers; rejects unlisted import candidates and bytecode,
native, cache, symlink, or same-name-package substitutes; and captures stable
exact bytes plus object-identity and access-policy evidence for every retained
source file. Timestamp changes are not mutation evidence. A closed meta-path
finder executes only those captured bytes and raises for every unknown
`retrospective_v2.*` name; the live scripts directory is never added to
`sys.path`. `implementation_authority.py` validates the schema-v2 startup receipt
before command parsing. After adding or removing a production package module,
update the generated block in the runtime with
`scripts/generate_retrospective_v2_bootstrap_manifest.py --write`; its default
mode checks deterministically for a stale manifest.

The transport worker imports only modules present in the authenticated program
manifest. Its snapshot finder is the sole authority for the package namespace;
the live worker root is never placed on `sys.path`, and a missing manifest
module cannot fall through to repository or installed-package bytes. Discovered
source locators must satisfy the closed grammar and be UTF-8 encodable. A
filesystem name that cannot be represented becomes an explicit
`source_locator_unrepresentable` gap rather than crashing discovery or being
silently omitted. Discovered source candidates must be single-link regular
files; a multi-link object becomes an explicit
`source_hardlink_not_supported` gap before any occurrence identity is issued.
Source rereads compare the selected protected properties: object identity,
normalized descriptor ACL policy, selected BSD access-policy flags, and the
exact scanned byte-range digest. The candidate token and every scan proof
sample bind the link count, ACL policy, and selected BSD flags, and every scan
observation must remain single-link. A post-discovery hardlink, grant, revoke,
or policy-flag change during scanning therefore produces a source-stability gap.
Timestamp-only churn is benign, while content, identity, or access-policy drift
remains explicit.

Catalog unit identity binds the source kind of each observation. Physical and
canonical rollout-record identities intentionally remain independent of the
active-versus-archived locator so an ordinary archive rename can still be
deduplicated after both observations are admitted. This separation prevents an
active observation and a later archived observation of the same file from
colliding before catalog freeze while preserving their physical equivalence.

The remote relay, publication/history subprocess owners, and publisher canary
keep their leaders unreaped until post-output work is terminal. They share one
strict closure owner, signal each task-owned process group while the PID/PGID is
still pinned, and retire signal authority before any operation that may reap.
`ESRCH` is the only ordinary signal absence; every other signal failure is
explicit. Darwin may return `EPERM` when the unreaped zombie is the group's only
remaining member. After the leader is reaped, `EPERM` from the non-signaling
probe remains unproven and is retried only within the original cleanup deadline;
only a later `ESRCH` proves closure. A still-present or unverifiable group or an
incomplete leader reap is an explicit cleanup failure, and no later cleanup path
may signal the now-reusable PGID. Selector construction, selector close, and
stream close all run inside the process owner's cleanup boundary; every local
resource close is attempted, but none can bypass group closure. Cleanup failure
alongside an active primary is carried through bounded exception wrappers and
becomes a non-retryable machine-visible CLI result rather than an invisible note.
Availability, readiness, canary, and remote-gap fallbacks must rethrow that
security failure instead of converting it to an ordinary false or gap result.
The publisher canary, legacy remote-helper snapshot, remote transport output
spool, session-shards verification/record spools, and publication Git index use
separate fixed owner-only roots beneath
`/tmp/codex-session-retrospective-<uid>`. A shared temporary-directory authority
rejects both lexical and resolved overlap with the canonical local Codex source,
opens the fixed root through the secure directory-chain policy, creates the
unguessable child through the held root descriptor, and holds both root and
child descriptors until bounded inventory-based cleanup. It validates the
named root, named child, descriptor identities, access policy, and actual
resolved location before publishing the path, around path-consuming work, and
before cleanup. A proved mismatch retains the unproven object instead of
removing a replacement. These checks detect replacement but do not claim to
defeat an actively malicious same-UID writer in the final revalidation-to-use
syscall window; that writer remains part of the host trust boundary.
Sensitive fixed roots that permit crash recovery keep one owner-only persistent
recovery lock. That root lock covers bounded inventory, child creation, and the
final deletion boundary; it is not held while an operation uses its child. Each
active GPG snapshot instead holds an owner-only `.active.lock` lease created
atomically through the bound child descriptor. Startup accepts only the exact
`g-` prefix plus a 256-bit lowercase hexadecimal suffix, rebinds every child,
and probes that child's exact lease while the root lock is held. A validated busy
lease proves only that the child is active and is retained; an absent or
successfully locked lease is stale and may be recovered. Before normal cleanup,
the owner reacquires the root lock, revalidates and releases its lease, and then
performs bounded descriptor-owned tree removal. A process crash releases the
lease without deleting its child, so the next startup can stop the exact bound
GPG agent and recover the stale tree. An unknown root entry, replacement,
unreadable lease, access-policy mismatch, or cleanup uncertainty blocks the new
operation and retains the unproved object. These are cooperative ownership
guarantees; an actively malicious same-UID process remains part of the host trust
boundary. If an operation and sensitive temporary cleanup both fail, the outer
primary carries a content-free cleanup marker so the CLI cannot classify the
result as retryable. Specialized cleanup uncertainty also marks the bound child
for recovery before control returns to the generic temporary-directory context.
That context closes its descriptors but does not recursively remove the retained
tree; only a later root-lock holder may recover it through the bounded inventory.
Recovery never treats an absent socket or a refused connection as durable
listener-absence evidence. A stale snapshot can be removed only after a bounded
Assuan shutdown removes every bound socket, or after the normal cleanup owner
has persisted an exact owner-only `.agent-cleanup.proved` marker after agent,
socket, and lock cleanup. The marker is read twice through the bound child
descriptor with exact content, identity, link-count, mode, and ACL validation.
Missing, malformed, replaced, unreadable, or policy-drifted proof retains the
complete snapshot and blocks recovery. A same-UID process remains part of the
documented host trust boundary.

The canary child receives `TEMP`, `TMP`, and `TMPDIR` bound to the exact
descriptor-validated disposable workspace through the otherwise closed
subprocess environment. The source-transport bootstrap cache is fixed below
`/tmp/codex-session-retrospective-<uid>/source-transport-snapshot`; its module
does not consult ambient temporary-directory variables during import. The remote
snapshot, transport spools, and publication index likewise ignore ambient
temporary-directory selection. Host variables therefore cannot redirect any of
these writes into session or archive sources.
The secure-I/O
capability probe that can run before temporary-root creation also uses the fixed
`/tmp` parent rather than ambient temporary-directory selection.

Source scheduling prepares the transport-program snapshot, remote-helper
snapshot, and bound empty output together with the candidate checkpoint. Exact
checkpoint capacity is proved before any file is materialized. A successful
commit records the run-relative output binding; status projection only
authenticates the existing binding and program snapshot with recovery disabled;
it never creates raw state. A stale snapshot therefore cannot recreate a path
after retention cleanup has claimed and removed the raw tree.

Source acceptance has a separate bounded staging boundary. Before transport
iteration, the coordinator proves the candidate batch fits run-global source
capacity and conservatively reserves the full 64 MiB acceptance-sidecar ceiling.
The final checkpoint transaction rechecks the current state with the exact
prepared sidecar bytes. Segmented transport then keeps at most one bounded raw
record in memory
while appending accepted bytes to one deterministic lease-derived, owner-only,
descriptor-held spool. A persistent owner-only lock serializes cooperating
recovery; after the lock is acquired, a retry authenticates and removes only the
same deterministic orphan. Exact record and byte caps are checked before each
write. Compact per-record descriptors drive transcript validation and the
acceptance digest. A preallocated receipt ledger exists before any final file is
created, so rollback authority cannot be lost to a post-create collection
allocation. Replay, failure, rollback, and success all discard the exact spool.

Retained export uses two independently 250-line-bounded CLI support modules: one
owns the transaction and one owns the closed reservation, claim, and result
schemas. The transaction canonicalizes the ignored destination, rejects every
current-run cleanup root, occupies the legacy descriptor path with a no-replace
reservation, and then establishes the immutable destination claim before
artifact assembly or output writes. An exact legacy final descriptor remains
authoritative; a legacy claim that was already in flight may become the effective
destination without allowing two completed results. Final result persistence
reauthenticates the claim and any legacy descriptor before binding the bundle
digest and retention deadline.

Publication cleanup classifies the retained bundle and retention sidecar while
holding the export anchor lock. Two absent objects are an idempotent collected
state; exactly one present object is a conflict. The lifecycle release must
complete before the provider persists its abort and cleanup receipt, so a
one-sided or unreadable retained state cannot authorize reservation release.
Ordinary export checkpoints also persist the canonical staging locator. Expiry
GC acquires that exact bundle lock before it claims raw cleanup, then compares
the authenticated checkpoint and validated sidecar. A publication bootstrap
uses the same lock and rechecks the checkpoint immediately before binding. The
winner is therefore explicit: a bound sidecar blocks raw cleanup, while an
already persisted cleanup claim blocks a waiting bind. A new publication claim
requires this bundle-bound bootstrap; only an existing exact claim may replay
without supplying the bundle again.

The transport program commitment includes every runtime module above. Adding a
module without adding it to the closed allowlist fails source transport.

Runtime source matrices, run-level source capacity, and durable shadow/production
authority derive from one canonical five-host role inventory: `local`,
`BL-mac-mini-m4-hoteng`, `miku-bot-dev`, `hoteng-srv-01`, and
`codex-hoteng-srv-01`. No independent production-host subset may authorize a
complete run or cursor advancement.
The closed five-module run-state authority slice validates the authenticated
checkpoint at both the orchestrator state boundary and the formal publication
boundary. It binds each cursor start to the signed history snapshot, derives
each cursor proposal from terminal source cells, and requires the durable cursor
rows, source snapshot refs, episode-head root/list, and `backfill_of` value to be
the exact checkpoint projection. A single-host Daily backfill is accepted only
when its controlled-gap receipt authenticates and binds the partial run,
canonical host/ref, exact window, backlog, head-set commitments, and shadow mode;
checkpoint HMAC validity or a non-null `backfill_of` field alone is insufficient.
Formal source gaps additionally require an exact authenticated Daily partial
holdout set and reauthenticate each referenced transport receipt body against
the checkpoint source receipts; reference equality alone is not authority.
Weekly gaps, mixed gap cells, cross-host receipts, and ordinary runs that would
clear an existing backlog are rejected. Shadow backfills revalidate the
completed-partial successor authorization and all of its history, provenance,
window, coverage, cleanup, and bundle bindings on every checkpoint read.

Opening a publication journal validates that authenticated checkpoint and its
persistent claim before any adapter recovery. It rebuilds the exact inventory of
every present retained bundle before adapter side effects; only the durable
post-CAS recovery path may continue when that bundle is exactly absent. Direct
abort recovery independently repeats the claim check before adapter release.
Before target CAS, every forward transition additionally re-derives the journal
plan from the current retained bundle, signed history base, provider cache,
cursor vector, and episode update. After an exact target CAS is already
reachable, recovery instead binds the adapter attempt and signed durable
history; it neither mistakes the expected history advance for drift nor requires
an already collected local bundle.

History readiness and formal publication use the same local-repository
admission receipt. It binds owner-controlled real ancestry for the worktree,
Git directory, common directory, and closed object store; rejects alternates,
grafts, shallow repositories, promisor/partial-clone configuration, bounded
descriptor-relative `objects/pack/*.promisor` markers, include directives,
worktree configuration, and an enabled `extensions.worktreeConfig`; and binds
the exact owner-controlled common-config bytes. Failure to complete a stable,
bounded pack-directory scan is distinct from proof of a marker but still fails
closed because marker absence remains unproved. Pack-directory entry names must
be portable ASCII, and the marker suffix comparison is ASCII
case-insensitive; this avoids claiming that Unicode normalization approximates
the host filesystem's native alias rules. Each later Git command
holds all four admitted directory descriptors, launches from the held worktree
descriptor with only relative repository discovery, and revalidates directory
identity, access policy, config content, and forbidden metadata before and after
the subprocess. The isolated Python trampoline that performs descriptor-relative
`fchdir` is itself resolved through the shared executable authority, contributes
its physical path, content, and access-policy receipt, and is revalidated around
every Git or GPG child launch. Close failures fail the otherwise-successful
command and remain secondary evidence when another failure is already primary.
These are point-in-time checks: they detect path replacement and stable drift but
do not claim to exclude an actively malicious same-UID ABA after the final
pre-launch check. A repository that finalize would reject is therefore blocked
by doctor/start before an expensive retrospective run begins.

The publisher GPG executable uses the same authority model. `doctor` and
`start` require its absolute configured path; start persists a digest over the
path-object identities, executable bytes, and ancestor access policies in the
authenticated run specification. Every later signed-history read and
publication phase supplies and rechecks that exact path/digest. `finalize` has
no caller-selected signer override. Timestamp-only changes are benign because
they are not part of the protected authority receipt.

Automation cutover receives that executable path as an independent parent
authority input. The cutover HMAC commits the exact canonical path in both the
top-level record and each automation-record reference; prompt text cannot select
or redefine the expected signer authority.

Keyring inventory, sign/verify canaries, Git signing, and Git verification all
place `--no-options` before every other GPG argument. Git reaches GPG only
through the fixed executable `scripts/retrospective_v2_gpg_no_options`; the
launcher bytes, executable identity, and access policy are authenticated around
each signing or verification subprocess, while the selected GPG executable is
passed through one closed environment key.

Every such operation first opens the configured publisher home through an
owner-only descriptor binding and copies only the bounded `pubring.kbx`,
optional `trustdb.gpg`, and closed `private-keys-v1.d/<keygrip>.key`
inventory into an unpredictable owner-only snapshot under the fixed short
socket-safe root. Each selected source file must remain a single regular
owner-controlled object with stable bytes and access policy while copied. The
private-key directory is enumerated again after copying, and every selected
private-key object is read and compared again through its held descriptor, so
inventory churn or a same-object content change cannot be hidden by the first
copy pass.
`common.conf`, `gpg.conf`, `gpg-agent.conf`, source sockets, and every
other source-home entry are excluded rather than interpreted. Snapshot
configuration therefore cannot redirect output, run helpers, or alter signing
and verification behavior.

The snapshot owner shuts down any spawned agent through a bounded authenticated
Assuan exchange on the owner-only primary socket; it does not add `gpgconf` or
another ambient executable to the trust root. The exact socket allowlist is the
four `S.gpg-agent*` endpoints plus `S.scdaemon`. When `S.scdaemon` exists, the
owner first requires `SCD KILLSCD` to succeed, then sends `KILLAGENT`. One
monotonic deadline covers connect, greeting, both commands and responses, and
socket disappearance; a peer cannot multiply the bound by delivering one byte
per read. Top-level inventory is capped while `scandir` is consumed. A known
socket that appears or changes identity during shutdown, any unknown `S.*`
entry, or any socket that survives the deadline fails closed.

A process crash may leave both selected key bytes and live GPG processes in the
fixed snapshot root. The next snapshot lifecycle holds the persistent recovery
lock, binds every exact `g-<64 lowercase hex>` child, performs the same bounded
agent/scdaemon shutdown, removes only strictly validated GPG lock shapes and
stable known sockets, and then applies descriptor-bound bounded tree cleanup.
An absent listener permits removal only after each known socket has stable
identity and owner-only policy. Agent, socket, source binding, or cleanup
uncertainty blocks creation of the next snapshot; it never silently abandons
private key material under `/tmp`.
If interruption leaves GPG's documented lock/sentinel hard-link shape, cleanup
accepts only strict bounded lock names and proves regular-file identity, owner,
non-writable access policy, ACL absence, and that every inode link is present
inside the bound snapshot. It then unlinks each name relative to the held
snapshot descriptor while rechecking the decreasing link count. A malformed
name, external link, replacement, or incomplete proof retains the snapshot
rather than generalizing deletion authority.

Repeated readiness projections use a bounded process-local cache only after
opening one configuration-free keyring snapshot receipt. The same descriptor-
held receipt supplies both the cache commitment and the inventory validation;
readiness never keys on one snapshot and validates an independently rebuilt
snapshot. The key also binds the GPG executable authority digest, canonical
source path, expected fingerprint, and sole UID. Only a successful parsed
identity is cached; failures are not. GPG configuration changes are
intentionally outside that commitment because configuration is excluded, while
any selected key bytes, admitted access policy, path, identity expectation, or
executable authority change forces a new GPG inventory validation. The startup
canary, every actual signing operation, and every signature verification remain
uncached.

Repository Git calls also force `core.fsmonitor=false` together with the
existing commit-graph and multi-pack-index controls. Publication calls
additionally force `core.splitIndex=false`, so the descriptor-bound temporary
index cannot create a repository-local shared index. Repository-local
fsmonitor hooks and split-index side effects therefore cannot execute during
publication or history validation.

Source-program, descriptor-bound Git, and remote-helper Python bootstraps all
inherit the coordinator's fixed owner-controlled copied runtime. `doctor` and
`start` authenticate that runtime's exact executable path objects, bytes, and
ancestor access policy before source scheduling. Every bootstrap then runs with
`-I -B -S` and verifies isolated, no-site, no-bytecode flags before
authenticating or compiling retained source. Global or user site initialization
therefore cannot run before the authenticated source-only loader; an ambient
Homebrew Cellar interpreter is not a production entry point.

Start persists a non-sensitive digest of the canonical runtime path and a
separate authority digest over executable identity, content, and ancestor
access policy. Both values participate in the run's `configuration_root`.
`status`, `accept-source`, `accept-agent-result`, `advance`, `export`, and
`finalize` reauthenticate the current executable and require exact equality
with that persisted runtime contract before reading model work or changing run
state. Runtime substitution therefore fails closed even when the replacement
still reports a compatible Python version and isolation flags.

Program-component stability protects object identity and access policy without
treating size or timestamps as identity. Every regular component is read twice
through the held descriptor and the exact bytes and final size must agree.
Package-directory child-entry, link-count, and timestamp churn is benign while
directory identity, ownership, type, and mode remain exact; regular components
still require one link. Source rollout
stability similarly compares only BSD immutable, append, nounlink, restricted,
and datavault flags plus the normalized descriptor ACL policy; `UF_HIDDEN` and
other presentation flags are not access policy.

The transport slice remains independently bounded after this hardening: 9,124
physical lines across a 9,150-line aggregate limit. One exact 17-module
inventory and its aggregate are enforced together, so omitting a transport
module cannot create a false budget pass. The facade remains 268/275 lines;
`transport_host_inventory.py` is 551/560 lines,
`transport_remote.py` is 539/575 lines, the account/home authority owner is
262/275 lines, the parent snapshot/legacy owner is 185/200 lines, the
executable bootstrap owner is 243/250 lines, and the source worker owner is
1,956/1,960 lines after adding the authenticated host/command contract and
closed failure-class relay. Retrospective still contains no SSH host table or
transport implementation.

The orchestrator foundation remains below its aggregate limit. The seven agent
support modules remain below 1,100 lines; the complete result-schema owner is
503/525, implementation authority is 586/600, and `orchestrator_jobs.py` is
526/530. The result validator is 3,900/3,900, hierarchical reduction is
2,356/2,500, and the dedicated synthesis-lineage owner is 226/250 after adding
compact recursive commitments and
revision-level recurrence proof. The global branch proxy is exactly
9,856/9,856 nodes after adding digest-bound IANA root-suffix classification,
explicit sensitive-temporary retention, and auxiliary GPG-listener proof. The
shared temporary-directory authority is 337/350 lines, while the bounded GPG
snapshot recovery owner is 235/250 lines. The shared process-group lifecycle
owner is 290/300 lines after separating signal retirement from group-absence
proof. These gates
keep complete agent schemas, claim-size projection, source-byte provenance,
semantic topic validation, and delegated remote transport in explicit owners
instead of expanding the coordinator or reviving a second remote probe.

## Architecture inventory

The inventory snapshot below uses physical lines, Python AST function boundaries (including
nested functions), and a branch proxy that counts `if`, loops, `try`, `match`,
boolean branches, conditional expressions, and comprehensions. Exact duplicate
groups hash normalized AST function bodies of at least eight lines.

| Metric | Before boundary refactor | After boundary refactor |
| --- | ---: | ---: |
| Engine Python modules | 20 | 32 |
| Engine Python lines | 44,954 | 45,469 |
| Nonblank, non-comment lines | 42,234 | 42,808 |
| Functions | 1,206 | 1,191 |
| Functions over 100 lines | 71 | 75 |
| Functions over 200 lines | 18 | 18 |
| Branch proxy total | 6,667 | 6,776 |
| Exact duplicate function-body groups | 0 | 0 |
| `orchestrator.py` lines | 11,819 | 654 |
| Largest orchestrator capability | 11,819 | 3,101 |
| `finalize.py` lines | 7,271 | 87 |
| Largest publication module | 7,271 | 3,186 |

The package inventory includes transport and excludes the 1,892-line public CLI
entrypoint. At that boundary-refactor snapshot, the largest modules were:

| Module | Lines | Functions | Branch proxy | Largest function |
| --- | ---: | ---: | ---: | ---: |
| `transport.py` | 4,839 | 119 | 713 | 542 |
| `reporting.py` | 4,067 | 77 | 704 | 399 |
| `publication_support.py` | 3,186 | 113 | 529 | 236 |
| `orchestrator_lifecycle.py` | 3,101 | 48 | 465 | 474 |
| `authority.py` | 2,985 | 61 | 424 | 200 |
| `result_validation.py` | 2,978 | 62 | 451 | 231 |
| `publication_git.py` | 2,296 | 78 | 282 | 112 |
| `orchestrator_reduction.py` | 2,234 | 40 | 393 | 184 |
| `orchestrator_source.py` | 1,995 | 30 | 292 | 389 |
| `publication_transaction.py` | 1,907 | 58 | 256 | 172 |
| `episode_review.py` | 1,653 | 49 | 291 | 158 |
| `export.py` | 1,652 | 54 | 253 | 128 |

The net lines add explicit bounded task, state, relay, authority, conservation,
and recovery contracts rather than duplicated state machines. The refactor
changes ownership boundaries without deleting fail-closed validation. The audit
finds no exact generated function-body duplication of eight or more lines.
Shared result, hierarchy, row-shape, and privacy validators remain centralized
instead of being mechanically repeated at call sites. Only `__init__.py`,
`orchestrator.py`, and `finalize.py` publish explicit wildcard interfaces;
internal modules are explicit-import-only.

`tests/test_retrospective_v2_module_boundaries.py` enforces total and per-module
line limits, a 600-line function ceiling, aggregate branch and long-function
budgets, zero exact duplicate function bodies of eight or more lines, facade
sizes, stateless capability ownership, dependency direction, publication facade
identity, and transport closure. Import enforcement walks the complete AST and
includes constant-target `importlib.import_module` and `__import__` calls, so
function-, class-, `try`-, and dynamic-import escapes remain covered.
