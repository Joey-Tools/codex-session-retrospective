"""Static host inventory derived from authenticated remote helper source bytes."""

from __future__ import annotations

import ast
import hashlib
from dataclasses import dataclass
from pathlib import PurePosixPath
import re
from typing import Any, Mapping

try:
    from .contracts import MAX_RUN_HOSTS, canonical_json_bytes
except (ImportError, ModuleNotFoundError):
    from contracts import (  # type: ignore[no-redef]
        MAX_RUN_HOSTS,
        canonical_json_bytes,
    )


HOST_INVENTORY_SCHEMA = "remote_host_context_host_inventory_v1"
HOST_INVENTORY_COMMITMENT_DOMAIN = (
    b"codex-session-retrospective/remote-host-context-host-inventory/v1\x00"
)
MAX_HOST_INVENTORY_CANONICAL_ENTRIES = MAX_RUN_HOSTS
MAX_HOST_INVENTORY_ALIASES = 32
MAX_HOST_INVENTORY_KEYS = (
    MAX_HOST_INVENTORY_CANONICAL_ENTRIES + MAX_HOST_INVENTORY_ALIASES
)
MAX_REMOTE_HOST_CONTEXT_HELPER_BYTES = 4 * 1024 * 1024
MAX_REMOTE_HOST_CONTEXT_HELPER_AST_NODES = 100_000
MAX_HOST_KEY_BYTES = 128
MAX_HOST_TARGET_BYTES = 255
MAX_CODEX_ROOT_BYTES = 4096

_HOST_KEY_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")
_HOST_TARGET_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,254}\Z")
_COMMITMENT_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")


class HostInventoryError(ValueError):
    """Raised when helper source or a retained inventory is not closed and valid."""


def _bounded_token(value: object, *, label: str, target: bool = False) -> str:
    pattern = _HOST_TARGET_RE if target else _HOST_KEY_RE
    maximum = MAX_HOST_TARGET_BYTES if target else MAX_HOST_KEY_BYTES
    if (
        not isinstance(value, str)
        or not value
        or len(value.encode("utf-8")) > maximum
        or pattern.fullmatch(value) is None
    ):
        raise HostInventoryError(f"{label} is invalid")
    return value


def _normalized_root(value: object, *, role: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value.encode("utf-8")) > MAX_CODEX_ROOT_BYTES
        or "\\" in value
        or any(ord(character) < 0x20 for character in value)
    ):
        raise HostInventoryError("host codex_root is invalid")
    if value.startswith("~/") and role == "local":
        suffix = value[2:]
        if not suffix or PurePosixPath(suffix).as_posix() != suffix:
            raise HostInventoryError("local host codex_root is not canonical")
        parts = PurePosixPath(suffix).parts
    elif value.startswith("/"):
        if value == "/" or PurePosixPath(value).as_posix() != value:
            raise HostInventoryError("host codex_root is not canonical")
        parts = PurePosixPath(value).parts[1:]
    else:
        raise HostInventoryError(
            "host codex_root must be absolute or local-home rooted"
        )
    if any(part in {"", ".", ".."} for part in parts):
        raise HostInventoryError("host codex_root contains an unsafe component")
    if role == "remote" and not value.startswith("/"):
        raise HostInventoryError("remote host codex_root must be absolute")
    return value


@dataclass(frozen=True, slots=True)
class CanonicalHost:
    host: str
    role: str
    codex_root: str
    transport_target: str | None

    def __post_init__(self) -> None:
        _bounded_token(self.host, label="canonical host")
        if self.role not in {"local", "remote"}:
            raise HostInventoryError("canonical host role is invalid")
        _normalized_root(self.codex_root, role=self.role)
        if self.role == "local":
            if self.transport_target is not None:
                raise HostInventoryError("local host cannot have a transport target")
        else:
            _bounded_token(
                self.transport_target,
                label="remote host transport target",
                target=True,
            )

    def to_dict(self) -> dict[str, str | None]:
        return {
            "codex_root": self.codex_root,
            "host": self.host,
            "role": self.role,
            "transport_target": self.transport_target,
        }


