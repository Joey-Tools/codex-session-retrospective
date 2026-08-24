"""Descriptor-bound filesystem identity chains for source separation."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import os
from pathlib import Path
import stat
from typing import Iterator

try:
    from . import safe_io
except (ImportError, ModuleNotFoundError):
    import safe_io  # type: ignore[no-redef]


PATH_IDENTITY_COMPONENT_LIMIT = 256


def object_identity(metadata: os.stat_result) -> tuple[int, int, int]:
    return (
        int(metadata.st_dev),
        int(metadata.st_ino),
        stat.S_IFMT(metadata.st_mode),
    )


def _close_descriptors(
    descriptors: tuple[int, ...] | list[int],
    *,
    primary: BaseException | None,
) -> None:
    close_error: OSError | None = None
    for descriptor in reversed(descriptors):
        try:
            os.close(descriptor)
        except OSError as error:
            if primary is not None:
                primary.add_note(f"path identity descriptor close failed: {error}")
            elif close_error is None:
                close_error = error
    if primary is None and close_error is not None:
        raise close_error


@dataclass(frozen=True, slots=True)
class BoundPathIdentityChain:
    descriptors: tuple[int, ...]
    identities: tuple[tuple[int, int, int], ...]
    names: tuple[str, ...]
    unresolved: tuple[str, ...]
    missing_name: str | None

    def suffix_after(self, identity_index: int) -> tuple[str, ...]:
        return self.names[identity_index:] + self.unresolved

    def revalidate(self) -> None:
        for index, (descriptor, expected) in enumerate(
            zip(self.descriptors, self.identities, strict=True)
        ):
            if object_identity(os.fstat(descriptor)) != expected:
                raise safe_io.UnsafePathError(
                    "path object identity changed while source separation was inspected"
                )
            if index == 0:
                continue
            named = os.stat(
                self.names[index - 1],
                dir_fd=self.descriptors[index - 1],
                follow_symlinks=True,
            )
            if object_identity(named) != expected:
                raise safe_io.UnsafePathError(
                    "path route changed while source separation was inspected"
                )
        if self.missing_name is not None:
            try:
                os.stat(
                    self.missing_name,
                    dir_fd=self.descriptors[-1],
                    follow_symlinks=False,
                )
            except FileNotFoundError:
                pass
            else:
                raise safe_io.UnsafePathError(
                    "path appeared while source separation was inspected"
                )


def _open_path_identity_chain(path: Path) -> BoundPathIdentityChain:
    normalized = Path(os.path.abspath(os.fspath(path)))
    components = tuple(
        component
        for component in normalized.parts[1:]
        if component not in {"", ".", os.sep}
    )
    if len(components) > PATH_IDENTITY_COMPONENT_LIMIT:
        raise safe_io.UnsafePathError(
            "path has too many components for source separation"
        )
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_CLOEXEC", 0)
    descriptors: list[int] = []
    identities: list[tuple[int, int, int]] = []
    names: list[str] = []
    unresolved: tuple[str, ...] = ()
    missing_name: str | None = None
    try:
        root_fd = os.open(normalized.anchor, flags | getattr(os, "O_DIRECTORY", 0))
        descriptors.append(root_fd)
        identities.append(object_identity(os.fstat(root_fd)))
        for index, name in enumerate(components):
            parent_fd = descriptors[-1]
            try:
                child_fd = os.open(name, flags, dir_fd=parent_fd)
            except FileNotFoundError:
                unresolved = components[index:]
                missing_name = name
                break
            except OSError as error:
                raise safe_io.UnsafePathError(
                    "path object identity is unavailable for source separation"
                ) from error
            descriptors.append(child_fd)
            child_identity = object_identity(os.fstat(child_fd))
            named = os.stat(name, dir_fd=parent_fd, follow_symlinks=True)
            if object_identity(named) != child_identity:
                raise safe_io.UnsafePathError(
                    "path changed while source separation was inspected"
                )
            identities.append(child_identity)
            names.append(name)
            if index + 1 < len(components) and not stat.S_ISDIR(
                os.fstat(child_fd).st_mode
            ):
                unresolved = components[index + 1 :]
                break
        return BoundPathIdentityChain(
            descriptors=tuple(descriptors),
            identities=tuple(identities),
            names=tuple(names),
            unresolved=unresolved,
            missing_name=missing_name,
        )
    except BaseException as primary:
        _close_descriptors(descriptors, primary=primary)
        raise


@contextmanager
def bound_path_identity_chain(path: Path) -> Iterator[BoundPathIdentityChain]:
    chain = _open_path_identity_chain(path)
    primary: BaseException | None = None
    try:
        yield chain
    except BaseException as error:
        primary = error
        raise
    finally:
        _close_descriptors(chain.descriptors, primary=primary)


@dataclass(frozen=True, slots=True)
class BoundDirectoryAncestorChain:
    descriptors: tuple[int, ...]
    identities: tuple[tuple[int, int, int], ...]

    def revalidate(self) -> None:
        for index, (descriptor, expected) in enumerate(
            zip(self.descriptors, self.identities, strict=True)
        ):
            if object_identity(os.fstat(descriptor)) != expected:
                raise safe_io.UnsafePathError(
                    "bound directory ancestor identity changed during inspection"
                )
            parent_fd = os.open(
                "..",
                os.O_RDONLY
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_CLOEXEC", 0),
                dir_fd=descriptor,
            )
            primary: BaseException | None = None
            try:
                parent_index = min(index + 1, len(self.identities) - 1)
                if (
                    object_identity(os.fstat(parent_fd))
                    != self.identities[parent_index]
                ):
                    raise safe_io.UnsafePathError(
                        "bound directory ancestor route changed during inspection"
                    )
            except BaseException as error:
                primary = error
                raise
            finally:
                _close_descriptors((parent_fd,), primary=primary)


def _open_directory_ancestor_chain(descriptor: int) -> BoundDirectoryAncestorChain:
    descriptors: list[int] = []
    identities: list[tuple[int, int, int]] = []
    try:
        current = os.dup(descriptor)
        descriptors.append(current)
        current_identity = object_identity(os.fstat(current))
        identities.append(current_identity)
        if not stat.S_ISDIR(os.fstat(current).st_mode):
            raise safe_io.UnsafePathError("bound runtime path is not a directory")
        for _depth in range(PATH_IDENTITY_COMPONENT_LIMIT + 1):
            parent = os.open(
                "..",
                os.O_RDONLY
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_CLOEXEC", 0),
                dir_fd=current,
            )
            descriptors.append(parent)
            parent_identity = object_identity(os.fstat(parent))
            identities.append(parent_identity)
            if parent_identity == current_identity:
                break
            current = parent
            current_identity = parent_identity
        else:
            raise safe_io.UnsafePathError(
                "bound directory has too many ancestors for source separation"
            )
        return BoundDirectoryAncestorChain(
            descriptors=tuple(descriptors),
            identities=tuple(identities),
        )
    except BaseException as primary:
        _close_descriptors(descriptors, primary=primary)
        raise


@contextmanager
def bound_directory_ancestor_chain(
    descriptor: int,
) -> Iterator[BoundDirectoryAncestorChain]:
    chain = _open_directory_ancestor_chain(descriptor)
    primary: BaseException | None = None
    try:
        yield chain
    except BaseException as error:
        primary = error
        raise
    finally:
        _close_descriptors(chain.descriptors, primary=primary)
