"""Descriptor-bound separation between runtime paths and source data."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable
import unicodedata

try:
    from . import path_identity, safe_io, transport_paths
except (ImportError, ModuleNotFoundError):
    import path_identity  # type: ignore[no-redef]
    import safe_io  # type: ignore[no-redef]
    import transport_paths  # type: ignore[no-redef]


_ComparedComponent = tuple[str, bool]


def _unresolved_component_key(component: str) -> str:
    return unicodedata.normalize("NFC", component).casefold()


def _components_equal(
    left: _ComparedComponent,
    right: _ComparedComponent,
) -> bool:
    if left[0] == right[0]:
        return True
    if not (left[1] or right[1]):
        return False
    return _unresolved_component_key(left[0]) == _unresolved_component_key(right[0])


def _component_prefix(
    left: tuple[_ComparedComponent, ...],
    right: tuple[_ComparedComponent, ...],
) -> bool:
    return len(left) <= len(right) and all(
        _components_equal(left_component, right_component)
        for left_component, right_component in zip(left, right, strict=False)
    )


def _components_after(
    chain: path_identity.BoundPathIdentityChain,
    identity_index: int,
) -> tuple[_ComparedComponent, ...]:
    return tuple((name, False) for name in chain.names[identity_index:]) + tuple(
        (name, True) for name in chain.unresolved
    )


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
            _root_rollout_component_matches((lexical_name, True)),
            _root_rollout_component_matches((resolved_name, True)),
        )
    )


def _root_rollout_component_matches(component: _ComparedComponent) -> bool:
    name = _unresolved_component_key(component[0]) if component[1] else component[0]
    return transport_paths.ROOT_ROLLOUT_RELATIVE_RE.fullmatch(name) is not None


def _ordinary_object_overlap(
    temporary: path_identity.BoundPathIdentityChain,
    source: path_identity.BoundPathIdentityChain,
) -> bool:
    for temporary_index, temporary_identity in enumerate(temporary.identities):
        temporary_suffix = _components_after(temporary, temporary_index)
        for source_index, source_identity in enumerate(source.identities):
            if temporary_identity != source_identity:
                continue
            source_suffix = _components_after(source, source_index)
            if _component_prefix(temporary_suffix, source_suffix) or _component_prefix(
                source_suffix,
                temporary_suffix,
            ):
                return True
    return False


def _root_rollout_object_overlap(
    temporary: path_identity.BoundPathIdentityChain,
    source: path_identity.BoundPathIdentityChain,
) -> bool:
    if source.unresolved:
        return False
    source_identity = source.identities[-1]
    for index, identity in enumerate(temporary.identities):
        if identity != source_identity:
            continue
        suffix = _components_after(temporary, index)
        if suffix and _root_rollout_component_matches(suffix[0]):
            return True
    return False


def require_root_outside_source(
    temporary_root: Path,
    source_root: Path,
    overlap_test: Callable[..., bool] = _ordinary_source_overlap,
    *,
    check_object_identity: bool = True,
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
    if check_object_identity:
        with (
            path_identity.bound_path_identity_chain(
                lexical_temporary_root
            ) as temporary_chain,
            path_identity.bound_path_identity_chain(
                lexical_source_root
            ) as source_chain,
        ):
            if overlap_test is _root_rollout_overlap:
                object_overlap = _root_rollout_object_overlap(
                    temporary_chain,
                    source_chain,
                )
            else:
                object_overlap = _ordinary_object_overlap(
                    temporary_chain,
                    source_chain,
                )
            temporary_chain.revalidate()
            source_chain.revalidate()
        overlap = overlap or object_overlap
    if overlap:
        raise safe_io.UnsafePathError(
            "runtime temporary root overlaps a retrospective source root"
        )


def _source_checks(
    source_root: Path,
) -> tuple[tuple[Path, Callable[..., bool]], ...]:
    return (
        (source_root / "sessions", _ordinary_source_overlap),
        (source_root / "archived_sessions", _ordinary_source_overlap),
        (source_root / "history.jsonl", _ordinary_source_overlap),
        (source_root / "session_index.jsonl", _ordinary_source_overlap),
        (source_root, _root_rollout_overlap),
    )


def require_run_directory_lexically_outside_sources(
    run_dir: Path,
    source_root: Path,
) -> Path:
    """Reject lexical and resolver-visible source overlap without opening paths."""
    for source_path, overlap_test in _source_checks(source_root):
        require_root_outside_source(
            run_dir,
            source_path,
            overlap_test,
            check_object_identity=False,
        )
    return run_dir


def require_run_directory_outside_sources(run_dir: Path, source_root: Path) -> Path:
    source_checks = _source_checks(source_root)
    require_run_directory_lexically_outside_sources(run_dir, source_root)
    with path_identity.bound_path_identity_chain(run_dir) as temporary_chain:
        for source_path, overlap_test in source_checks:
            with path_identity.bound_path_identity_chain(source_path) as source_chain:
                if overlap_test is _root_rollout_overlap:
                    overlap = _root_rollout_object_overlap(
                        temporary_chain,
                        source_chain,
                    )
                else:
                    overlap = _ordinary_object_overlap(
                        temporary_chain,
                        source_chain,
                    )
                source_chain.revalidate()
            if overlap:
                raise safe_io.UnsafePathError(
                    "runtime temporary root overlaps a retrospective source root"
                )
        temporary_chain.revalidate()
    return run_dir


def require_bound_run_directory_outside_sources(
    run_dir: Path,
    descriptor: int,
    source_root: Path,
) -> Path:
    with path_identity.bound_directory_ancestor_chain(descriptor) as ancestors:
        expected = ancestors.identities[0]
        for source_path in (
            source_root / "sessions",
            source_root / "archived_sessions",
            source_root / "history.jsonl",
            source_root / "session_index.jsonl",
        ):
            with path_identity.bound_path_identity_chain(source_path) as source_chain:
                bound_is_ancestor = expected in source_chain.identities
                bound_is_descendant = (
                    not source_chain.unresolved
                    and source_chain.identities[-1] in ancestors.identities
                )
                if bound_is_ancestor or bound_is_descendant:
                    raise safe_io.UnsafePathError(
                        "bound runtime directory overlaps a retrospective source root"
                    )
                source_chain.revalidate()
        normalized = require_run_directory_outside_sources(run_dir, source_root)
        with path_identity.bound_path_identity_chain(normalized) as named_chain:
            if named_chain.unresolved or named_chain.identities[-1] != expected:
                raise safe_io.UnsafePathError(
                    "bound runtime directory name changed after it was opened"
                )
            named_chain.revalidate()
        ancestors.revalidate()
    return normalized