@dataclass(frozen=True, slots=True)
class HostAlias:
    alias: str
    canonical_host: str

    def __post_init__(self) -> None:
        _bounded_token(self.alias, label="host alias")
        _bounded_token(self.canonical_host, label="alias canonical host")
        if self.alias == self.canonical_host:
            raise HostInventoryError("host alias cannot equal its canonical host")

    def to_dict(self) -> dict[str, str]:
        return {"alias": self.alias, "canonical_host": self.canonical_host}


@dataclass(frozen=True, slots=True)
class HostInventory:
    canonical_entries: tuple[CanonicalHost, ...]
    aliases: tuple[HostAlias, ...]

    def __post_init__(self) -> None:
        if not 1 <= len(self.canonical_entries) <= MAX_HOST_INVENTORY_CANONICAL_ENTRIES:
            raise HostInventoryError("canonical host inventory size is invalid")
        if len(self.aliases) > MAX_HOST_INVENTORY_ALIASES:
            raise HostInventoryError("host alias inventory exceeds its bound")
        canonical_names = tuple(item.host for item in self.canonical_entries)
        alias_names = tuple(item.alias for item in self.aliases)
        if self.canonical_entries != tuple(
            sorted(
                self.canonical_entries,
                key=lambda item: (item.role != "local", item.host),
            )
        ) or len(set(canonical_names)) != len(canonical_names):
            raise HostInventoryError("canonical host keys must be unique and sorted")
        if alias_names != tuple(sorted(alias_names)) or len(set(alias_names)) != len(
            alias_names
        ):
            raise HostInventoryError("host alias keys must be unique and sorted")
        if set(canonical_names) & set(alias_names):
            raise HostInventoryError("canonical host and alias keys must be unique")
        if sum(item.role == "local" for item in self.canonical_entries) != 1:
            raise HostInventoryError(
                "host inventory must contain exactly one local host"
            )
        if any(item.canonical_host not in canonical_names for item in self.aliases):
            raise HostInventoryError("host alias names an unknown canonical host")

    @property
    def canonical_hosts(self) -> tuple[str, ...]:
        return tuple(item.host for item in self.canonical_entries)

    @property
    def remote_hosts(self) -> tuple[str, ...]:
        return tuple(
            item.host for item in self.canonical_entries if item.role == "remote"
        )

    @property
    def local_host(self) -> CanonicalHost:
        return next(item for item in self.canonical_entries if item.role == "local")

    def resolve(self, key: str) -> CanonicalHost:
        _bounded_token(key, label="host key")
        canonical_name = next(
            (item.canonical_host for item in self.aliases if item.alias == key),
            key,
        )
        try:
            return next(
                item for item in self.canonical_entries if item.host == canonical_name
            )
        except StopIteration as exc:
            raise HostInventoryError("unknown host key") from exc

    def to_dict(self) -> dict[str, object]:
        return {
            "aliases": [item.to_dict() for item in self.aliases],
            "canonical_entries": [item.to_dict() for item in self.canonical_entries],
            "schema": HOST_INVENTORY_SCHEMA,
        }

    @property
    def commitment(self) -> str:
        payload = HOST_INVENTORY_COMMITMENT_DOMAIN + canonical_json_bytes(
            self.to_dict()
        )
        return "sha256:" + hashlib.sha256(payload).hexdigest()

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> HostInventory:
        if not isinstance(value, Mapping) or set(value) != {
            "aliases",
            "canonical_entries",
            "schema",
        }:
            raise HostInventoryError("host inventory has an unexpected shape")
        if value.get("schema") != HOST_INVENTORY_SCHEMA:
            raise HostInventoryError("host inventory schema is invalid")
        raw_entries, raw_aliases = value.get("canonical_entries"), value.get("aliases")
        if not isinstance(raw_entries, list) or not isinstance(raw_aliases, list):
            raise HostInventoryError("host inventory rows must be lists")
        entries: list[CanonicalHost] = []
        for row in raw_entries:
            if not isinstance(row, Mapping) or set(row) != {
                "codex_root",
                "host",
                "role",
                "transport_target",
            }:
                raise HostInventoryError("canonical host row has an unexpected shape")
            entries.append(
                CanonicalHost(
                    host=row["host"],
                    role=row["role"],
                    codex_root=row["codex_root"],
                    transport_target=row["transport_target"],
                )
            )
        aliases: list[HostAlias] = []
        for row in raw_aliases:
            if not isinstance(row, Mapping) or set(row) != {"alias", "canonical_host"}:
                raise HostInventoryError("host alias row has an unexpected shape")
            aliases.append(
                HostAlias(alias=row["alias"], canonical_host=row["canonical_host"])
            )
        inventory = cls(tuple(entries), tuple(aliases))
        if dict(value) != inventory.to_dict():
            raise HostInventoryError("host inventory is not canonically normalized")
        return inventory


