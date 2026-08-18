"""Closed local-repository completeness checks for retained-history Git reads."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import hmac
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
from typing import Iterator, Mapping, Sequence

from . import executable_authority, safe_io
from .authority_errors import HistoryValidationError


GitRunner = Callable[[tuple[str, ...]], subprocess.CompletedProcess[bytes]]
DirectoryIdentity = Callable[[Path], tuple[int, ...]]
HISTORY_TOPOLOGY_CONFIG_ARGUMENTS = (
    "-c",
    "core.commitGraph=false",
    "-c",
    "core.multiPackIndex=false",
)
_HISTORY_TARGET_REF_RE = re.compile(
    r"refs/heads/"
    r"(?!\.)(?!.*(?:/\.|//|\.lock(?:/|\Z)|\.\.|@\{|[\x00-\x20\x7f~^:?*\[\\]))"
    r"(?!.*\.\Z)[^/]+(?:/[^/]+)*\Z"
)


class LocalRepositorySafetyError(ValueError):
    """A closed local-repository admission property was not proved."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


def require_history_target_ref_shape(target_ref: object) -> str:
    """Require the closed lexical shape before repository admission starts."""

    if (
        not isinstance(target_ref, str)
        or _HISTORY_TARGET_REF_RE.fullmatch(target_ref) is None
    ):
        raise HistoryValidationError(
            "durable history target must be a valid fully qualified branch ref",
        )
    return target_ref


def validate_history_target_ref(run: GitRunner, target_ref: object) -> str:
    """Require one fully qualified, syntactically valid mutable branch ref."""

    target_ref = require_history_target_ref_shape(target_ref)
    result = run(("check-ref-format", target_ref))
    if result.returncode != 0:
        raise HistoryValidationError(
            "durable history target is not a valid Git branch ref",
        )
    return target_ref


@dataclass(frozen=True)
class GitDiscoveryFileBinding:
    """Identity and content binding for one Git discovery control file."""

    parent: Path
    name: str
    path: Path
    identity: tuple[int, ...]
    sha256: str


@dataclass(frozen=True)
class LocalRepositoryAdmission:
    """Filesystem binding shared by history readers and publishers."""

    repository: Path
    git_dir: Path
    common_dir: Path
    object_store: Path
    directory_identities: tuple[tuple[Path, tuple[int, ...]], ...]
    forbidden_metadata: tuple[tuple[Path, str], ...]
    config_path: Path
    config_sha256: str
    git_dir_relative: str
    git_marker_is_directory: bool
    discovery_files: tuple[GitDiscoveryFileBinding, ...]
    absent_discovery_files: tuple[tuple[Path, str, Path], ...]


@dataclass
class LocalRepositoryCommandBinding:
    """Held directory objects used by one admitted Git subprocess."""

    admission: LocalRepositoryAdmission
    repository_fd: int
    git_dir_fd: int
    common_dir_fd: int
    object_store_fd: int

    @property
    def descriptors(self) -> tuple[int, ...]:
        return (
            self.repository_fd,
            self.git_dir_fd,
            self.common_dir_fd,
            self.object_store_fd,
        )

    def command(
        self,
        python_executable: str,
        executable: str,
        arguments: Sequence[str],
    ) -> tuple[str, ...]:
        return (
            python_executable,
            "-I",
            "-B",
            "-S",
            "-c",
            _DESCRIPTOR_CWD_EXEC_SOURCE,
            str(self.common_dir_fd),
            str(self.git_dir_fd),
            str(self.object_store_fd),
            self.admission.git_dir_relative,
            executable,
            "--bare",
            "-C",
            ".",
            *arguments,
        )


