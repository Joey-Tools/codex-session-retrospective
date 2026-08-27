"""Descriptor-bound automation records and their production contract."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import os
from pathlib import Path
import shlex
import stat
from typing import Mapping, Sequence

from . import executable_authority, safe_io
from .authority_errors import AutomationCutoverBlocked


_AUTOMATION_ACCESS_POLICY_FLAG_MASK = 0x001E0096  # BSD write/delete restrictions.
_WEEKDAYS = frozenset({"MO", "TU", "WE", "TH", "FR", "SA", "SU"})
_PUBLISHER_GPG_PROMPT_PREFIX = "Authenticated publisher GPG executable: "


def _access_policy_flags(metadata: os.stat_result) -> int:
    return int(getattr(metadata, "st_flags", 0)) & _AUTOMATION_ACCESS_POLICY_FLAG_MASK


def _directory_identity(metadata: os.stat_result) -> tuple[int, ...]:
    return (
        int(metadata.st_dev),
        int(metadata.st_ino),
        int(metadata.st_uid),
        int(metadata.st_gid),
        int(stat.S_IFMT(metadata.st_mode)),
        int(stat.S_IMODE(metadata.st_mode)),
        _access_policy_flags(metadata),
    )


def _file_identity(metadata: os.stat_result) -> tuple[int, ...]:
    return (
        *_directory_identity(metadata),
        int(metadata.st_nlink),
        int(metadata.st_size),
    )


def _close_descriptors(
    descriptors: Sequence[int],
    *,
    label: str,
    primary: BaseException | None = None,
) -> None:
    failures: list[OSError] = []
    for descriptor in reversed(descriptors):
        try:
            os.close(descriptor)
        except OSError as exc:
            failures.append(exc)
    if not failures:
        return
    message = f"{label} descriptor close failed"
    if primary is not None:
        primary.add_note(message)
        return
    raise AutomationCutoverBlocked(message) from failures[0]


def build_production_prompt(
    *,
    cli_path: Path,
    python_path: Path,
    expected_mode: str,
    publisher_gpg_program: str,
    provider_state_path: Path,
    production_marker_path: Path,
) -> str:
    if expected_mode not in {"daily", "weekly"}:
        raise ValueError("production automation mode is invalid")
    for value in (str(python_path), str(cli_path), publisher_gpg_program):
        if not executable_authority.is_canonical_absolute_executable_path(value):
            raise ValueError("production automation executable path is invalid")
    for value in (str(provider_state_path), str(production_marker_path)):
        if any(ord(character) < 0x20 or ord(character) == 0x7F for character in value):
            raise ValueError(
                "production automation authority path contains control characters"
            )
        if not executable_authority.is_canonical_absolute_executable_path(value):
            raise ValueError("production automation authority path is invalid")
    authority_argv = shlex.join((str(python_path), "-I", "-B", "-S", str(cli_path)))
    return "\n".join(
        (
            "Run $codex-session-retrospective as the exact "
            f"{expected_mode} production coordinator.",
            f"Authenticated coordinator argv prefix: {authority_argv}",
            _PUBLISHER_GPG_PROMPT_PREFIX + shlex.quote(publisher_gpg_program),
            "Derive the exact UTC --start and --end production window and bind "
            "owner-private --run-dir, immutable --run-config, append-only "
            "--history-repo, and fully qualified --history-target-ref before "
            "invoking either stage.",
            "Invoke doctor with --run-config, --history-repo, "
            "--history-target-ref, --publisher-gpg-program "
            f"{shlex.quote(publisher_gpg_program)}, --provider-state "
            f"{shlex.quote(str(provider_state_path))}, and --production-marker "
            f"{shlex.quote(str(production_marker_path))}.",
            f"Invoke start with --mode {expected_mode}, --start, --end, "
            "--run-dir, --run-config, --history-repo, --history-target-ref, "
            "--publisher-gpg-program "
            f"{shlex.quote(publisher_gpg_program)}, --provider-state "
            f"{shlex.quote(str(provider_state_path))} and --production-marker "
            f"{shlex.quote(str(production_marker_path))}.",
            "Repeat status; execute every listed native_coordinator_actions "
            "command exactly once, verbatim, and in listed order, honoring each "
            "stdout_path, including each run-owned accept-source command; use "
            "$remote-host-context session-shards only when that action explicitly "
            "requires it; spawn the maximum available native subagent wave -> "
            "accept-agent-result -> advance until exportable; then export and "
            "repeat finalize until terminal.",
            "Do not stop after start and do not ask Joey to invoke intermediate "
            "stages.",
        )
    )


def production_prompt_is_closed(
    prompt: str,
    *,
    cli_path: Path,
    python_path: Path,
    expected_mode: str,
    publisher_gpg_program: str,
    provider_state_path: Path,
    production_marker_path: Path,
) -> bool:
    try:
        lines = prompt.splitlines()
        if len(lines) != 8:
            return False
        expected = build_production_prompt(
            cli_path=cli_path,
            python_path=python_path,
            expected_mode=expected_mode,
            publisher_gpg_program=publisher_gpg_program,
            provider_state_path=provider_state_path,
            production_marker_path=production_marker_path,
        )
        return hmac.compare_digest(prompt.encode("utf-8"), expected.encode("utf-8"))
    except (UnicodeEncodeError, ValueError, IndexError):
        return False


def production_document_is_closed(
    document: Mapping[str, object],
    *,
    automation_id: str,
    cli_path: Path,
    python_path: Path,
    expected_mode: str,
    publisher_gpg_program: str,
    provider_state_path: Path,
    production_marker_path: Path,
) -> bool:
    expected_fields = {"version", "id", "kind", "name", "prompt", "status", "rrule"}
    prompt = document.get("prompt")
    schedule = document.get("rrule")
    return (
        set(document) == expected_fields
        and type(document.get("version")) is int
        and document.get("version") == 1
        and document.get("id") == automation_id
        and document.get("kind") == "cron"
        and document.get("name") == f"Session Retrospective {expected_mode.title()}"
        and document.get("status") == "ACTIVE"
        and isinstance(prompt, str)
        and production_prompt_is_closed(
            prompt,
            cli_path=cli_path,
            python_path=python_path,
            expected_mode=expected_mode,
            publisher_gpg_program=publisher_gpg_program,
            provider_state_path=provider_state_path,
            production_marker_path=production_marker_path,
        )
        and isinstance(schedule, str)
        and production_rrule_is_closed(schedule, expected_mode=expected_mode)
    )


def production_rrule_is_closed(rrule: str, *, expected_mode: str) -> bool:
    components: dict[str, str] = {}
    for field in rrule.split(";"):
        if field.count("=") != 1:
            return False
        key, value = field.split("=", 1)
        if not key or not value or key != key.upper() or key in components:
            return False
        components[key] = value
    allowed = {"FREQ", "INTERVAL", "BYHOUR", "BYMINUTE", "BYSECOND"}
    if expected_mode == "weekly":
        allowed.add("BYDAY")
    expected_frequency = "DAILY" if expected_mode == "daily" else "WEEKLY"
    if (
        set(components) - allowed
        or components.get("FREQ") != expected_frequency
        or components.get("INTERVAL", "1") != "1"
    ):
        return False
    for key, upper_bound in (("BYHOUR", 23), ("BYMINUTE", 59), ("BYSECOND", 59)):
        value = components.get(key)
        if value is not None and (
            not value.isascii()
            or not value.isdecimal()
            or str(int(value)) != value
            or not 0 <= int(value) <= upper_bound
        ):
            return False
    return "BYDAY" not in components or components["BYDAY"] in _WEEKDAYS


def _validate_directory_descriptor(
    descriptor: int,
    display_path: Path,
) -> tuple[tuple[int, ...], bytes]:
    try:
        metadata = safe_io.validate_owner_only_directory_descriptor(
            descriptor,
            display_path,
            exact_mode=False,
        )
        acl_policy = safe_io.descriptor_acl_policy_bytes(descriptor)
    except (OSError, ValueError) as exc:
        raise AutomationCutoverBlocked(
            "automation directory ownership or access policy is invalid"
        ) from exc
    identity = _directory_identity(metadata)
    if acl_policy or _access_policy_flags(metadata):
        raise AutomationCutoverBlocked(
            "automation directory ownership or access policy is invalid"
        )
    return identity, acl_policy


def _validate_file_descriptor(
    descriptor: int,
    display_path: Path,
    *,
    max_bytes: int,
) -> tuple[tuple[int, ...], bytes]:
    try:
        metadata = os.fstat(descriptor)
        acl_policy = safe_io.descriptor_acl_policy_bytes(descriptor)
    except (OSError, ValueError) as exc:
        raise AutomationCutoverBlocked(
            "automation record ownership or access policy is invalid"
        ) from exc
    identity = _file_identity(metadata)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) & 0o022
        or metadata.st_nlink != 1
        or metadata.st_size > max_bytes
        or acl_policy
        or _access_policy_flags(metadata)
    ):
        raise AutomationCutoverBlocked(
            "automation record ownership or access policy is invalid"
        )
    return identity, acl_policy


def _read_record_pass(
    descriptor: int,
    *,
    display_path: Path,
    max_bytes: int,
) -> tuple[bytes, str]:
    try:
        os.lseek(descriptor, 0, os.SEEK_SET)
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(
                descriptor,
                min(64 * 1024, max_bytes - total + 1),
            )
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > max_bytes:
                raise AutomationCutoverBlocked("automation record exceeds byte limit")
    except OSError as exc:
        raise AutomationCutoverBlocked(
            f"automation record could not be read: {display_path}"
        ) from exc
    raw = b"".join(chunks)
    return raw, hashlib.sha256(raw).hexdigest()


@dataclass(slots=True)
class AutomationRootBinding:
    path: Path
    descriptor: int
    identity: tuple[int, ...]
    acl_policy: bytes
    max_record_bytes: int

    def revalidate(self) -> None:
        identity, acl_policy = _validate_directory_descriptor(
            self.descriptor,
            self.path,
        )
        try:
            named = os.stat(self.path, follow_symlinks=False)
        except OSError as exc:
            raise AutomationCutoverBlocked(
                "automation root identity is unavailable"
            ) from exc
        if (
            identity != self.identity
            or _directory_identity(named) != self.identity
            or not hmac.compare_digest(acl_policy, self.acl_policy)
        ):
            raise AutomationCutoverBlocked("automation root identity changed")

    def close(self, *, primary: BaseException | None = None) -> None:
        descriptor, self.descriptor = self.descriptor, -1
        if descriptor != -1:
            _close_descriptors((descriptor,), label="automation root", primary=primary)


@dataclass(slots=True)
class AutomationRecordBinding:
    root: AutomationRootBinding
    automation_id: str
    directory_path: Path
    directory_descriptor: int
    directory_identity: tuple[int, ...]
    directory_acl_policy: bytes
    record_path: Path
    record_descriptor: int
    record_identity: tuple[int, ...]
    record_acl_policy: bytes
    raw: bytes
    sha256: str

    def revalidate_navigation(self) -> None:
        self.root.revalidate()
        directory_identity, directory_acl = _validate_directory_descriptor(
            self.directory_descriptor,
            self.directory_path,
        )
        record_identity, record_acl = _validate_file_descriptor(
            self.record_descriptor,
            self.record_path,
            max_bytes=self.root.max_record_bytes,
        )
        try:
            named_directory = os.stat(
                self.automation_id,
                dir_fd=self.root.descriptor,
                follow_symlinks=False,
            )
            named_record = os.stat(
                "automation.toml",
                dir_fd=self.directory_descriptor,
                follow_symlinks=False,
            )
        except OSError as exc:
            raise AutomationCutoverBlocked(
                "automation record path identity is unavailable"
            ) from exc
        if (
            directory_identity != self.directory_identity
            or _directory_identity(named_directory) != self.directory_identity
            or record_identity != self.record_identity
            or _file_identity(named_record) != self.record_identity
            or not hmac.compare_digest(directory_acl, self.directory_acl_policy)
            or not hmac.compare_digest(record_acl, self.record_acl_policy)
        ):
            raise AutomationCutoverBlocked(
                "automation record path identity or access policy changed"
            )

    def revalidate(self) -> None:
        self.revalidate_navigation()
        first_raw, first_digest = _read_record_pass(
            self.record_descriptor,
            display_path=self.record_path,
            max_bytes=self.root.max_record_bytes,
        )
        middle_identity, middle_acl = _validate_file_descriptor(
            self.record_descriptor,
            self.record_path,
            max_bytes=self.root.max_record_bytes,
        )
        second_raw, second_digest = _read_record_pass(
            self.record_descriptor,
            display_path=self.record_path,
            max_bytes=self.root.max_record_bytes,
        )
        self.revalidate_navigation()
        if (
            middle_identity != self.record_identity
            or not hmac.compare_digest(middle_acl, self.record_acl_policy)
            or first_raw != self.raw
            or second_raw != self.raw
            or not hmac.compare_digest(first_digest, self.sha256)
            or not hmac.compare_digest(second_digest, self.sha256)
        ):
            raise AutomationCutoverBlocked(
                "automation record content changed while it was authenticated"
            )

    def close(self, *, primary: BaseException | None = None) -> None:
        descriptors = (self.directory_descriptor, self.record_descriptor)
        self.directory_descriptor = -1
        self.record_descriptor = -1
        _close_descriptors(
            tuple(descriptor for descriptor in descriptors if descriptor != -1),
            label="automation record",
            primary=primary,
        )


def validate_automation_root(automation_root: Path) -> Path:
    try:
        candidate = automation_root.expanduser().absolute()
        candidate_metadata = candidate.stat(follow_symlinks=False)
        if stat.S_ISLNK(candidate_metadata.st_mode):
            raise AutomationCutoverBlocked("automation root uses a symlink")
        normalized = candidate.resolve(strict=True)
        metadata = normalized.stat(follow_symlinks=False)
    except (OSError, RuntimeError) as exc:
        raise AutomationCutoverBlocked(
            "automation root is unavailable or invalid"
        ) from exc
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) & 0o022
    ):
        raise AutomationCutoverBlocked("automation root ownership is invalid")
    return normalized


def open_automation_root(
    automation_root: Path,
    *,
    max_record_bytes: int,
) -> AutomationRootBinding:
    normalized = validate_automation_root(automation_root)
    descriptor: int | None = None
    try:
        opened_path, descriptor = safe_io.open_owner_controlled_directory(normalized)
        identity, acl_policy = _validate_directory_descriptor(descriptor, opened_path)
        binding = AutomationRootBinding(
            path=opened_path,
            descriptor=descriptor,
            identity=identity,
            acl_policy=acl_policy,
            max_record_bytes=max_record_bytes,
        )
        binding.revalidate()
        return binding
    except BaseException as exc:
        if descriptor is not None:
            _close_descriptors((descriptor,), label="automation root", primary=exc)
        if isinstance(exc, AutomationCutoverBlocked):
            raise
        raise AutomationCutoverBlocked(
            "automation root is unavailable or invalid"
        ) from exc


def open_automation_record_binding(
    root: AutomationRootBinding,
    automation_id: str,
) -> AutomationRecordBinding:
    directory_path = root.path / automation_id
    record_path = directory_path / "automation.toml"
    directory_descriptor: int | None = None
    record_descriptor: int | None = None
    try:
        directory_descriptor = os.open(
            automation_id,
            os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=root.descriptor,
        )
        directory_identity, directory_acl = _validate_directory_descriptor(
            directory_descriptor,
            directory_path,
        )
        named_directory = os.stat(
            automation_id,
            dir_fd=root.descriptor,
            follow_symlinks=False,
        )
        if _directory_identity(named_directory) != directory_identity:
            raise AutomationCutoverBlocked(
                "automation directory identity changed while it was opened"
            )
        record_descriptor = os.open(
            "automation.toml",
            os.O_RDONLY
            | os.O_CLOEXEC
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0),
            dir_fd=directory_descriptor,
        )
        record_identity, record_acl = _validate_file_descriptor(
            record_descriptor,
            record_path,
            max_bytes=root.max_record_bytes,
        )
        named_record = os.stat(
            "automation.toml",
            dir_fd=directory_descriptor,
            follow_symlinks=False,
        )
        if _file_identity(named_record) != record_identity:
            raise AutomationCutoverBlocked(
                "automation record identity changed while it was opened"
            )
        first_raw, first_digest = _read_record_pass(
            record_descriptor,
            display_path=record_path,
            max_bytes=root.max_record_bytes,
        )
        middle_identity, middle_acl = _validate_file_descriptor(
            record_descriptor,
            record_path,
            max_bytes=root.max_record_bytes,
        )
        second_raw, second_digest = _read_record_pass(
            record_descriptor,
            display_path=record_path,
            max_bytes=root.max_record_bytes,
        )
        if (
            middle_identity != record_identity
            or not hmac.compare_digest(middle_acl, record_acl)
            or first_raw != second_raw
            or not hmac.compare_digest(first_digest, second_digest)
        ):
            raise AutomationCutoverBlocked(
                "automation record content changed while it was read"
            )
        binding = AutomationRecordBinding(
            root=root,
            automation_id=automation_id,
            directory_path=directory_path,
            directory_descriptor=directory_descriptor,
            directory_identity=directory_identity,
            directory_acl_policy=directory_acl,
            record_path=record_path,
            record_descriptor=record_descriptor,
            record_identity=record_identity,
            record_acl_policy=record_acl,
            raw=first_raw,
            sha256=first_digest,
        )
        binding.revalidate_navigation()
        return binding
    except BaseException as exc:
        _close_descriptors(
            tuple(
                descriptor
                for descriptor in (directory_descriptor, record_descriptor)
                if descriptor is not None
            ),
            label="automation record",
            primary=exc,
        )
        raise


def close_automation_bindings(
    root: AutomationRootBinding,
    bindings: Sequence[AutomationRecordBinding],
    *,
    primary: BaseException | None = None,
) -> None:
    descriptors = [root.descriptor]
    root.descriptor = -1
    for binding in bindings:
        descriptors.extend((binding.directory_descriptor, binding.record_descriptor))
        binding.directory_descriptor = -1
        binding.record_descriptor = -1
    _close_descriptors(
        tuple(descriptor for descriptor in descriptors if descriptor != -1),
        label="automation authority",
        primary=primary,
    )


def read_installed_automation_bytes(
    record_path: Path,
    *,
    automation_root: Path,
    max_record_bytes: int,
) -> bytes:
    root: AutomationRootBinding | None = None
    binding: AutomationRecordBinding | None = None
    primary: BaseException | None = None
    try:
        root = open_automation_root(
            automation_root,
            max_record_bytes=max_record_bytes,
        )
        binding = open_automation_record_binding(root, record_path.parent.name)
        if binding.record_path != record_path:
            raise AutomationCutoverBlocked("automation record path is invalid")
        binding.revalidate()
        return binding.raw
    except (OSError, RuntimeError) as exc:
        primary = AutomationCutoverBlocked(
            "required automation record is unavailable or invalid"
        )
        raise primary from exc
    except BaseException as exc:
        primary = exc
        raise
    finally:
        if root is not None:
            close_automation_bindings(
                root,
                () if binding is None else (binding,),
                primary=primary,
            )
