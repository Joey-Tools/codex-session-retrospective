#!/usr/bin/env -S python3 -I -B -S
"""Descriptor-captured machine-only runtime for Session Retrospective v2."""

from __future__ import annotations

import json
import sys


def _startup_failure(code, message):
    sys.stdout.write(
        json.dumps(
            {
                "command": "startup",
                "error": {
                    "code": code,
                    "message": message,
                    "reason_code": "readiness_failed",
                    "recovery_action": "satisfy_readiness_gate",
                    "retryable": False,
                },
                "exit_code": 9,
                "ok": False,
                "result": None,
                "schema": "cli_result_v2",
            },
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    )
    sys.stderr.write("session_retrospective_v2: %s: %s\n" % (code, message))
    return 9


if __name__ == "__main__" and not (
    sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode
):
    raise SystemExit(
        _startup_failure("unsafe_python_runtime", "invoke with python3 -I -B -S")
    )

if sys.version_info < (3, 13):
    raise SystemExit(
        _startup_failure(
            "unsupported_python_runtime",
            "Session Retrospective v2 requires Python 3.13 or newer",
        )
    )


if __name__ != "__main__":
    import importlib

    _api = importlib.import_module("retrospective_v2.cli")
    sys.modules[__name__] = _api
else:
    import ctypes
    import errno
    import hashlib
    import hmac
    import importlib
    import importlib.abc
    import importlib.util
    import os
    import stat

    _READINESS_SCHEMA = "coordinator_implementation_readiness_v2"
    _IMPLEMENTATION_ID = "session_retrospective_v2_python_source"
    _EVIDENCE_ATTRIBUTE = "_retrospective_v2_startup_authority_v2"
    _BOOTSTRAP_LAUNCHER_NAME = "session_retrospective_v2.py"
    _PRELOADED_ENTRY_ATTRIBUTE = "_RETROSPECTIVE_V2_PRELOADED_ENTRY"
    _MAX_SOURCE_FILES = 160
    _MAX_SOURCE_FILE_BYTES = 2 * 1024 * 1024
    _MAX_SOURCE_TOTAL_BYTES = 32 * 1024 * 1024
    _DIRECTORY_FLAGS = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    _FILE_FLAGS = (
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    _IMPORT_SUFFIXES = (".py", ".pyc", ".pyo", ".so", ".pyd", ".dylib")

    # BEGIN GENERATED RETROSPECTIVE V2 SOURCE MANIFEST
    _PACKAGE_SOURCE_MANIFEST = (
        "__init__.py",
        "agent_capacity.py",
        "agent_checkpoint_capacity.py",
        "agent_claim_artifacts.py",
        "agent_claim_projection.py",
        "agent_raw_artifacts.py",
        "agent_result_contracts.py",
        "agent_results.py",
        "agent_task_inputs.py",
        "authority.py",
        "authority_errors.py",
        "automation_cutover_files.py",
        "calibration.py",
        "catalog.py",
        "checkpoints.py",
        "cleanup_inventory.py",
        "cleanup_sidecars.py",
        "cli.py",
        "contracts.py",
        "controlled_gaps.py",
        "episode_review.py",
        "executable_authority.py",
        "export.py",
        "extracted_turns.py",
        "finalize.py",
        "git_safety.py",
        "gpg_status.py",
        "history_graph.py",
        "identity.py",
        "implementation_authority.py",
        "legacy_history_git.py",
        "legacy_history_worktree.py",
        "orchestrator.py",
        "orchestrator_components.py",
        "orchestrator_context.py",
        "orchestrator_core.py",
        "orchestrator_execution_contract.py",
        "orchestrator_history.py",
        "orchestrator_jobs.py",
        "orchestrator_lifecycle.py",
        "orchestrator_projection.py",
        "orchestrator_protocols.py",
        "orchestrator_reduction.py",
        "orchestrator_scheduler.py",
        "orchestrator_source.py",
        "orchestrator_source_segments.py",
        "orchestrator_state.py",
        "orchestrator_support.py",
        "orchestrator_synthesis.py",
        "orchestrator_transport.py",
        "privacy_locators.py",
        "process_lifecycle.py",
        "publication_abort_authority.py",
        "publication_abort_replay.py",
        "publication_claims.py",
        "publication_cli_adapter.py",
        "publication_contracts.py",
        "publication_git.py",
        "publication_git_capacity.py",
        "publication_git_commits.py",
        "publication_git_storage.py",
        "publication_state.py",
        "publication_support.py",
        "publication_transaction.py",
        "raw_cleanup_state.py",
        "raw_shard_staging.py",
        "reduction_lineage.py",
        "reduction_task_inputs.py",
        "reporting.py",
        "result_validation.py",
        "retained_export_binding.py",
        "retained_export_coordination.py",
        "retained_inputs.py",
        "run_state_authority.py",
        "run_state_contracts.py",
        "run_state_cursors.py",
        "run_state_holdouts.py",
        "run_state_lineage.py",
        "safe_io.py",
        "session_shards_adapter.py",
        "session_shards_relay.py",
        "sharding.py",
        "source_acceptance.py",
        "source_capacity.py",
        "source_inputs.py",
        "source_overlap.py",
        "source_payloads.py",
        "source_session_policy.py",
        "source_spool.py",
        "source_staging.py",
        "synthesis_evidence.py",
        "synthesis_lineage.py",
        "synthesis_sources.py",
        "synthesis_tasks.py",
        "transport.py",
        "transport_auth.py",
        "transport_capture.py",
        "transport_contracts.py",
        "transport_discovery.py",
        "transport_host_inventory.py",
        "transport_paths.py",
        "transport_program.py",
        "transport_program_components.py",
        "transport_remote.py",
        "transport_remote_snapshot.py",
        "transport_resume.py",
        "transport_session_shards.py",
        "transport_snapshot.py",
        "transport_source.py",
        "transport_worker.py",
    )
    _ROOT_HELPER_SOURCE_MANIFEST = (
        "session_retrospective_v2_export.py",
        "session_retrospective_v2_transcript.py",
    )
    _ROOT_SUPPORT_SOURCE_MANIFEST = (
        "session_retrospective_v2_export_binding.py",
        "session_retrospective_v2_export_legacy.py",
        "session_retrospective_v2_export_records.py",
    )
    # END GENERATED RETROSPECTIVE V2 SOURCE MANIFEST

    class _SourceAuthorityError(PermissionError):
        pass

    def _canonical_bytes(value):
        return json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")

    def _darwin_acl_api():
        if sys.platform != "darwin":
            return None
        try:
            libc = ctypes.CDLL(None, use_errno=True)
            getter = libc.acl_get_fd_np
            getter.argtypes = (ctypes.c_int, ctypes.c_int)
            getter.restype = ctypes.c_void_p
            serializer = libc.acl_to_text
            serializer.argtypes = (ctypes.c_void_p, ctypes.POINTER(ctypes.c_ssize_t))
            serializer.restype = ctypes.c_void_p
            releaser = libc.acl_free
            releaser.argtypes = (ctypes.c_void_p,)
            releaser.restype = ctypes.c_int
        except (AttributeError, OSError) as error:
            raise _SourceAuthorityError(
                "implementation ACL authority is unavailable"
            ) from error
        return getter, serializer, releaser

    _ACL_API = _darwin_acl_api()

    def _acl_policy_bytes(descriptor):
        if _ACL_API is None:
            return b""
        getter, serializer, releaser = _ACL_API
        ctypes.set_errno(0)
        acl = getter(descriptor, 0x100)
        if not acl:
            if ctypes.get_errno() == errno.ENOENT:
                return b""
            raise _SourceAuthorityError("implementation ACL cannot be inspected")
        length = ctypes.c_ssize_t()
        ctypes.set_errno(0)
        text_pointer = serializer(acl, ctypes.byref(length))
        if not text_pointer or not 0 <= length.value <= 64 * 1024:
            releaser(acl)
            raise _SourceAuthorityError("implementation ACL cannot be serialized")
        value = bytes(ctypes.string_at(text_pointer, length.value))
        text_cleanup = releaser(text_pointer)
        acl_cleanup = releaser(acl)
        if text_cleanup != 0 or acl_cleanup != 0:
            raise _SourceAuthorityError("implementation ACL cleanup failed")
        return value

    def _metadata_identity(metadata, directory):
        identity = (
            metadata.st_dev,
            metadata.st_ino,
            metadata.st_uid,
            metadata.st_gid,
            metadata.st_mode,
        )
        if directory:
            return identity
        return identity + (metadata.st_nlink, metadata.st_size)

    def _policy(descriptor, directory):
        metadata = os.fstat(descriptor)
        expected_type = stat.S_ISDIR if directory else stat.S_ISREG
        if not expected_type(metadata.st_mode):
            raise _SourceAuthorityError("implementation source type is invalid")
        if metadata.st_uid not in {0, os.geteuid()}:
            raise _SourceAuthorityError("implementation source owner is invalid")
        mode = stat.S_IMODE(metadata.st_mode)
        if mode & 0o022:
            raise _SourceAuthorityError(
                "implementation source is writable by another user"
            )
        if not directory and metadata.st_nlink != 1:
            raise _SourceAuthorityError("implementation source link count is invalid")
        acl = _acl_policy_bytes(descriptor)
        entries = [
            line for line in acl.splitlines() if line and not line.startswith(b"!#acl")
        ]
        if any(b":allow:" in line or b":deny:" not in line for line in entries):
            raise _SourceAuthorityError("implementation source ACL is unsafe")
        return {
            "acl_sha256": hashlib.sha256(acl).hexdigest(),
            "gid": metadata.st_gid,
            "mode": mode,
            "nlink": None if directory else metadata.st_nlink,
            "type": "directory" if directory else "regular-file",
            "uid": metadata.st_uid,
        }

    def _require_named(parent_fd, name, descriptor, directory, expected_policy):
        opened = os.fstat(descriptor)
        named = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if (
            _metadata_identity(opened, directory)
            != _metadata_identity(named, directory)
            or _policy(descriptor, directory) != expected_policy
        ):
            raise _SourceAuthorityError("implementation source identity changed")
        return opened

    def _read_exact(descriptor, size):
        if not 0 <= size <= _MAX_SOURCE_FILE_BYTES:
            raise _SourceAuthorityError("implementation source exceeds its byte bound")
        chunks = []
        offset = 0
        while offset < size:
            chunk = os.pread(descriptor, min(64 * 1024, size - offset), offset)
            if not chunk:
                raise _SourceAuthorityError("implementation source changed while read")
            chunks.append(chunk)
            offset += len(chunk)
        if os.pread(descriptor, 1, size):
            raise _SourceAuthorityError("implementation source changed while read")
        return b"".join(chunks)

    def _capture_source(parent_fd, name, module_name, relative_path, display_path):
        descriptor = os.open(name, _FILE_FLAGS, dir_fd=parent_fd)
        try:
            before = os.fstat(descriptor)
            policy = _policy(descriptor, False)
            _require_named(parent_fd, name, descriptor, False, policy)
            first = _read_exact(descriptor, before.st_size)
            middle = _require_named(parent_fd, name, descriptor, False, policy)
            second = _read_exact(descriptor, before.st_size)
            after = _require_named(parent_fd, name, descriptor, False, policy)
            if (
                _metadata_identity(before, False) != _metadata_identity(middle, False)
                or _metadata_identity(before, False) != _metadata_identity(after, False)
                or not hmac.compare_digest(first, second)
            ):
                raise _SourceAuthorityError("implementation source changed while read")
            source_row = {
                "module": module_name,
                "relative_path": relative_path,
                "sha256": hashlib.sha256(first).hexdigest(),
                "size": len(first),
            }
            access_row = {
                "access_policy": policy,
                "module": module_name,
                "relative_path": relative_path,
            }
            return module_name, first, display_path, source_row, access_row
        finally:
            os.close(descriptor)

    def _capture_preloaded_entry(
        parent_fd, name, module_name, relative_path, display_path
    ):
        binding = globals().pop(_PRELOADED_ENTRY_ATTRIBUTE, None)
        if not isinstance(binding, dict) or set(binding) != {
            "access_policy",
            "descriptor",
            "identity",
            "path",
            "source",
        }:
            raise _SourceAuthorityError("preloaded runtime source is unavailable")
        descriptor = binding["descriptor"]
        source = binding["source"]
        identity = binding["identity"]
        expected_policy = binding["access_policy"]
        if (
            not isinstance(descriptor, int)
            or isinstance(descriptor, bool)
            or descriptor < 0
            or not isinstance(source, bytes)
            or not isinstance(identity, tuple)
            or binding["path"] != display_path
            or name != os.path.basename(display_path)
        ):
            raise _SourceAuthorityError("preloaded runtime source binding is invalid")
        before = os.fstat(descriptor)
        policy = _policy(descriptor, False)
        _require_named(parent_fd, name, descriptor, False, policy)
        first = _read_exact(descriptor, before.st_size)
        middle = _require_named(parent_fd, name, descriptor, False, policy)
        second = _read_exact(descriptor, before.st_size)
        after = _require_named(parent_fd, name, descriptor, False, policy)
        if (
            _metadata_identity(before, False) != identity
            or _metadata_identity(before, False) != _metadata_identity(middle, False)
            or _metadata_identity(before, False) != _metadata_identity(after, False)
            or policy != expected_policy
            or not hmac.compare_digest(first, second)
            or not hmac.compare_digest(first, source)
        ):
            raise _SourceAuthorityError(
                "preloaded runtime source changed after descriptor capture"
            )
        source_row = {
            "module": module_name,
            "relative_path": relative_path,
            "sha256": hashlib.sha256(source).hexdigest(),
            "size": len(source),
        }
        access_row = {
            "access_policy": policy,
            "module": module_name,
            "relative_path": relative_path,
        }
        try:
            os.close(descriptor)
        except OSError as error:
            raise _SourceAuthorityError(
                "preloaded runtime descriptor cleanup failed"
            ) from error
        binding["descriptor"] = -1
        return module_name, source, display_path, source_row, access_row

    def _list_names(descriptor):
        names = os.listdir(descriptor)
        if len(names) > _MAX_SOURCE_FILES * 4 or any(
            not isinstance(name, str) or "\x00" in name for name in names
        ):
            raise _SourceAuthorityError("implementation inventory is invalid")
        return tuple(sorted(names))

    def _is_import_substitute(parent_fd, name):
        if name == "__pycache__" or name.endswith(_IMPORT_SUFFIXES):
            return True
        metadata = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        return stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode)

    def _validate_inventory(scripts_fd, package_fd):
        scripts_names = _list_names(scripts_fd)
        package_names = _list_names(package_fd)
        expected_package = set(_PACKAGE_SOURCE_MANIFEST)
        expected_root = {
            os.path.basename(__file__),
            _BOOTSTRAP_LAUNCHER_NAME,
            *_ROOT_HELPER_SOURCE_MANIFEST,
            *_ROOT_SUPPORT_SOURCE_MANIFEST,
        }
        if not expected_package <= set(package_names) or not expected_root <= set(
            scripts_names
        ):
            raise _SourceAuthorityError("implementation inventory is incomplete")
        if "__pycache__" in scripts_names or "__pycache__" in package_names:
            raise _SourceAuthorityError("implementation bytecode cache is forbidden")
        package_candidates = []
        for name in package_names:
            if name in expected_package:
                package_candidates.append(name)
            elif _is_import_substitute(package_fd, name):
                raise _SourceAuthorityError(
                    "implementation inventory has an unlisted import candidate"
                )
        root_candidates = []
        for name in scripts_names:
            if name in expected_root or name == "retrospective_v2":
                root_candidates.append(name)
                continue
            if name.startswith(("retrospective_v2", "session_retrospective_v2")):
                if _is_import_substitute(scripts_fd, name):
                    raise _SourceAuthorityError(
                        "implementation inventory has an unlisted import candidate"
                    )
        return tuple(root_candidates), tuple(package_candidates)

    def _open_scripts_chain():
        scripts = os.path.dirname(os.path.realpath(__file__))
        if not os.path.isabs(scripts) or os.path.basename(scripts) != "scripts":
            raise _SourceAuthorityError("implementation scripts root is invalid")
        descriptors = []
        policies = []
        try:
            current = os.open(os.path.sep, _DIRECTORY_FLAGS)
            descriptors.append(current)
            policies.append(_policy(current, True))
            for component in scripts.split(os.path.sep)[1:]:
                child = os.open(component, _DIRECTORY_FLAGS, dir_fd=current)
                child_policy = _policy(child, True)
                _require_named(current, component, child, True, child_policy)
                descriptors.append(child)
                policies.append(child_policy)
                current = child
            return scripts, descriptors, policies
        except BaseException:
            for descriptor in reversed(descriptors):
                try:
                    os.close(descriptor)
                except OSError:
                    pass
            raise

    def _module_name(filename):
        if filename == "__init__.py":
            return "retrospective_v2"
        return "retrospective_v2." + filename[:-3]

    def _capture_startup_authority():
        scripts, descriptors, ancestor_policies = _open_scripts_chain()
        package_fd = -1
        try:
            scripts_fd = descriptors[-1]
            package_fd = os.open(
                "retrospective_v2", _DIRECTORY_FLAGS, dir_fd=scripts_fd
            )
            package_policy = _policy(package_fd, True)
            _require_named(
                scripts_fd,
                "retrospective_v2",
                package_fd,
                True,
                package_policy,
            )
            initial_inventory = _validate_inventory(scripts_fd, package_fd)
            captured = []
            captured_bytes = 0
            entry_name = os.path.basename(__file__)
            entry_row = _capture_preloaded_entry(
                scripts_fd,
                entry_name,
                "session_retrospective_v2_runtime",
                entry_name,
                os.path.join(scripts, entry_name),
            )
            captured_bytes += entry_row[3]["size"]
            if captured_bytes > _MAX_SOURCE_TOTAL_BYTES:
                raise _SourceAuthorityError(
                    "implementation exceeds its aggregate byte bound"
                )
            captured.append(entry_row)
            for filename in _PACKAGE_SOURCE_MANIFEST:
                relative_path = "retrospective_v2/" + filename
                row = _capture_source(
                    package_fd,
                    filename,
                    _module_name(filename),
                    relative_path,
                    os.path.join(scripts, relative_path),
                )
                captured_bytes += row[3]["size"]
                if captured_bytes > _MAX_SOURCE_TOTAL_BYTES:
                    raise _SourceAuthorityError(
                        "implementation exceeds its aggregate byte bound"
                    )
                captured.append(row)
            for filename in (
                *_ROOT_HELPER_SOURCE_MANIFEST,
                *_ROOT_SUPPORT_SOURCE_MANIFEST,
            ):
                row = _capture_source(
                    scripts_fd,
                    filename,
                    filename[:-3],
                    filename,
                    os.path.join(scripts, filename),
                )
                captured_bytes += row[3]["size"]
                if captured_bytes > _MAX_SOURCE_TOTAL_BYTES:
                    raise _SourceAuthorityError(
                        "implementation exceeds its aggregate byte bound"
                    )
                captured.append(row)
            if len(captured) > _MAX_SOURCE_FILES:
                raise _SourceAuthorityError(
                    "implementation inventory exceeds its file bound"
                )
            if initial_inventory != _validate_inventory(scripts_fd, package_fd):
                raise _SourceAuthorityError("implementation inventory changed")
            if (
                _policy(package_fd, True) != package_policy
                or [_policy(descriptor, True) for descriptor in descriptors]
                != ancestor_policies
            ):
                raise _SourceAuthorityError(
                    "implementation directory access policy changed"
                )
            importable = [
                row for row in captured if row[0] != "session_retrospective_v2_runtime"
            ]
            sources = {row[0]: row[1] for row in importable}
            paths = {row[0]: row[2] for row in importable}
            source_rows = [row[3] for row in captured]
            total_bytes = sum(row["size"] for row in source_rows)
            manifest = [row[0] for row in captured]
            access = {
                "ancestors": ancestor_policies,
                "files": [row[4] for row in captured],
                "package": package_policy,
            }
            authority = {
                "access": access,
                "manifest": manifest,
                "source": source_rows,
            }
            receipt = {
                "access_policy_sha256": "sha256:"
                + hashlib.sha256(_canonical_bytes(access)).hexdigest(),
                "authority_sha256": "sha256:"
                + hashlib.sha256(_canonical_bytes(authority)).hexdigest(),
                "file_count": len(source_rows),
                "implementation": _IMPLEMENTATION_ID,
                "schema": _READINESS_SCHEMA,
                "source_sha256": "sha256:"
                + hashlib.sha256(_canonical_bytes(source_rows)).hexdigest(),
                "total_bytes": total_bytes,
            }
            evidence = {
                "access": access,
                "manifest": manifest,
                "receipt": receipt,
                "source": source_rows,
            }
            return sources, paths, receipt, _canonical_bytes(evidence), scripts
        finally:
            if package_fd >= 0:
                os.close(package_fd)
            for descriptor in reversed(descriptors):
                os.close(descriptor)

    class _CapturedLoader(importlib.abc.Loader):
        def __init__(self, fullname, source, display_path, is_package):
            self._fullname = fullname
            self._source = source
            self._display_path = display_path
            self._is_package = is_package

        def create_module(self, spec):
            return None

        def exec_module(self, module):
            module.__file__ = self._display_path
            module.__cached__ = None
            exec(
                compile(
                    self._source,
                    self._display_path,
                    "exec",
                    dont_inherit=True,
                ),
                module.__dict__,
            )

    class _CapturedFinder(importlib.abc.MetaPathFinder):
        def __init__(self, sources, paths):
            self._sources = sources
            self._paths = paths

        def find_spec(self, fullname, path=None, target=None):
            del path, target
            source = self._sources.get(fullname)
            if source is not None:
                is_package = fullname == "retrospective_v2"
                loader = _CapturedLoader(
                    fullname,
                    source,
                    self._paths[fullname],
                    is_package,
                )
                return importlib.util.spec_from_loader(
                    fullname,
                    loader,
                    origin=self._paths[fullname],
                    is_package=is_package,
                )
            if fullname == "retrospective_v2" or fullname.startswith(
                "retrospective_v2."
            ):
                raise ModuleNotFoundError(
                    "retrospective_v2 module is outside the startup manifest",
                    name=fullname,
                )
            if fullname == "session_retrospective_v2" or fullname.startswith(
                "session_retrospective_v2_"
            ):
                raise ModuleNotFoundError(
                    "retrospective v2 helper is outside the startup manifest",
                    name=fullname,
                )
            return None

    def _authenticated_cli():
        sources, paths, receipt, evidence, scripts = _capture_startup_authority()
        for entry in sys.path:
            if entry and os.path.realpath(entry) == scripts:
                raise _SourceAuthorityError(
                    "implementation scripts root is present on sys.path"
                )
        if any(
            name == "retrospective_v2"
            or name.startswith("retrospective_v2.")
            or name == "session_retrospective_v2"
            or name.startswith("session_retrospective_v2_")
            for name in sys.modules
        ):
            raise _SourceAuthorityError("implementation modules were imported early")
        finder = _CapturedFinder(sources, paths)
        setattr(sys, _EVIDENCE_ATTRIBUTE, evidence)
        sys.meta_path.insert(0, finder)
        cli_api = importlib.import_module("retrospective_v2.cli")
        authority_api = importlib.import_module(
            "retrospective_v2.implementation_authority"
        )
        if authority_api.coordinator_implementation_readiness() != receipt:
            raise _SourceAuthorityError("implementation startup receipt is invalid")
        return cli_api

    try:
        _cli = _authenticated_cli()
    except Exception:
        raise SystemExit(
            _startup_failure(
                "implementation_authority_invalid",
                "coordinator implementation authority cannot be authenticated",
            )
        )
    raise SystemExit(_cli.main())