_CONFIG_LIMIT_BYTES = 1024 * 1024
_GIT_DISCOVERY_FILE_LIMIT_BYTES = 4096
_BOUND_GIT_ENVIRONMENT_KEYS = frozenset(
    {
        "GIT_CEILING_DIRECTORIES",
        "GIT_COMMON_DIR",
        "GIT_DIR",
        "GIT_OBJECT_DIRECTORY",
        "GIT_WORK_TREE",
    }
)
_DESCRIPTOR_CWD_EXEC_SOURCE = (
    "import os,stat,sys\n"
    "common_fd,git_fd,object_fd=map(int,sys.argv[1:4])\n"
    "relative_git_dir=sys.argv[4]\n"
    "flags=os.O_RDONLY|os.O_DIRECTORY|getattr(os,'O_CLOEXEC',0)|getattr(os,'O_NOFOLLOW',0)\n"
    "def identity(fd):\n"
    " metadata=os.fstat(fd)\n"
    " return metadata.st_dev,metadata.st_ino,metadata.st_mode,metadata.st_uid\n"
    "def open_relative(root_fd,path):\n"
    " descriptor=os.dup(root_fd)\n"
    " try:\n"
    "  parts=() if path=='.' else tuple(path.split(os.sep))\n"
    "  if any(part in {'','.', '..'} for part in parts): raise OSError('unsafe relative Git metadata path')\n"
    "  for part in parts:\n"
    "   child=os.open(part,flags,dir_fd=descriptor)\n"
    "   os.close(descriptor)\n"
    "   descriptor=child\n"
    "   metadata=os.fstat(descriptor)\n"
    "   if not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid!=os.geteuid() or stat.S_IMODE(metadata.st_mode)&0o022: raise OSError('unsafe Git metadata directory')\n"
    "  return descriptor\n"
    " except BaseException:\n"
    "  os.close(descriptor)\n"
    "  raise\n"
    "os.fchdir(common_fd)\n"
    "cwd_fd=os.open('.',flags)\n"
    "try:\n"
    " if identity(common_fd)!=identity(cwd_fd): raise OSError('Git common directory changed')\n"
    "finally:\n"
    " os.close(cwd_fd)\n"
    "opened_git=open_relative(common_fd,relative_git_dir)\n"
    "opened_objects=open_relative(common_fd,'objects')\n"
    "try:\n"
    " if identity(opened_git)!=identity(git_fd) or identity(opened_objects)!=identity(object_fd): raise OSError('Git metadata identity changed')\n"
    "finally:\n"
    " os.close(opened_git)\n"
    " os.close(opened_objects)\n"
    "os.environ['GIT_CEILING_DIRECTORIES']=os.getcwd()\n"
    "os.environ['GIT_COMMON_DIR']='.'\n"
    "os.environ['GIT_DIR']=relative_git_dir\n"
    "os.environ['GIT_OBJECT_DIRECTORY']='objects'\n"
    "os.environ.pop('GIT_WORK_TREE',None)\n"
    "os.execve(sys.argv[5],sys.argv[5:],os.environ)\n"
)


def _stat_identity(metadata: os.stat_result) -> tuple[int, int, int, int]:
    return metadata.st_dev, metadata.st_ino, metadata.st_mode, metadata.st_uid


def _config_stat_identity(metadata: os.stat_result) -> tuple[int, ...]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_uid,
        metadata.st_gid,
        metadata.st_nlink,
        metadata.st_size,
    )


def _closed_git_dir_relative(common_dir: Path, git_dir: Path) -> str:
    try:
        relative = git_dir.relative_to(common_dir)
    except ValueError as error:
        raise LocalRepositorySafetyError(
            "discovery-path-not-closed",
            "Git directory must be contained by the admitted common directory",
        ) from error
    if not relative.parts:
        return "."
    if any(part in {"", ".", ".."} for part in relative.parts):
        raise LocalRepositorySafetyError(
            "discovery-path-not-closed", "Git directory path is not closed"
        )
    return os.path.join(*relative.parts)


def _validate_git_discovery_file_stat(
    metadata: os.stat_result,
    display_path: Path,
) -> None:
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) & 0o022
        or metadata.st_nlink != 1
        or metadata.st_size > _GIT_DISCOVERY_FILE_LIMIT_BYTES
    ):
        raise LocalRepositorySafetyError(
            "discovery-file-unsafe",
            f"Git discovery file is not owner-controlled: {display_path}",
        )


