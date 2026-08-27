#!/usr/bin/env -S python3 -I -B -S
"""Descriptor launcher for the authenticated Session Retrospective v2 runtime."""

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
    import os
    import stat

    _RUNTIME_NAME = "session_retrospective_v2_runtime.py"
    _MAX_RUNTIME_BYTES = 2 * 1024 * 1024
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

    class _LauncherAuthorityError(PermissionError):
        pass

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
            raise _LauncherAuthorityError(
                "runtime launcher ACL authority is unavailable"
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
            raise _LauncherAuthorityError("runtime launcher ACL cannot be inspected")
        length = ctypes.c_ssize_t()
        ctypes.set_errno(0)
        text_pointer = serializer(acl, ctypes.byref(length))
        if not text_pointer or not 0 <= length.value <= 64 * 1024:
            releaser(acl)
            raise _LauncherAuthorityError("runtime launcher ACL cannot be serialized")
        value = bytes(ctypes.string_at(text_pointer, length.value))
        text_cleanup = releaser(text_pointer)
        acl_cleanup = releaser(acl)
        if text_cleanup != 0 or acl_cleanup != 0:
            raise _LauncherAuthorityError("runtime launcher ACL cleanup failed")
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
            raise _LauncherAuthorityError("runtime launcher source type is invalid")
        if metadata.st_uid not in {0, os.geteuid()}:
            raise _LauncherAuthorityError("runtime launcher source owner is invalid")
        mode = stat.S_IMODE(metadata.st_mode)
        if mode & 0o022:
            raise _LauncherAuthorityError(
                "runtime launcher source is writable by another user"
            )
        if not directory and metadata.st_nlink != 1:
            raise _LauncherAuthorityError(
                "runtime launcher source link count is invalid"
            )
        acl = _acl_policy_bytes(descriptor)
        entries = [
            line for line in acl.splitlines() if line and not line.startswith(b"!#acl")
        ]
        if any(b":allow:" in line or b":deny:" not in line for line in entries):
            raise _LauncherAuthorityError("runtime launcher source ACL is unsafe")
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
            raise _LauncherAuthorityError("runtime launcher source identity changed")
        return opened

    def _read_exact(descriptor, size):
        if not 0 <= size <= _MAX_RUNTIME_BYTES:
            raise _LauncherAuthorityError("runtime source exceeds its byte bound")
        chunks = []
        offset = 0
        while offset < size:
            chunk = os.pread(descriptor, min(64 * 1024, size - offset), offset)
            if not chunk:
                raise _LauncherAuthorityError("runtime source changed while read")
            chunks.append(chunk)
            offset += len(chunk)
        if os.pread(descriptor, 1, size):
            raise _LauncherAuthorityError("runtime source changed while read")
        return b"".join(chunks)

    def _open_scripts_chain():
        launcher = __file__
        if (
            not isinstance(launcher, str)
            or not os.path.isabs(launcher)
            or os.path.abspath(launcher) != launcher
            or launcher.startswith("//")
            or os.path.basename(launcher) != "session_retrospective_v2.py"
        ):
            raise _LauncherAuthorityError("runtime launcher path is invalid")
        scripts = os.path.dirname(launcher)
        if os.path.basename(scripts) != "scripts":
            raise _LauncherAuthorityError("runtime launcher scripts root is invalid")
        descriptors = []
        policies = []
        try:
            current = os.open(os.path.sep, _DIRECTORY_FLAGS)
            descriptors.append(current)
            policies.append(_policy(current, True))
            for component in scripts.split(os.path.sep)[1:]:
                child = os.open(component, _DIRECTORY_FLAGS, dir_fd=current)
                policy = _policy(child, True)
                _require_named(current, component, child, True, policy)
                descriptors.append(child)
                policies.append(policy)
                current = child
            return scripts, descriptors, policies
        except BaseException:
            for descriptor in reversed(descriptors):
                try:
                    os.close(descriptor)
                except OSError:
                    pass
            raise

    def _capture_runtime():
        scripts, descriptors, ancestor_policies = _open_scripts_chain()
        runtime_descriptor = -1
        primary = None
        try:
            scripts_fd = descriptors[-1]
            runtime_descriptor = os.open(_RUNTIME_NAME, _FILE_FLAGS, dir_fd=scripts_fd)
            before = os.fstat(runtime_descriptor)
            policy = _policy(runtime_descriptor, False)
            _require_named(
                scripts_fd,
                _RUNTIME_NAME,
                runtime_descriptor,
                False,
                policy,
            )
            first = _read_exact(runtime_descriptor, before.st_size)
            middle = _require_named(
                scripts_fd,
                _RUNTIME_NAME,
                runtime_descriptor,
                False,
                policy,
            )
            second = _read_exact(runtime_descriptor, before.st_size)
            after = _require_named(
                scripts_fd,
                _RUNTIME_NAME,
                runtime_descriptor,
                False,
                policy,
            )
            if (
                _metadata_identity(before, False) != _metadata_identity(middle, False)
                or _metadata_identity(before, False) != _metadata_identity(after, False)
                or not hmac.compare_digest(first, second)
                or [_policy(descriptor, True) for descriptor in descriptors]
                != ancestor_policies
            ):
                raise _LauncherAuthorityError("runtime source changed while captured")
            return {
                "access_policy": policy,
                "descriptor": runtime_descriptor,
                "identity": _metadata_identity(before, False),
                "path": os.path.join(scripts, _RUNTIME_NAME),
                "source": first,
            }
        except BaseException as error:
            primary = error
            if runtime_descriptor >= 0:
                try:
                    os.close(runtime_descriptor)
                except OSError:
                    error.add_note("runtime descriptor cleanup failed")
            raise
        finally:
            close_failures = []
            for descriptor in reversed(descriptors):
                try:
                    os.close(descriptor)
                except OSError as error:
                    close_failures.append(error)
            if close_failures:
                if primary is not None:
                    primary.add_note("runtime launcher directory cleanup failed")
                else:
                    if runtime_descriptor >= 0:
                        try:
                            os.close(runtime_descriptor)
                        except OSError:
                            pass
                    raise _LauncherAuthorityError(
                        "runtime launcher directory cleanup failed"
                    ) from close_failures[0]

    def _execute_runtime():
        binding = _capture_runtime()
        primary = None
        try:
            code = compile(
                binding["source"],
                binding["path"],
                "exec",
                dont_inherit=True,
            )
            namespace = {
                "__builtins__": __builtins__,
                "__file__": binding["path"],
                "__name__": "__main__",
                "__package__": None,
                "__spec__": None,
                "_RETROSPECTIVE_V2_PRELOADED_ENTRY": binding,
            }
            exec(code, namespace)
            raise _LauncherAuthorityError("runtime returned without a terminal exit")
        except BaseException as error:
            primary = error
            raise
        finally:
            descriptor = binding.get("descriptor")
            if descriptor != -1 and (
                not isinstance(descriptor, int) or isinstance(descriptor, bool)
            ):
                raise _LauncherAuthorityError("runtime descriptor custody is invalid")
            if descriptor != -1:
                try:
                    os.close(descriptor)
                except OSError as error:
                    if isinstance(primary, SystemExit) and primary.code in (None, 0):
                        raise _LauncherAuthorityError(
                            "runtime descriptor cleanup failed"
                        ) from error
                    if primary is not None:
                        primary.add_note("runtime descriptor cleanup failed")
                    else:
                        raise _LauncherAuthorityError(
                            "runtime descriptor cleanup failed"
                        ) from error

    try:
        _execute_runtime()
    except SystemExit:
        raise
    except Exception:
        raise SystemExit(
            _startup_failure(
                "implementation_authority_invalid",
                "coordinator implementation authority cannot be authenticated",
            )
        )
