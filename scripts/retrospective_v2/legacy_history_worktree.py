"""Descriptor-bound clean-worktree proof for migration-only history reads."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import stat
import subprocess
import time

from . import git_safety, reporting, safe_io
from .authority_errors import HistoryValidationError


MAX_HISTORY_WORKTREE_ENTRIES = 100_000
MAX_HISTORY_WORKTREE_PATH_BYTES = 16 * 1024 * 1024
MAX_HISTORY_WORKTREE_FILE_BYTES = reporting.MAX_RETAINED_ARTIFACT_BYTES
MAX_HISTORY_WORKTREE_TOTAL_BYTES = 2 * 1024 * 1024 * 1024
MAX_HISTORY_WORKTREE_DEPTH = 64
HISTORY_WORKTREE_TIMEOUT_SECONDS = 30
_READ_CHUNK_BYTES = 64 * 1024
_DIRECTORY_FLAGS = (
    os.O_RDONLY
    | getattr(os, "O_CLOEXEC", 0)
    | getattr(os, "O_DIRECTORY", 0)
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_NONBLOCK", 0)
)
_FILE_FLAGS = (
    os.O_RDONLY
    | getattr(os, "O_CLOEXEC", 0)
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_NONBLOCK", 0)
)
_ALLOWED_MODES = {b"100644", b"100755", b"120000"}


HistoryGitRunner = Callable[
    [tuple[str, ...], float], subprocess.CompletedProcess[bytes]
]


@dataclass(frozen=True, slots=True)
class _TrackedEntry:
    mode: bytes
    object_id: bytes


@dataclass(frozen=True, slots=True)
class _GitSnapshot:
    algorithm: str
    head: bytes
    entries: dict[bytes, _TrackedEntry]
    index_bytes: bytes


@dataclass(frozen=True, slots=True)
class _FilesystemEntryCommitment:
    kind: str
    identity_and_access_policy: tuple[int, ...]
    size: int | None
    object_id: bytes | None


@dataclass(slots=True)
class _WorktreeBudget:
    deadline: float
    entries: int = 0
    path_bytes: int = 0
    content_bytes: int = 0

    @classmethod
    def create(cls) -> _WorktreeBudget:
        return cls(time.monotonic() + HISTORY_WORKTREE_TIMEOUT_SECONDS)

    def checkpoint(self) -> None:
        if time.monotonic() >= self.deadline:
            raise HistoryValidationError(
                "history worktree inspection exceeded its deadline"
            )

    def reserve_path(self, path: bytes, *, depth: int) -> None:
        self.checkpoint()
        if depth > MAX_HISTORY_WORKTREE_DEPTH:
            raise HistoryValidationError("history worktree exceeds its depth bound")
        if self.entries >= MAX_HISTORY_WORKTREE_ENTRIES:
            raise HistoryValidationError("history worktree exceeds its entry bound")
        if self.path_bytes + len(path) > MAX_HISTORY_WORKTREE_PATH_BYTES:
            raise HistoryValidationError("history worktree exceeds its path-byte bound")
        self.entries += 1
        self.path_bytes += len(path)

    def reserve_content(self, size: int) -> None:
        self.checkpoint()
        if size < 0 or size > MAX_HISTORY_WORKTREE_FILE_BYTES:
            raise HistoryValidationError("history worktree file exceeds its byte bound")
        if self.content_bytes + size > MAX_HISTORY_WORKTREE_TOTAL_BYTES:
            raise HistoryValidationError(
                "history worktree exceeds its aggregate byte bound"
            )
        self.content_bytes += size


def _run_required(
    run_git: HistoryGitRunner,
    arguments: tuple[str, ...],
    label: str,
    budget: _WorktreeBudget,
) -> bytes:
    result = run_git(arguments, budget.deadline)
    budget.checkpoint()
    if result.returncode != 0:
        raise HistoryValidationError(f"failed to inspect history {label}")
    return result.stdout


def _validate_path(path: bytes, budget: _WorktreeBudget) -> None:
    if (
        not path
        or path.startswith(b"/")
        or b"\0" in path
        or any(component in {b"", b".", b".."} for component in path.split(b"/"))
    ):
        raise HistoryValidationError("history Git output contains an unsafe path")
    budget.reserve_path(path, depth=path.count(b"/") + 1)


def _parse_tree(
    payload: bytes,
    *,
    algorithm: str,
    budget: _WorktreeBudget,
) -> dict[bytes, _TrackedEntry]:
    oid_length = 40 if algorithm == "sha1" else 64
    entries: dict[bytes, _TrackedEntry] = {}
    for record in payload.split(b"\0"):
        if not record:
            continue
        metadata, separator, path = record.partition(b"\t")
        fields = metadata.split(b" ")
        if (
            not separator
            or len(fields) != 3
            or fields[0] not in _ALLOWED_MODES
            or fields[1] != b"blob"
            or len(fields[2]) != oid_length
            or any(byte not in b"0123456789abcdef" for byte in fields[2])
        ):
            raise HistoryValidationError("history tree output is malformed")
        _validate_path(path, budget)
        if path in entries:
            raise HistoryValidationError("history tree contains a duplicate path")
        entries[path] = _TrackedEntry(fields[0], fields[2])
    return entries


def _parse_index(
    payload: bytes,
    *,
    algorithm: str,
    budget: _WorktreeBudget,
) -> dict[bytes, _TrackedEntry]:
    oid_length = 40 if algorithm == "sha1" else 64
    entries: dict[bytes, _TrackedEntry] = {}
    for record in payload.split(b"\0"):
        if not record:
            continue
        metadata, separator, path = record.partition(b"\t")
        fields = metadata.split(b" ")
        if (
            not separator
            or len(fields) != 3
            or fields[0] not in _ALLOWED_MODES
            or len(fields[1]) != oid_length
            or any(byte not in b"0123456789abcdef" for byte in fields[1])
            or fields[2] != b"0"
        ):
            raise HistoryValidationError("history index output is malformed")
        _validate_path(path, budget)
        if path in entries:
            raise HistoryValidationError("history index contains a duplicate path")
        entries[path] = _TrackedEntry(fields[0], fields[1])
    return entries


def _load_git_snapshot(
    run_git: HistoryGitRunner,
    budget: _WorktreeBudget,
) -> _GitSnapshot:
    algorithm_bytes = _run_required(
        run_git,
        ("rev-parse", "--show-object-format"),
        "object format",
        budget,
    ).strip()
    if algorithm_bytes not in {b"sha1", b"sha256"}:
        raise HistoryValidationError("history object format is unsupported")
    algorithm = algorithm_bytes.decode("ascii")
    head = _run_required(
        run_git,
        ("rev-parse", "--verify", "HEAD^{commit}"),
        "HEAD",
        budget,
    ).strip()
    oid_length = 40 if algorithm == "sha1" else 64
    if len(head) != oid_length or any(byte not in b"0123456789abcdef" for byte in head):
        raise HistoryValidationError("history HEAD is malformed")
    tree = _parse_tree(
        _run_required(
            run_git,
            ("ls-tree", "-r", "-z", head.decode("ascii")),
            "tree",
            budget,
        ),
        algorithm=algorithm,
        budget=budget,
    )
    index_bytes = _run_required(
        run_git,
        ("ls-files", "--stage", "-z"),
        "index",
        budget,
    )
    index = _parse_index(
        index_bytes,
        algorithm=algorithm,
        budget=budget,
    )
    if index != tree:
        raise HistoryValidationError(
            "history worktree must be clean before advancing state"
        )
    snapshot = _GitSnapshot(algorithm, head, tree, index_bytes)
    _require_git_snapshot_current(run_git, snapshot, budget)
    return snapshot


def _require_git_snapshot_current(
    run_git: HistoryGitRunner,
    snapshot: _GitSnapshot,
    budget: _WorktreeBudget,
) -> None:
    current_head = _run_required(
        run_git,
        ("rev-parse", "--verify", "HEAD^{commit}"),
        "HEAD",
        budget,
    ).strip()
    current_index = _run_required(
        run_git,
        ("ls-files", "--stage", "-z"),
        "index",
        budget,
    )
    if current_head != snapshot.head or current_index != snapshot.index_bytes:
        raise HistoryValidationError("history worktree changed while inspected")


def _identity_and_access_policy(metadata: os.stat_result) -> tuple[int, ...]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        stat.S_IFMT(metadata.st_mode),
        metadata.st_uid,
        metadata.st_gid,
        stat.S_IMODE(metadata.st_mode),
    )


def _require_safe_owner(metadata: os.stat_result, path: Path) -> None:
    if metadata.st_uid != os.geteuid():
        raise HistoryValidationError(f"history worktree path has another owner: {path}")
    if not stat.S_ISLNK(metadata.st_mode) and stat.S_IMODE(metadata.st_mode) & 0o022:
        raise HistoryValidationError(
            f"history worktree path is writable by others: {path}"
        )


def _read_regular_file(
    parent_fd: int,
    name: str,
    *,
    path: Path,
    expected: _TrackedEntry,
    algorithm: str,
    budget: _WorktreeBudget,
) -> _FilesystemEntryCommitment:
    descriptor = os.open(name, _FILE_FLAGS, dir_fd=parent_fd)
    primary: BaseException | None = None
    try:
        anchored = os.fstat(descriptor)
        named = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        _require_safe_owner(anchored, path)
        if (
            not stat.S_ISREG(anchored.st_mode)
            or _identity_and_access_policy(anchored)
            != _identity_and_access_policy(named)
            or anchored.st_size != named.st_size
            or safe_io.descriptor_has_extended_acl(descriptor)
        ):
            raise HistoryValidationError(
                "history worktree file cannot be authenticated"
            )
        budget.reserve_content(anchored.st_size)
        digest = hashlib.new(algorithm)
        digest.update(f"blob {anchored.st_size}\0".encode("ascii"))
        remaining = anchored.st_size
        while remaining:
            budget.checkpoint()
            chunk = os.read(descriptor, min(_READ_CHUNK_BYTES, remaining))
            if not chunk:
                raise HistoryValidationError("history worktree file changed while read")
            digest.update(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise HistoryValidationError("history worktree file grew while read")
        final = os.fstat(descriptor)
        current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if (
            _identity_and_access_policy(final) != _identity_and_access_policy(anchored)
            or _identity_and_access_policy(current)
            != _identity_and_access_policy(anchored)
            or final.st_size != anchored.st_size
            or current.st_size != anchored.st_size
            or safe_io.descriptor_has_extended_acl(descriptor)
        ):
            raise HistoryValidationError("history worktree file changed while read")
        mode = b"100755" if anchored.st_mode & stat.S_IXUSR else b"100644"
        if (
            mode != expected.mode
            or digest.hexdigest().encode("ascii") != expected.object_id
        ):
            raise HistoryValidationError(
                "history worktree must be clean before advancing state"
            )
        return _FilesystemEntryCommitment(
            "regular",
            _identity_and_access_policy(final),
            final.st_size,
            expected.object_id,
        )
    except BaseException as error:
        primary = error
        raise
    finally:
        git_safety.close_repository_descriptors(
            (descriptor,),
            "history worktree file",
            primary=primary,
        )


def _list_directory(
    descriptor: int,
    *,
    relative: bytes | None,
    budget: _WorktreeBudget,
    depth: int,
    expected_count: int | None = None,
) -> tuple[tuple[str, bytes], ...]:
    entries: list[tuple[str, bytes]] = []
    with os.scandir(descriptor) as iterator:
        for entry in iterator:
            budget.checkpoint()
            name = entry.name
            if depth == 0 and name == ".git":
                continue
            if expected_count is not None and len(entries) >= expected_count:
                raise HistoryValidationError("history worktree changed while inspected")
            raw_name = os.fsencode(name)
            if relative is not None:
                path = raw_name if not relative else relative + b"/" + raw_name
                budget.reserve_path(path, depth=depth + 1)
            entries.append((name, raw_name))
    entries.sort(key=lambda item: item[1])
    return tuple(entries)


def _scan_directory(
    descriptor: int,
    *,
    relative: bytes,
    display_path: Path,
    expected: dict[bytes, _TrackedEntry],
    seen: set[bytes],
    commitments: dict[bytes, _FilesystemEntryCommitment],
    algorithm: str,
    budget: _WorktreeBudget,
    depth: int,
) -> None:
    budget.checkpoint()
    anchored = safe_io.validate_owner_only_directory_descriptor(
        descriptor,
        display_path,
        exact_mode=False,
    )
    entries = _list_directory(
        descriptor,
        relative=relative,
        budget=budget,
        depth=depth,
    )
    for name, raw_name in entries:
        path = raw_name if not relative else relative + b"/" + raw_name
        display_child = display_path / name
        observed = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
        _require_safe_owner(observed, display_child)
        if stat.S_ISDIR(observed.st_mode):
            child_fd = os.open(name, _DIRECTORY_FLAGS, dir_fd=descriptor)
            primary: BaseException | None = None
            try:
                opened = os.fstat(child_fd)
                if _identity_and_access_policy(opened) != _identity_and_access_policy(
                    observed
                ):
                    raise HistoryValidationError(
                        "history worktree directory changed while opened"
                    )
                _scan_directory(
                    child_fd,
                    relative=path,
                    display_path=display_child,
                    expected=expected,
                    seen=seen,
                    commitments=commitments,
                    algorithm=algorithm,
                    budget=budget,
                    depth=depth + 1,
                )
                current = os.stat(
                    name,
                    dir_fd=descriptor,
                    follow_symlinks=False,
                )
                if _identity_and_access_policy(current) != _identity_and_access_policy(
                    opened
                ):
                    raise HistoryValidationError(
                        "history worktree directory changed while inspected"
                    )
                commitments[path] = _FilesystemEntryCommitment(
                    "directory",
                    _identity_and_access_policy(current),
                    None,
                    None,
                )
            except BaseException as error:
                primary = error
                raise
            finally:
                git_safety.close_repository_descriptors(
                    (child_fd,),
                    "history worktree directory",
                    primary=primary,
                )
            continue
        expected_entry = expected.get(path)
        if expected_entry is None:
            raise HistoryValidationError(
                "history worktree must be clean before advancing state"
            )
        if stat.S_ISREG(observed.st_mode):
            commitments[path] = _read_regular_file(
                descriptor,
                name,
                path=display_child,
                expected=expected_entry,
                algorithm=algorithm,
                budget=budget,
            )
        elif stat.S_ISLNK(observed.st_mode):
            raise HistoryValidationError(
                "history worktree symlinks cannot be authenticated"
            )
        else:
            raise HistoryValidationError(
                "history worktree contains an unsupported object"
            )
        seen.add(path)
    final_entries = _list_directory(
        descriptor,
        relative=None,
        budget=budget,
        depth=depth,
        expected_count=len(entries),
    )
    final = safe_io.validate_owner_only_directory_descriptor(
        descriptor,
        display_path,
        exact_mode=False,
    )
    if final_entries != entries or (
        final.st_dev,
        final.st_ino,
        final.st_uid,
        final.st_gid,
        stat.S_IMODE(final.st_mode),
    ) != (
        anchored.st_dev,
        anchored.st_ino,
        anchored.st_uid,
        anchored.st_gid,
        stat.S_IMODE(anchored.st_mode),
    ):
        raise HistoryValidationError("history worktree changed while inspected")


def _scan_held_repository(
    repository_fd: int,
    repository: Path,
    snapshot: _GitSnapshot,
    budget: _WorktreeBudget,
) -> dict[bytes, _FilesystemEntryCommitment]:
    seen: set[bytes] = set()
    root = safe_io.validate_owner_only_directory_descriptor(
        repository_fd,
        repository,
        exact_mode=False,
    )
    commitments: dict[bytes, _FilesystemEntryCommitment] = {
        b"": _FilesystemEntryCommitment(
            "directory",
            _identity_and_access_policy(root),
            None,
            None,
        )
    }
    _scan_directory(
        repository_fd,
        relative=b"",
        display_path=repository,
        expected=snapshot.entries,
        seen=seen,
        commitments=commitments,
        algorithm=snapshot.algorithm,
        budget=budget,
        depth=0,
    )
    if seen != set(snapshot.entries):
        raise HistoryValidationError(
            "history worktree must be clean before advancing state"
        )
    return commitments


def require_clean_worktree(
    repository: Path,
    *,
    admission: git_safety.LocalRepositoryAdmission,
    run_git: HistoryGitRunner,
    directory_identity: git_safety.DirectoryIdentity,
) -> None:
    """Require HEAD, index, and held worktree bytes to match exactly."""

    try:
        deadline = _WorktreeBudget.create().deadline
        with git_safety.bind_local_repository_command(
            admission,
            directory_identity,
        ) as binding:
            before = _load_git_snapshot(run_git, _WorktreeBudget(deadline))
            first_commitments = _scan_held_repository(
                binding.repository_fd,
                repository,
                before,
                _WorktreeBudget(deadline),
            )
            after = _load_git_snapshot(run_git, _WorktreeBudget(deadline))
            if after != before:
                raise HistoryValidationError("history worktree changed while inspected")
            final_commitments = _scan_held_repository(
                binding.repository_fd,
                repository,
                after,
                _WorktreeBudget(deadline),
            )
            if final_commitments != first_commitments:
                raise HistoryValidationError("history worktree changed while inspected")
            _require_git_snapshot_current(
                run_git,
                after,
                _WorktreeBudget(deadline),
            )
    except HistoryValidationError:
        raise
    except (OSError, ValueError) as error:
        raise HistoryValidationError(
            "history worktree cannot be authenticated"
        ) from error