@dataclass(frozen=True, slots=True)
class AuthenticatedHostInventory:
    inventory: HostInventory
    helper_commitment: str

    def __post_init__(self) -> None:
        if _COMMITMENT_RE.fullmatch(self.helper_commitment) is None:
            raise HostInventoryError("helper commitment is invalid")

    @property
    def inventory_commitment(self) -> str:
        return self.inventory.commitment


def _host_literal(node: ast.AST) -> dict[str, dict[str, str]]:
    if not isinstance(node, ast.Dict) or len(node.keys) > MAX_HOST_INVENTORY_KEYS:
        raise HostInventoryError("HOSTS must be a bounded dictionary literal")
    seen: set[str] = set()
    for key_node, value_node in zip(node.keys, node.values, strict=True):
        if not isinstance(key_node, ast.Constant) or not isinstance(
            key_node.value, str
        ):
            raise HostInventoryError("HOSTS keys must be string literals")
        key = _bounded_token(key_node.value, label="HOSTS key")
        if key in seen:
            raise HostInventoryError("HOSTS contains a duplicate key")
        seen.add(key)
        if not isinstance(value_node, ast.Dict):
            raise HostInventoryError("HOSTS rows must be dictionary literals")
        row_keys: set[str] = set()
        for field_node, item_node in zip(
            value_node.keys, value_node.values, strict=True
        ):
            if (
                not isinstance(field_node, ast.Constant)
                or not isinstance(field_node.value, str)
                or field_node.value in row_keys
                or not isinstance(item_node, ast.Constant)
                or not isinstance(item_node.value, str)
            ):
                raise HostInventoryError(
                    "HOSTS rows must contain unique string literals"
                )
            row_keys.add(field_node.value)
    try:
        value = ast.literal_eval(node)
    except (MemoryError, RecursionError, SyntaxError, ValueError) as exc:
        raise HostInventoryError("HOSTS literal cannot be decoded") from exc
    if not isinstance(value, dict):
        raise HostInventoryError("HOSTS literal is not a dictionary")
    return value


