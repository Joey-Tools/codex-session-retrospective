"""Stable account and home binding for remote transport authentication."""

from __future__ import annotations

import base64
from dataclasses import asdict, dataclass
import hashlib
import hmac
import json
import os
from pathlib import Path
import pwd
import stat
from typing import Any, Mapping

try:
    from . import safe_io
    from .transport_contracts import TransportValidationError
except (ImportError, ModuleNotFoundError):
    import safe_io  # type: ignore[no-redef]
    from transport_contracts import TransportValidationError  # type: ignore[no-redef]


REMOTE_HOST_CONTEXT_ACCOUNT_BINDING_OPTION = "--remote-account-binding"
REMOTE_HOST_CONTEXT_ACCOUNT_BINDING_SCHEMA = "remote_host_context_account_v1"
_ACCOUNT_BINDING_FIELDS = frozenset(
    {
        "account_gid",
        "account_name",
        "account_uid",
        "home",
        "home_acl_sha256",
        "home_device",
        "home_generation",
        "home_group",
        "home_inode",
        "home_mode",
        "home_owner",
        "home_policy_flags",
        "schema",
    }
)


def _stat_value(metadata: os.stat_result, name: str, default: int) -> int:
    value = getattr(metadata, name, default)
    return int(value) if type(value) is int else default


def _home_metadata(metadata: os.stat_result) -> tuple[int, ...]:
    return (
        int(metadata.st_dev),
        int(metadata.st_ino),
        int(metadata.st_mode),
        int(metadata.st_uid),
        int(metadata.st_gid),
        safe_io.directory_access_policy_flags(metadata),
        _stat_value(metadata, "st_gen", -1),
    )


def _observe_home(path: Path) -> tuple[tuple[int, ...], str]:
    normalized, descriptor = safe_io.open_owner_controlled_directory_with_bound_acl(
        path
    )
    active_error: BaseException | None = None
    try:
        before = os.fstat(descriptor)
        acl_sha256 = hashlib.sha256(
            safe_io.descriptor_acl_policy_bytes(descriptor)
        ).hexdigest()
        after = os.fstat(descriptor)
        path_metadata = os.stat(normalized, follow_symlinks=False)
        if _home_metadata(before) != _home_metadata(after) or _home_metadata(
            after
        ) != _home_metadata(path_metadata):
            raise TransportValidationError(
                "remote-host-context account home changed while observed"
            )
        return _home_metadata(after), acl_sha256
    except BaseException as exc:
        active_error = exc
        raise
    finally:
        try:
            os.close(descriptor)
        except OSError as close_error:
            if active_error is None:
                raise
            active_error.add_note(
                "remote-host-context account home descriptor close failed: "
                f"{close_error}"
            )


def _valid_account_name(value: object) -> bool:
    return (
        isinstance(value, str)
        and 0 < len(value.encode("utf-8")) <= 255
        and not any(character in value for character in ("\x00", "\r", "\n"))
    )


def _canonical_home(value: object) -> Path:
    if (
        not isinstance(value, str)
        or not value
        or any(character in value for character in ("\x00", "\r", "\n"))
    ):
        raise TransportValidationError(
            "remote-host-context account home binding is invalid"
        )
    path = Path(value)
    if not path.is_absolute() or os.path.normpath(value) != value:
        raise TransportValidationError(
            "remote-host-context account home binding is invalid"
        )
    return path