def _read_git_discovery_file_at(
    parent_fd: int,
    name: str,
    display_path: Path,
) -> tuple[tuple[int, ...], bytes]:
    primary: BaseException | None = None
    descriptor: int | None = None
    try:
        descriptor = safe_io.open_checked_file_at(
            parent_fd,
            name,
            display_path=display_path,
            require_owner_only=False,
        )
    except (OSError, safe_io.UnsafePathError) as error:
        raise LocalRepositorySafetyError(
            "discovery-file-unreadable",
            f"Git discovery file cannot be authenticated: {display_path}",
        ) from error
    try:
        before = os.fstat(descriptor)
        named_before = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        _validate_git_discovery_file_stat(before, display_path)
        _validate_git_discovery_file_stat(named_before, display_path)
        if safe_io.descriptor_has_extended_acl(descriptor):
            raise LocalRepositorySafetyError(
                "discovery-file-unsafe",
                f"Git discovery file has an extended ACL: {display_path}",
            )

        def read_once() -> bytes:
            os.lseek(descriptor, 0, os.SEEK_SET)
            payload = bytearray()
            while len(payload) <= _GIT_DISCOVERY_FILE_LIMIT_BYTES:
                chunk = os.read(
                    descriptor,
                    min(
                        64 * 1024,
                        _GIT_DISCOVERY_FILE_LIMIT_BYTES - len(payload) + 1,
                    ),
                )
                if not chunk:
                    break
                payload.extend(chunk)
            if len(payload) > _GIT_DISCOVERY_FILE_LIMIT_BYTES:
                raise LocalRepositorySafetyError(
                    "discovery-file-unsafe",
                    f"Git discovery file exceeds its bound: {display_path}",
                )
            return bytes(payload)

        first = read_once()
        middle = os.fstat(descriptor)
        second = read_once()
        after = os.fstat(descriptor)
        named_after = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        for metadata in (middle, after, named_after):
            _validate_git_discovery_file_stat(metadata, display_path)
        expected_identity = _config_stat_identity(before)
        if (
            any(
                _config_stat_identity(metadata) != expected_identity
                for metadata in (named_before, middle, after, named_after)
            )
            or len(first) != before.st_size
            or not hmac.compare_digest(first, second)
        ):
            raise LocalRepositorySafetyError(
                "discovery-file-changed",
                f"Git discovery file changed while read: {display_path}",
            )
        return expected_identity, first
    except LocalRepositorySafetyError as error:
        primary = error
        raise
    except OSError as error:
        mapped = LocalRepositorySafetyError(
            "discovery-file-unreadable",
            f"Git discovery file cannot be authenticated: {display_path}",
        )
        primary = mapped
        raise mapped from error
    except BaseException as error:
        primary = error
        raise
    finally:
        if descriptor is not None:
            _close_descriptors(
                (descriptor,),
                "Git discovery file",
                primary=primary,
            )


def _bind_git_discovery_file(
    parent: Path,
    parent_fd: int,
    name: str,
) -> tuple[GitDiscoveryFileBinding, bytes]:
    path = parent / name
    identity, payload = _read_git_discovery_file_at(parent_fd, name, path)
    return (
        GitDiscoveryFileBinding(
            parent=parent,
            name=name,
            path=path,
            identity=identity,
            sha256=hashlib.sha256(payload).hexdigest(),
        ),
        payload,
    )


def _git_pointer_path(parent: Path, payload: bytes, *, marker: bool) -> Path:
    prefix = b"gitdir: " if marker else b""
    if not payload.startswith(prefix):
        raise LocalRepositorySafetyError(
            "discovery-file-invalid", "Git discovery file syntax is invalid"
        )
    raw = payload[len(prefix) :]
    if raw.endswith(b"\n"):
        raw = raw[:-1]
    if not raw or any(character in raw for character in (b"\x00", b"\r", b"\n")):
        raise LocalRepositorySafetyError(
            "discovery-file-invalid", "Git discovery file syntax is invalid"
        )
    candidate = Path(os.fsdecode(raw))
    if not candidate.is_absolute():
        candidate = parent / candidate
    return Path(os.path.abspath(candidate))


def _require_discovery_file_absent(parent_fd: int, name: str, path: Path) -> None:
    try:
        os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    except OSError as error:
        raise LocalRepositorySafetyError(
            "discovery-file-unreadable",
            f"Git discovery file absence cannot be authenticated: {path}",
        ) from error
    raise LocalRepositorySafetyError(
        "discovery-file-changed",
        f"unexpected Git discovery file is present: {path}",
    )


def _close_descriptors(
    descriptors: Sequence[int],
    label: str,
    *,
    primary: BaseException | None = None,
) -> None:
    failures: list[OSError] = []
    for descriptor in reversed(descriptors):
        try:
            os.close(descriptor)
        except OSError as error:
            failures.append(error)
    if not failures:
        return
    message = f"{label} descriptor close failed"
    if primary is not None:
        primary.add_note(message)
        return
    raise LocalRepositorySafetyError("descriptor-close-failed", message) from failures[
        0
    ]


