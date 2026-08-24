"""Descriptor-bound temporary-directory authority for runtime operations."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
import os
from pathlib import Path
import pwd
import secrets
import stat
from typing import Callable, Iterator

try:
    from . import safe_io, transport_paths
    from .transport_contracts import source_root_commitment
except (ImportError, ModuleNotFoundError):
    import safe_io  # type: ignore[no-redef]
    import transport_paths  # type: ignore[no-redef]
    from transport_contracts import source_root_commitment  # type: ignore[no-redef]


_RUNTIME_TEMP_BASE = Path("/tmp") / f"codex-session-retrospective-{os.getuid()}"
PUBLISHER_CANARY_TEMP_ROOT = _RUNTIME_TEMP_BASE / "publisher-canary"
PUBLISHER_KEYRING_SNAPSHOT_TEMP_ROOT = Path("/tmp") / f"csr{os.getuid()}"
REMOTE_HELPER_TEMP_ROOT = _RUNTIME_TEMP_BASE / "remote-helper"
REMOTE_TRANSPORT_SPOOL_TEMP_ROOT = _RUNTIME_TEMP_BASE / "remote-transport-spool"
SESSION_SHARDS_SPOOL_TEMP_ROOT = _RUNTIME_TEMP_BASE / "session-shards-spool"
PUBLICATION_INDEX_TEMP_ROOT = _RUNTIME_TEMP_BASE / "publication-index"
_TEMPORARY_NAME_ATTEMPTS = 8
_TEMPORARY_CLEANUP_ENTRIES = 64
_TEMPORARY_CLEANUP_PATH_BYTES = 64 * 1024
_TEMPORARY_CLEANUP_DEPTH = 4
_TEMPORARY_CLEANUP_SECONDS = 30.0
_TEMPORARY_CLEANUP_CAUSE_LIMIT = 16
_TEMPORARY_CLEANUP_INCOMPLETE_ATTRIBUTE = "_retrospective_temporary_cleanup_incomplete"
_UNEXPECTED_RETENTION = (
    "sensitive temporary directory retained without an active failure"
)
_BOUNDED_RETENTION = "sensitive temporary directory retained for bounded recovery"


def mark_incomplete_cleanup(error: BaseException, *, stage: str) -> None:
    """Attach a content-free sensitive temporary-cleanup marker."""
    setattr(error, _TEMPORARY_CLEANUP_INCOMPLETE_ATTRIBUTE, True)
    error.add_note(f"sensitive temporary cleanup incomplete at {stage}")


def incomplete_cleanup_primary(error: BaseException) -> BaseException | None:
    """Return the outer primary when nested temporary cleanup is incomplete."""
    current: BaseException | None = error
    visited: set[int] = set()
    for _ in range(_TEMPORARY_CLEANUP_CAUSE_LIMIT):
        if current is None or id(current) in visited:
            return None
        visited.add(id(current))
        if getattr(current, _TEMPORARY_CLEANUP_INCOMPLETE_ATTRIBUTE, False) is True:
            return error
        current = current.__cause__ or current.__context__
    return None


def local_codex_root() -> Path:
    """Resolve the canonical local source root without ambient HOME state."""
    try:
        account = pwd.getpwuid(os.getuid())
    except (KeyError, OSError) as exc:
        raise ValueError("local account identity is unavailable") from exc
    home = account.pw_dir
    if not isinstance(home, str) or not home or set(home) & {"\x00", "\r", "\n"}:
        raise ValueError("local account home is invalid")
    root = Path(home) / ".codex"
    source_root_commitment(codex_root=str(root), route="local", host="local")
    return root


def require_run_directory_outside_sources(run_dir: str | Path) -> Path:
    """Reject a run directory that can contain or enter local session sources."""
    lexical_run_dir = Path(os.path.abspath(os.fspath(Path(run_dir).expanduser())))
    source_root = local_codex_root()
    _require_root_outside_source(lexical_run_dir, source_root / "sessions")
    _require_root_outside_source(lexical_run_dir, source_root / "archived_sessions")
    _require_root_outside_source(lexical_run_dir, source_root / "history.jsonl")
    _require_root_outside_source(lexical_run_dir, source_root / "session_index.jsonl")
    _require_root_outside_source(lexical_run_dir, source_root, _root_rollout_overlap)
    return lexical_run_dir


def _ordinary_source_overlap(*paths: Path) -> bool:
    return any(
        (
            paths[0].is_relative_to(paths[1]),
            paths[1].is_relative_to(paths[0]),
            paths[2].is_relative_to(paths[3]),
            paths[3].is_relative_to(paths[2]),
        )
    )


def _root_rollout_overlap(*paths: Path) -> bool:
    lexical_name = os.path.relpath(paths[0], paths[1]).partition(os.sep)[0]
    resolved_name = os.path.relpath(paths[2], paths[3]).partition(os.sep)[0]
    return any(
        (
            transport_paths.ROOT_ROLLOUT_RELATIVE_RE.fullmatch(lexical_name),
            transport_paths.ROOT_ROLLOUT_RELATIVE_RE.fullmatch(resolved_name),
        )
    )


def _require_root_outside_source(
    temporary_root: Path,
    source_root: Path,
    overlap_test: Callable[..., bool] = _ordinary_source_overlap,
) -> None:
    lexical_temporary_root = Path(os.path.abspath(os.fspath(temporary_root)))
    lexical_source_root = Path(os.path.abspath(os.fspath(source_root)))
    resolved_temporary_root = lexical_temporary_root.resolve(strict=False)
    resolved_source_root = lexical_source_root.resolve(strict=False)
    overlap = overlap_test(
        lexical_temporary_root,
        lexical_source_root,
        resolved_temporary_root,
        resolved_source_root,
    )
    if overlap:
        raise safe_io.UnsafePathError(
            "runtime temporary root overlaps a retrospective source root"
        )


def _directory_object(metadata: os.stat_result) -> tuple[int, int, int, int]:
    mode = stat.S_IMODE(metadata.st_mode)
    return metadata.st_dev, metadata.st_ino, metadata.st_uid, mode


def _close_descriptor(descriptor: int, *, primary: BaseException | None) -> None:
    try:
        os.close(descriptor)
    except OSError as error:
        mark_incomplete_cleanup(primary or error, stage="descriptor-close")
        if primary is None:
            raise
        primary.add_note(f"temporary-directory descriptor close failed: {error}")


@dataclass(slots=True)
class _TemporaryRetention:
    requested: bool = False


@dataclass(frozen=True, slots=True)
class BoundTemporaryDirectory:
    path: Path
    _root_path: Path
    _source_root: Path
    _root_fd: int
    _child_fd: int
    _retention: _TemporaryRetention = field(
        default_factory=_TemporaryRetention, repr=False, compare=False
    )

    @property
    def retained_for_recovery(self) -> bool:
        return self._retention.requested

    def retain_for_recovery(self, error: BaseException, *, stage: str) -> None:
        """Prevent generic removal when specialized cleanup is unproved."""
        self._retention.requested = True
        mark_incomplete_cleanup(error, stage=stage)

    def revalidate(self) -> None:
        root = safe_io.validate_owner_only_directory_descriptor(
            self._root_fd, self._root_path
        )
        named_root = os.stat(self._root_path, follow_symlinks=False)
        if not stat.S_ISDIR(named_root.st_mode) or _directory_object(
            named_root
        ) != _directory_object(root):
            raise safe_io.UnsafePathError(
                "runtime temporary root changed after binding"
            )
        child = safe_io.validate_owner_only_directory_descriptor(
            self._child_fd, self.path
        )
        named_child = os.stat(
            self.path.name,
            dir_fd=self._root_fd,
            follow_symlinks=False,
        )
        if not stat.S_ISDIR(named_child.st_mode) or _directory_object(
            named_child
        ) != _directory_object(child):
            raise safe_io.UnsafePathError(
                "runtime temporary directory changed after binding"
            )
        resolved_root = self._root_path.resolve(strict=True)
        resolved_child = self.path.resolve(strict=True)
        if resolved_child.parent != resolved_root:
            raise safe_io.UnsafePathError(
                "runtime temporary directory escaped its bound root"
            )
        _require_root_outside_source(resolved_child, self._source_root)

    def harden_file(self, name: str) -> Path:
        if not name or name in {".", ".."} or "/" in name or "\x00" in name:
            raise ValueError("temporary file name must be one safe component")
        self.revalidate()
        display_path = self.path / name
        descriptor = os.open(
            name,
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0)
            | getattr(os, "O_CLOEXEC", 0),
            dir_fd=self._child_fd,
        )
        primary: BaseException | None = None
        try:
            safe_io.harden_created_owner_only_file_descriptor(descriptor, display_path)
            anchored = os.fstat(descriptor)
            named = os.stat(name, dir_fd=self._child_fd, follow_symlinks=False)
            if _directory_object(named) != _directory_object(anchored):
                raise safe_io.UnsafePathError(
                    "runtime temporary file changed while hardened"
                )
        except BaseException as error:
            primary = error
            raise
        finally:
            _close_descriptor(descriptor, primary=primary)
        self.revalidate()
        return display_path


def _cleanup_budget() -> safe_io.TreeInventoryBudget:
    return safe_io.TreeInventoryBudget.from_timeout(
        max_entries=_TEMPORARY_CLEANUP_ENTRIES,
        max_path_bytes=_TEMPORARY_CLEANUP_PATH_BYTES,
        max_depth=_TEMPORARY_CLEANUP_DEPTH,
        timeout_seconds=_TEMPORARY_CLEANUP_SECONDS,
    )


def _cleanup_bound_directory(binding: BoundTemporaryDirectory) -> None:
    binding.revalidate()
    inventory = safe_io.inspect_tree_inventory_at(
        binding._root_fd,
        binding.path.name,
        budget=_cleanup_budget(),
        display_path=binding.path,
    )
    binding.revalidate()
    safe_io.secure_remove_tree_at(
        binding._root_fd,
        binding.path.name,
        display_path=binding.path,
        expected_inventory=inventory["entries"],
        budget=_cleanup_budget(),
    )


@contextmanager
def owner_only_temporary_directory(
    *, root: Path, prefix: str
) -> Iterator[BoundTemporaryDirectory]:
    allowed = "abcdefghijklmnopqrstuvwxyz0123456789-_"
    if not prefix or len(prefix) > 64 or any(char not in allowed for char in prefix):
        raise ValueError("temporary directory prefix is invalid")
    source_root = local_codex_root()
    root = Path(root)
    _require_root_outside_source(root, source_root)
    root_path, root_fd = safe_io.open_owner_only_directory(root, create=True)
    binding: BoundTemporaryDirectory | None = None
    primary: BaseException | None = None
    retained_name: str | None = None
    try:
        _require_root_outside_source(root_path, source_root)
        for _attempt in range(_TEMPORARY_NAME_ATTEMPTS):
            name = prefix + secrets.token_hex(32)
            try:
                os.mkdir(name, safe_io.OWNER_DIRECTORY_MODE, dir_fd=root_fd)
            except FileExistsError:
                continue
            retained_name = name
            child_fd = os.open(
                name,
                os.O_RDONLY
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0),
                dir_fd=root_fd,
            )
            binding = BoundTemporaryDirectory(
                path=root_path / name,
                _root_path=root_path,
                _source_root=source_root,
                _root_fd=root_fd,
                _child_fd=child_fd,
            )
            safe_io.harden_created_owner_only_directory_descriptor(
                child_fd, root_path / name
            )
            binding.revalidate()
            break
        if binding is None:
            raise FileExistsError("could not allocate a unique temporary directory")
        yield binding
    except BaseException as error:
        primary = error
        raise
    finally:
        terminal_error: BaseException | None = None
        if binding is not None:
            if binding.retained_for_recovery:
                if primary is None:
                    terminal_error = RuntimeError(_UNEXPECTED_RETENTION)
                    mark_incomplete_cleanup(terminal_error, stage="explicit-retention")
                    primary = terminal_error
                else:
                    primary.add_note(_BOUNDED_RETENTION)
            else:
                try:
                    _cleanup_bound_directory(binding)
                except BaseException as cleanup_error:
                    if primary is None:
                        mark_incomplete_cleanup(cleanup_error, stage="tree-removal")
                        primary = cleanup_error
                        terminal_error = cleanup_error
                    else:
                        mark_incomplete_cleanup(primary, stage="tree-removal")
                        primary.add_note(
                            f"temporary-directory cleanup failed: {cleanup_error}"
                        )
            try:
                _close_descriptor(binding._child_fd, primary=primary)
            except BaseException as close_error:
                primary = close_error
                terminal_error = close_error
        elif retained_name is not None and primary is not None:
            mark_incomplete_cleanup(primary, stage="unproven-created-directory")
            primary.add_note(
                f"unproven temporary directory retained under bound root: {retained_name}"
            )
        try:
            _close_descriptor(root_fd, primary=primary)
        except BaseException as close_error:
            terminal_error = close_error
        if terminal_error is not None:
            raise terminal_error