@dataclass(frozen=True, slots=True)
class RemoteHostContextAccountSnapshot:
    schema: str
    account_name: str
    account_uid: int
    account_gid: int
    home: str
    home_device: int
    home_inode: int
    home_mode: int
    home_owner: int
    home_group: int
    home_policy_flags: int
    home_generation: int
    home_acl_sha256: str

    def __post_init__(self) -> None:
        if self.schema != REMOTE_HOST_CONTEXT_ACCOUNT_BINDING_SCHEMA:
            raise TransportValidationError(
                "remote-host-context account binding schema is invalid"
            )
        if not _valid_account_name(self.account_name):
            raise TransportValidationError(
                "remote-host-context account name binding is invalid"
            )
        _canonical_home(self.home)
        for field in (
            "account_uid",
            "account_gid",
            "home_device",
            "home_inode",
            "home_mode",
            "home_owner",
            "home_group",
            "home_policy_flags",
        ):
            value = getattr(self, field)
            if type(value) is not int or value < 0:
                raise TransportValidationError(
                    "remote-host-context account identity binding is invalid"
                )
        if type(self.home_generation) is not int or self.home_generation < -1:
            raise TransportValidationError(
                "remote-host-context account identity binding is invalid"
            )
        if (
            len(self.home_acl_sha256) != 64
            or any(
                character not in "0123456789abcdef"
                for character in self.home_acl_sha256
            )
            or not stat.S_ISDIR(self.home_mode)
            or self.home_owner != self.account_uid
        ):
            raise TransportValidationError(
                "remote-host-context account home policy binding is invalid"
            )

    @property
    def home_path(self) -> Path:
        return Path(self.home)

    def to_argument(self) -> str:
        payload = json.dumps(
            asdict(self), ensure_ascii=True, separators=(",", ":"), sort_keys=True
        ).encode("ascii")
        return base64.urlsafe_b64encode(payload).decode("ascii")

    def revalidate(self) -> None:
        try:
            observed = remote_host_context_account_snapshot()
        except RuntimeError as exc:
            raise TransportValidationError(
                "remote-host-context account or home binding changed"
            ) from exc
        if not hmac.compare_digest(self.to_argument(), observed.to_argument()):
            raise TransportValidationError(
                "remote-host-context account or home binding changed"
            )


def remote_host_context_account_snapshot() -> RemoteHostContextAccountSnapshot:
    account_uid = os.getuid()
    try:
        account = pwd.getpwuid(account_uid)
    except (KeyError, OSError) as exc:
        raise RuntimeError("remote-host-context account identity unavailable") from exc
    account_name = getattr(account, "pw_name", None)
    account_gid = getattr(account, "pw_gid", None)
    declared_uid = getattr(account, "pw_uid", None)
    raw_home = getattr(account, "pw_dir", None)
    if (
        not _valid_account_name(account_name)
        or type(account_gid) is not int
        or account_gid < 0
        or declared_uid != account_uid
        or not isinstance(raw_home, str)
        or not raw_home
        or not Path(raw_home).is_absolute()
    ):
        raise RuntimeError("remote-host-context account identity unavailable")
    try:
        home = Path(raw_home).resolve(strict=True)
        metadata, acl_sha256 = _observe_home(home)
    except (OSError, TransportValidationError, safe_io.UnsafePathError) as exc:
        raise RuntimeError("remote-host-context account home is invalid") from exc
    return RemoteHostContextAccountSnapshot(
        schema=REMOTE_HOST_CONTEXT_ACCOUNT_BINDING_SCHEMA,
        account_name=account_name,
        account_uid=account_uid,
        account_gid=account_gid,
        home=str(home),
        home_device=metadata[0],
        home_inode=metadata[1],
        home_mode=metadata[2],
        home_owner=metadata[3],
        home_group=metadata[4],
        home_policy_flags=metadata[5],
        home_generation=metadata[6],
        home_acl_sha256=acl_sha256,
    )


def parse_remote_host_context_account_binding(
    value: object,
) -> RemoteHostContextAccountSnapshot:
    if not isinstance(value, str) or not value or len(value) > 4096:
        raise TransportValidationError("remote-host-context account binding is invalid")
    try:
        payload = base64.b64decode(value, altchars=b"-_", validate=True)
        if not hmac.compare_digest(
            base64.urlsafe_b64encode(payload).decode("ascii"), value
        ):
            raise ValueError("noncanonical account binding")
        decoded: Any = json.loads(payload.decode("ascii"))
        if not isinstance(decoded, Mapping) or set(decoded) != _ACCOUNT_BINDING_FIELDS:
            raise ValueError("invalid account binding fields")
        return RemoteHostContextAccountSnapshot(**dict(decoded))
    except (TypeError, ValueError, UnicodeError) as exc:
        raise TransportValidationError(
            "remote-host-context account binding is invalid"
        ) from exc