def close_repository_descriptors(
    descriptors: Sequence[int],
    label: str,
    *,
    primary: BaseException | None = None,
) -> None:
    """Close repository-owned descriptors without replacing an active failure."""

    _close_descriptors(descriptors, label, primary=primary)


def _config_commitment(common_dir_fd: int, display_path: Path) -> str:
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    primary: BaseException | None = None
    try:
        descriptor = os.open("config", flags, dir_fd=common_dir_fd)
    except OSError as exc:
        raise LocalRepositorySafetyError(
            "config-unreadable", "local Git configuration cannot be authenticated"
        ) from exc
    try:
        before = os.fstat(descriptor)
        named_before = os.stat("config", dir_fd=common_dir_fd, follow_symlinks=False)
        mode = stat.S_IMODE(before.st_mode)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.geteuid()
            or mode & 0o022
            or before.st_nlink != 1
            or before.st_size > _CONFIG_LIMIT_BYTES
            or _config_stat_identity(named_before) != _config_stat_identity(before)
            or safe_io.descriptor_has_extended_acl(descriptor)
        ):
            raise LocalRepositorySafetyError(
                "config-unsafe", "local Git configuration is not owner-controlled"
            )
        remaining = _CONFIG_LIMIT_BYTES + 1
        chunks: list[bytes] = []
        while remaining:
            chunk = os.read(descriptor, min(64 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        after = os.fstat(descriptor)
        named_after = os.stat("config", dir_fd=common_dir_fd, follow_symlinks=False)
        if (
            _config_stat_identity(after) != _config_stat_identity(before)
            or _config_stat_identity(named_after) != _config_stat_identity(before)
            or len(payload) != after.st_size
            or len(payload) > _CONFIG_LIMIT_BYTES
            or safe_io.descriptor_has_extended_acl(descriptor)
        ):
            raise LocalRepositorySafetyError(
                "config-changed", "local Git configuration changed while read"
            )
        return hashlib.sha256(payload).hexdigest()
    except LocalRepositorySafetyError as error:
        primary = error
        raise
    except OSError as exc:
        mapped = LocalRepositorySafetyError(
            "config-unreadable", "local Git configuration cannot be authenticated"
        )
        primary = mapped
        raise mapped from exc
    except BaseException as error:
        primary = error
        raise
    finally:
        _close_descriptors((descriptor,), "Git config", primary=primary)


def _open_bound_directory(
    path: Path,
    expected: tuple[int, ...],
) -> int:
    descriptor: int | None = None
    try:
        _normalized, descriptor = safe_io.open_owner_controlled_directory(path)
        metadata = safe_io.validate_owner_only_directory_descriptor(
            descriptor, path, exact_mode=False
        )
        if _stat_identity(metadata) != expected:
            raise safe_io.UnsafePathError("Git metadata identity changed")
    except (OSError, safe_io.UnsafePathError) as exc:
        mapped = LocalRepositorySafetyError(
            "metadata-changed", "Git metadata changed after validation"
        )
        if descriptor is not None:
            _close_descriptors((descriptor,), "Git metadata", primary=mapped)
        raise mapped from exc
    except BaseException as error:
        if descriptor is not None:
            _close_descriptors((descriptor,), "Git metadata", primary=error)
        raise
    assert descriptor is not None
    return descriptor


def _admit_repository_discovery(
    *,
    repository: Path,
    repository_fd: int,
    git_dir: Path,
    git_dir_fd: int,
    common_dir: Path,
    directory_identities: Mapping[Path, tuple[int, ...]],
) -> tuple[
    bool,
    tuple[GitDiscoveryFileBinding, ...],
    tuple[tuple[Path, str, Path], ...],
]:
    files: list[GitDiscoveryFileBinding] = []
    absent: list[tuple[Path, str, Path]] = []
    marker_path = repository / ".git"
    try:
        marker_stat = os.stat(".git", dir_fd=repository_fd, follow_symlinks=False)
    except OSError as error:
        raise LocalRepositorySafetyError(
            "discovery-file-unreadable",
            "Git worktree marker cannot be authenticated",
        ) from error
    if stat.S_ISDIR(marker_stat.st_mode):
        marker_is_directory = True
        if (
            git_dir != marker_path
            or _stat_identity(marker_stat) != directory_identities[git_dir]
            or _stat_identity(os.fstat(git_dir_fd)) != directory_identities[git_dir]
        ):
            raise LocalRepositorySafetyError(
                "discovery-path-mismatch",
                "Git worktree marker does not bind the admitted Git directory",
            )
    elif stat.S_ISREG(marker_stat.st_mode):
        marker_is_directory = False
        marker_binding, marker_payload = _bind_git_discovery_file(
            repository, repository_fd, ".git"
        )
        if _git_pointer_path(repository, marker_payload, marker=True) != git_dir:
            raise LocalRepositorySafetyError(
                "discovery-path-mismatch",
                "Git worktree marker does not bind the admitted Git directory",
            )
        files.append(marker_binding)
    else:
        raise LocalRepositorySafetyError(
            "discovery-file-unsafe", "Git worktree marker has an unsupported type"
        )

    commondir_path = git_dir / "commondir"
    if common_dir == git_dir:
        _require_discovery_file_absent(git_dir_fd, "commondir", commondir_path)
        absent.append((git_dir, "commondir", commondir_path))
    else:
        commondir_binding, commondir_payload = _bind_git_discovery_file(
            git_dir, git_dir_fd, "commondir"
        )
        if _git_pointer_path(git_dir, commondir_payload, marker=False) != common_dir:
            raise LocalRepositorySafetyError(
                "discovery-path-mismatch",
                "Git commondir does not bind the admitted common directory",
            )
        files.append(commondir_binding)

    back_pointer_path = git_dir / "gitdir"
    try:
        os.stat("gitdir", dir_fd=git_dir_fd, follow_symlinks=False)
    except FileNotFoundError:
        if common_dir != git_dir:
            raise LocalRepositorySafetyError(
                "discovery-file-unreadable",
                "linked Git worktree back-pointer is missing",
            ) from None
        absent.append((git_dir, "gitdir", back_pointer_path))
    except OSError as error:
        raise LocalRepositorySafetyError(
            "discovery-file-unreadable",
            "Git worktree back-pointer cannot be authenticated",
        ) from error
    else:
        back_pointer, back_pointer_payload = _bind_git_discovery_file(
            git_dir, git_dir_fd, "gitdir"
        )
        if (
            _git_pointer_path(git_dir, back_pointer_payload, marker=False)
            != marker_path
        ):
            raise LocalRepositorySafetyError(
                "discovery-path-mismatch",
                "Git worktree back-pointer does not bind the admitted marker",
            )
        files.append(back_pointer)
    return marker_is_directory, tuple(files), tuple(absent)


def _revalidate_repository_discovery(
    admission: LocalRepositoryAdmission,
    parent_descriptors: Mapping[Path, int],
) -> None:
    repository_fd = parent_descriptors[admission.repository]
    if admission.git_marker_is_directory:
        try:
            marker = os.stat(".git", dir_fd=repository_fd, follow_symlinks=False)
        except OSError as error:
            raise LocalRepositorySafetyError(
                "discovery-file-changed",
                "Git worktree marker changed after validation",
            ) from error
        expected = dict(admission.directory_identities)[admission.git_dir]
        if not stat.S_ISDIR(marker.st_mode) or _stat_identity(marker) != expected:
            raise LocalRepositorySafetyError(
                "discovery-file-changed",
                "Git worktree marker changed after validation",
            )
    for binding in admission.discovery_files:
        identity, payload = _read_git_discovery_file_at(
            parent_descriptors[binding.parent], binding.name, binding.path
        )
        if identity != binding.identity or not hmac.compare_digest(
            hashlib.sha256(payload).hexdigest(), binding.sha256
        ):
            raise LocalRepositorySafetyError(
                "discovery-file-changed",
                f"Git discovery file changed after validation: {binding.path}",
            )
    for parent, name, path in admission.absent_discovery_files:
        _require_discovery_file_absent(parent_descriptors[parent], name, path)


def _revalidate_command_binding(binding: LocalRepositoryCommandBinding) -> None:
    identities = dict(binding.admission.directory_identities)
    for path, descriptor in (
        (binding.admission.repository, binding.repository_fd),
        (binding.admission.git_dir, binding.git_dir_fd),
        (binding.admission.common_dir, binding.common_dir_fd),
        (binding.admission.object_store, binding.object_store_fd),
    ):
        try:
            metadata = safe_io.validate_owner_only_directory_descriptor(
                descriptor, path, exact_mode=False
            )
        except (OSError, safe_io.UnsafePathError) as exc:
            raise LocalRepositorySafetyError(
                "metadata-changed", "Git metadata changed after validation"
            ) from exc
        if _stat_identity(metadata) != identities[path]:
            raise LocalRepositorySafetyError(
                "metadata-changed", "Git metadata changed after validation"
            )
    _revalidate_repository_discovery(
        binding.admission,
        {
            binding.admission.repository: binding.repository_fd,
            binding.admission.git_dir: binding.git_dir_fd,
        },
    )
    if (
        _config_commitment(binding.common_dir_fd, binding.admission.config_path)
        != binding.admission.config_sha256
    ):
        raise LocalRepositorySafetyError(
            "config-changed", "local Git configuration changed after validation"
        )


@contextmanager
def bind_local_repository_command(
    admission: LocalRepositoryAdmission,
    directory_identity: DirectoryIdentity,
) -> Iterator[LocalRepositoryCommandBinding]:
    """Hold every admitted directory across one Git subprocess."""

    revalidate_local_repository(admission, directory_identity)
    expected = dict(admission.directory_identities)
    descriptors: list[int] = []
    primary: BaseException | None = None
    try:
        for path in (
            admission.repository,
            admission.git_dir,
            admission.common_dir,
            admission.object_store,
        ):
            descriptors.append(_open_bound_directory(path, expected[path]))
        binding = LocalRepositoryCommandBinding(admission, *descriptors)
        _revalidate_command_binding(binding)
        try:
            yield binding
        except BaseException as operation_error:
            try:
                _revalidate_command_binding(binding)
                revalidate_local_repository(admission, directory_identity)
            except BaseException as validation_error:
                raise validation_error from operation_error
            raise
        _revalidate_command_binding(binding)
        revalidate_local_repository(admission, directory_identity)
    except BaseException as error:
        primary = error
        raise
    finally:
        _close_descriptors(descriptors, "Git metadata", primary=primary)


@contextmanager
def repository_git_invocation(
    admission: LocalRepositoryAdmission | None,
    repository: Path,
    executable: str,
    arguments: Sequence[str],
    environment: Mapping[str, str],
    directory_identity: DirectoryIdentity,
) -> Iterator[tuple[tuple[str, ...], dict[str, str], tuple[int, ...]]]:
    """Build one bootstrap or descriptor-bound Git invocation."""

    if admission is None:
        yield (
            (executable, "-C", str(repository), *arguments),
            dict(environment),
            (),
        )
        return
    python_authority = executable_authority.resolve_executable(
        sys.executable, label="Python"
    )
    with executable_authority.executable_invocation(python_authority):
        with bind_local_repository_command(admission, directory_identity) as binding:
            bound_environment = dict(environment)
            if _BOUND_GIT_ENVIRONMENT_KEYS & bound_environment.keys():
                raise LocalRepositorySafetyError(
                    "discovery-environment-conflict",
                    "caller supplied a protected Git discovery environment key",
                )
            yield (
                binding.command(python_authority.path, executable, arguments),
                bound_environment,
                binding.descriptors,
            )


@contextmanager
def history_repository_git_invocation(
    admission: LocalRepositoryAdmission | None,
    repository: Path,
    executable: str,
    arguments: Sequence[str],
    environment: Mapping[str, str],
    directory_identity: DirectoryIdentity,
) -> Iterator[tuple[tuple[str, ...], dict[str, str], tuple[int, ...]]]:
    """Map descriptor-bound launch failures to the history API."""

    try:
        with repository_git_invocation(
            admission,
            repository,
            executable,
            arguments,
            environment,
            directory_identity,
        ) as invocation:
            yield invocation
    except (OSError, LocalRepositorySafetyError, safe_io.UnsafePathError) as error:
        raise HistoryValidationError(
            "history repository safety binding changed"
        ) from error


def local_only_git_environment() -> dict[str, str]:
    """Return process controls shared by all retained-history Git callers."""

    return {
        "GIT_ASKPASS": "/usr/bin/false",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_GRAFT_FILE": os.devnull,
        "GIT_LITERAL_PATHSPECS": "1",
        "GIT_NO_LAZY_FETCH": "1",
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_PAGER": "cat",
        "GIT_TERMINAL_PROMPT": "0",
        "PAGER": "cat",
        "SSH_ASKPASS": "/usr/bin/false",
    }


def history_git_environment(*, home: str, gnupg_home: str) -> dict[str, str]:
    """Return the complete environment for authenticated history reads."""

    return {
        **local_only_git_environment(),
        "HOME": home,
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": os.defpath,
        "TZ": "UTC",
        "GNUPGHOME": gnupg_home,
    }


def validate_complete_local_repository_commands(run: GitRunner) -> None:
    """Probe completeness without reading repository objects."""

    shallow = run(("rev-parse", "--is-shallow-repository"))
    config = run(("config", "--local", "--no-includes", "--name-only", "--list"))
    if shallow.returncode != 0 or config.returncode != 0:
        raise ValueError("repository completeness cannot be verified")
    validate_complete_local_repository(shallow.stdout, config.stdout)


def validate_complete_local_repository(
    shallow_output: bytes,
    local_config_keys_output: bytes,
) -> None:
    """Reject repository modes that may lazily obtain missing objects."""

    if shallow_output.strip() != b"false":
        raise ValueError("repository is shallow")
    try:
        keys = local_config_keys_output.decode("ascii").splitlines()
    except UnicodeDecodeError as error:
        raise ValueError("local Git configuration keys are not ASCII") from error
    if any(not key or "\x00" in key for key in keys):
        raise ValueError("local Git configuration keys are malformed")
    normalized = [key.casefold() for key in keys]
    if any(
        key == "include.path"
        or (key.startswith("includeif.") and key.endswith(".path"))
        or key == "extensions.worktreeconfig"
        for key in normalized
    ):
        raise ValueError("repository has unclosed local configuration sources")
    if any(
        key == "extensions.partialclone"
        or (
            key.startswith("remote.")
            and key.endswith((".promisor", ".partialclonefilter"))
        )
        for key in normalized
    ):
        raise ValueError("repository has promisor or partial-clone configuration")


def _absolute_git_path(run: GitRunner, option: str, *values: str) -> Path:
    result = run(("rev-parse", "--path-format=absolute", option, *values))
    path = Path(os.fsdecode(result.stdout).strip())
    if not all((result.returncode == 0, path.is_absolute())):
        raise LocalRepositorySafetyError(
            "metadata-path-invalid", "Git metadata path is invalid"
        )
    return path


def _reject_forbidden_metadata(entries: tuple[tuple[Path, str], ...]) -> None:
    for path, label in entries:
        try:
            path.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise LocalRepositorySafetyError(
                "metadata-unreadable", f"{label} cannot be authenticated"
            ) from exc
        raise LocalRepositorySafetyError(
            "forbidden-metadata", f"{label} are not allowed"
        )


def admit_local_repository(
    repository: Path,
    run: GitRunner,
    directory_identity: DirectoryIdentity,
) -> LocalRepositoryAdmission:
    """Authenticate one complete local worktree and its closed object store."""

    repository = repository.absolute()
    identities = [(repository, directory_identity(repository))]
    probe = run(("rev-parse", "--is-inside-work-tree"))
    if not all((probe.returncode == 0, probe.stdout.strip() == b"true")):
        raise LocalRepositorySafetyError(
            "not-worktree", "repository is not a Git work tree"
        )
    git_dir = _absolute_git_path(run, "--git-dir")
    common_dir = _absolute_git_path(run, "--git-common-dir")
    git_dir_relative = _closed_git_dir_relative(common_dir, git_dir)
    object_store = common_dir / "objects"
    if _absolute_git_path(run, "--git-path", "objects") != object_store:
        raise LocalRepositorySafetyError(
            "object-store-not-closed", "Git object store path is not closed"
        )
    shallow_path = common_dir / "shallow"
    if _absolute_git_path(run, "--git-path", "shallow") != shallow_path:
        raise LocalRepositorySafetyError(
            "shallow-path-not-closed", "Git shallow boundary path is not closed"
        )
    identities.extend(
        map(
            lambda path: (path, directory_identity(path)),
            (git_dir, common_dir, object_store),
        )
    )
    forbidden_by_path = {
        object_store / "info" / "alternates": "Git object alternates",
        common_dir / "info" / "grafts": "Git grafts",
        common_dir / "config.worktree": "Git worktree configurations",
        git_dir / "config.worktree": "Git worktree configurations",
        shallow_path: "Git shallow boundaries",
    }
    forbidden = tuple(forbidden_by_path.items())
    _reject_forbidden_metadata(forbidden)
    try:
        validate_complete_local_repository_commands(run)
    except ValueError as exc:
        raise LocalRepositorySafetyError(
            "incomplete", "repository must be complete and non-promisor"
        ) from exc
    expected = dict(identities)
    descriptors: list[int] = []
    primary: BaseException | None = None
    try:
        repository_fd = _open_bound_directory(repository, expected[repository])
        descriptors.append(repository_fd)
        git_dir_fd = _open_bound_directory(git_dir, expected[git_dir])
        descriptors.append(git_dir_fd)
        common_dir_fd = _open_bound_directory(common_dir, expected[common_dir])
        descriptors.append(common_dir_fd)
        (
            git_marker_is_directory,
            discovery_files,
            absent_discovery_files,
        ) = _admit_repository_discovery(
            repository=repository,
            repository_fd=repository_fd,
            git_dir=git_dir,
            git_dir_fd=git_dir_fd,
            common_dir=common_dir,
            directory_identities=expected,
        )
        config_path = common_dir / "config"
        config_sha256 = _config_commitment(common_dir_fd, config_path)
    except BaseException as error:
        primary = error
        raise
    finally:
        _close_descriptors(descriptors, "Git admission", primary=primary)
    admission = LocalRepositoryAdmission(
        repository=repository,
        git_dir=git_dir,
        common_dir=common_dir,
        object_store=object_store,
        directory_identities=tuple(identities),
        forbidden_metadata=forbidden,
        config_path=config_path,
        config_sha256=config_sha256,
        git_dir_relative=git_dir_relative,
        git_marker_is_directory=git_marker_is_directory,
        discovery_files=discovery_files,
        absent_discovery_files=absent_discovery_files,
    )
    revalidate_local_repository(admission, directory_identity)
    return admission


def revalidate_local_repository(
    admission: LocalRepositoryAdmission,
    directory_identity: DirectoryIdentity,
) -> None:
    """Recheck the admitted filesystem objects before each history Git call."""

    for path, expected in admission.directory_identities:
        if directory_identity(path) != expected:
            raise LocalRepositorySafetyError(
                "metadata-changed", "Git metadata changed after validation"
            )
    _reject_forbidden_metadata(admission.forbidden_metadata)
    expected = dict(admission.directory_identities)
    descriptors: list[int] = []
    primary: BaseException | None = None
    try:
        repository_fd = _open_bound_directory(
            admission.repository, expected[admission.repository]
        )
        descriptors.append(repository_fd)
        git_dir_fd = _open_bound_directory(
            admission.git_dir, expected[admission.git_dir]
        )
        descriptors.append(git_dir_fd)
        common_dir_fd = _open_bound_directory(
            admission.common_dir, expected[admission.common_dir]
        )
        descriptors.append(common_dir_fd)
        _revalidate_repository_discovery(
            admission,
            {
                admission.repository: repository_fd,
                admission.git_dir: git_dir_fd,
            },
        )
        if (
            _config_commitment(common_dir_fd, admission.config_path)
            != admission.config_sha256
        ):
            raise LocalRepositorySafetyError(
                "config-changed", "local Git configuration changed after validation"
            )
    except BaseException as error:
        primary = error
        raise
    finally:
        _close_descriptors(descriptors, "Git revalidation", primary=primary)


def admit_history_repository(
    repository: Path,
    run: GitRunner,
    directory_identity: DirectoryIdentity,
) -> LocalRepositoryAdmission:
    """Map shared admission failures to the durable-history API."""

    try:
        return admit_local_repository(repository, run, directory_identity)
    except (OSError, ValueError) as error:
        message = {
            "incomplete": "history repository must be complete and non-promisor"
        }.get(
            getattr(error, "reason", None),
            "history repository failed local safety admission",
        )
        raise HistoryValidationError(message) from error


def revalidate_history_repository(
    admission: LocalRepositoryAdmission | None,
    directory_identity: DirectoryIdentity,
) -> None:
    """Map shared revalidation failures to the durable-history API."""

    if admission is None:
        return
    try:
        revalidate_local_repository(admission, directory_identity)
    except (OSError, ValueError) as error:
        raise HistoryValidationError(
            "history repository safety binding changed"
        ) from error