def parse_authenticated_helper_hosts(source: bytes) -> HostInventory:
    """Parse one static top-level HOSTS assignment without executing helper code."""

    if (
        not isinstance(source, bytes)
        or not source
        or len(source) > MAX_REMOTE_HOST_CONTEXT_HELPER_BYTES
    ):
        raise HostInventoryError("remote helper source byte size is invalid")
    try:
        text = source.decode("utf-8")
        tree = ast.parse(text, filename="<authenticated-remote-host-context-helper>")
    except (
        MemoryError,
        RecursionError,
        SyntaxError,
        UnicodeDecodeError,
        ValueError,
    ) as exc:
        raise HostInventoryError(
            "remote helper source is not valid Python UTF-8"
        ) from exc
    pending = [tree]
    count = 0
    while pending:
        current = pending.pop()
        count += 1
        if count > MAX_REMOTE_HOST_CONTEXT_HELPER_AST_NODES:
            raise HostInventoryError("remote helper AST exceeds its bound")
        pending.extend(ast.iter_child_nodes(current))
    assignments: list[ast.AST] = []
    definition_target: ast.Name | None = None
    for statement in tree.body:
        if isinstance(statement, ast.AnnAssign) and isinstance(
            statement.target, ast.Name
        ):
            if statement.target.id == "HOSTS" and statement.value is not None:
                assignments.append(statement.value)
                definition_target = statement.target
        elif isinstance(statement, ast.Assign):
            targets = [
                target for target in statement.targets if isinstance(target, ast.Name)
            ]
            if any(target.id == "HOSTS" for target in targets):
                if len(statement.targets) != 1 or len(targets) != 1:
                    raise HostInventoryError(
                        "HOSTS assignment must have one name target"
                    )
                assignments.append(statement.value)
                definition_target = targets[0]
    if len(assignments) != 1:
        raise HostInventoryError(
            "remote helper must define exactly one top-level HOSTS"
        )
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Name)
            and node.id == "HOSTS"
            and isinstance(node.ctx, (ast.Store, ast.Del))
            and node is not definition_target
        ):
            raise HostInventoryError("remote helper HOSTS is reassigned")
        if isinstance(node, (ast.Attribute, ast.Subscript)) and isinstance(
            node.ctx, (ast.Store, ast.Del)
        ):
            root: ast.expr = node
            while isinstance(root, (ast.Attribute, ast.Subscript)):
                root = root.value
            if isinstance(root, ast.Name) and root.id == "HOSTS":
                raise HostInventoryError("remote helper HOSTS is mutated")
    raw = _host_literal(assignments[0])
    rows: dict[str, CanonicalHost] = {}
    labels: dict[str, str] = {}
    for key, row in raw.items():
        if not isinstance(row, dict):
            raise HostInventoryError("HOSTS row is invalid")
        kind = row.get("kind")
        role = {"local": "local", "ssh": "remote"}.get(kind)
        expected = {"codex_root", "kind", "label"} | (
            {"ssh_target"} if role == "remote" else set()
        )
        if role is None or set(row) != expected:
            raise HostInventoryError("HOSTS row has an unexpected shape")
        label = _bounded_token(row["label"], label="HOSTS label")
        labels[key] = label
        rows[key] = CanonicalHost(
            host=label,
            role=role,
            codex_root=_normalized_root(row["codex_root"], role=role),
            transport_target=(
                None
                if role == "local"
                else _bounded_token(
                    row["ssh_target"], label="HOSTS ssh_target", target=True
                )
            ),
        )
    canonical = {key: row for key, row in rows.items() if labels[key] == key}
    if any(label not in canonical for label in labels.values()):
        raise HostInventoryError("HOSTS alias lacks a canonical entry")
    aliases: list[HostAlias] = []
    for key, row in rows.items():
        label = labels[key]
        if key == label:
            continue
        expected = canonical[label]
        if (
            row.role,
            row.codex_root,
            row.transport_target,
        ) != (
            expected.role,
            expected.codex_root,
            expected.transport_target,
        ):
            raise HostInventoryError("HOSTS alias differs from its canonical entry")
        aliases.append(HostAlias(alias=key, canonical_host=label))
    return HostInventory(
        tuple(
            sorted(
                canonical.values(),
                key=lambda item: (item.role != "local", item.host),
            )
        ),
        tuple(sorted(aliases, key=lambda item: item.alias)),
    )


def require_inventory_commitment(inventory: HostInventory, commitment: object) -> str:
    if not isinstance(commitment, str) or _COMMITMENT_RE.fullmatch(commitment) is None:
        raise HostInventoryError("host inventory commitment is invalid")
    if commitment != inventory.commitment:
        raise HostInventoryError("host inventory commitment does not match")
    return commitment
