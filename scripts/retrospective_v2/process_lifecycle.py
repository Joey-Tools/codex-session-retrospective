"""Shared unreaped-process lifecycle checks for bounded subprocess owners."""

from __future__ import annotations

import errno
import os
import signal
import subprocess
import time
from typing import Callable


_CLEANUP_INCOMPLETE_ATTRIBUTE = "_retrospective_process_group_cleanup_incomplete"
_CLEANUP_CAUSE_LIMIT = 16
_GROUP_ABSENCE_POLL_SECONDS = 0.01


class ProcessGroupCleanupIncompleteError(RuntimeError):
    """Raised when a caller would otherwise downgrade unproven cleanup."""


class GroupSignalRetirement:
    """Separate signal retirement from proof that the group is absent."""

    def __init__(self) -> None:
        self.retired = False
        self.group_absence_proven = False

    def retire(self) -> None:
        self.retired = True

    def prove_group_absence(self) -> None:
        if not self.retired:
            raise RuntimeError("process-group signal authority is still active")
        self.group_absence_proven = True


def wait_for_unreaped_exit(
    process: subprocess.Popen[bytes],
    *,
    deadline: float,
    error_type: type[Exception],
    deadline_message: str,
    status_message: str,
    poll_seconds: float = 0.01,
) -> None:
    """Wait for a leader to become terminal without releasing its PID fence."""

    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise error_type(deadline_message)
        try:
            observed = os.waitid(
                os.P_PID,
                process.pid,
                os.WEXITED | os.WNOHANG | os.WNOWAIT,
            )
        except InterruptedError:
            continue
        except (AttributeError, ChildProcessError, OSError) as error:
            raise error_type(status_message) from error
        if observed is not None and observed.si_pid == process.pid:
            return
        time.sleep(min(poll_seconds, remaining))


def reap_after_termination(
    process: subprocess.Popen[bytes],
    *,
    timeout_seconds: float,
    error_type: type[Exception],
    error_message: str,
) -> int:
    """Reap a previously terminated leader without another group signal."""

    deadline = time.monotonic() + timeout_seconds

    def remaining_seconds() -> float:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise error_type(error_message)
        return remaining

    try:
        return process.wait(timeout=remaining_seconds())
    except OSError as error:
        raise error_type(error_message) from error
    except subprocess.TimeoutExpired:
        try:
            process.kill()
        except OSError:
            pass
        try:
            return process.wait(timeout=remaining_seconds())
        except (OSError, subprocess.TimeoutExpired) as error:
            raise error_type(error_message) from error


def close_process_group(
    process: subprocess.Popen[bytes],
    *,
    signal_retirement: GroupSignalRetirement,
    timeout_seconds: float,
    error_type: type[RuntimeError],
    label: str,
    termination_message: str,
) -> int:
    """Signal a pinned task group, reap its leader, and prove group absence."""

    deadline = time.monotonic() + timeout_seconds
    process_group_id = process.pid

    def remaining_seconds() -> float:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise error_type(termination_message)
        return remaining

    def prove_group_absent() -> None:
        if os.name != "posix":
            return
        while True:
            try:
                os.killpg(process_group_id, 0)
            except OSError as probe_error:
                if probe_error.errno == errno.ESRCH:
                    return
                if probe_error.errno == errno.EINTR:
                    continue
                if probe_error.errno != errno.EPERM:
                    raise error_type(
                        f"{label} process group closure is unproven"
                    ) from probe_error
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise error_type(f"{label} process group closure is unproven")
            time.sleep(min(_GROUP_ABSENCE_POLL_SECONDS, remaining))

    if signal_retirement.retired:
        return_code = reap_after_termination(
            process,
            timeout_seconds=remaining_seconds(),
            error_type=error_type,
            error_message=termination_message,
        )
        prove_group_absent()
        signal_retirement.prove_group_absence()
        return return_code

    # Retire before the syscall attempt: interruption can make its side effect
    # ambiguous, so a cleanup retry must never signal the saved PGID again.
    signal_retirement.retire()
    try:
        if os.name == "posix":
            os.killpg(process_group_id, signal.SIGKILL)
        else:
            process.kill()
    except OSError as signal_error:
        if signal_error.errno == errno.ESRCH:
            pass
        elif os.name == "posix" and signal_error.errno == errno.EPERM:
            return_code = reap_after_termination(
                process,
                timeout_seconds=remaining_seconds(),
                error_type=error_type,
                error_message=termination_message,
            )
            try:
                prove_group_absent()
            except error_type as closure_error:
                raise closure_error from signal_error
            signal_retirement.prove_group_absence()
            return return_code
        else:
            raise error_type(
                f"{label} process group could not be signaled"
            ) from signal_error
    return_code = reap_after_termination(
        process,
        timeout_seconds=remaining_seconds(),
        error_type=error_type,
        error_message=termination_message,
    )
    prove_group_absent()
    signal_retirement.prove_group_absence()
    return return_code


def finish_cleanup(
    process: subprocess.Popen[bytes],
    *,
    signal_retirement: GroupSignalRetirement,
    terminate_and_reap: Callable[[subprocess.Popen[bytes]], int],
    reap_only: Callable[[subprocess.Popen[bytes]], int],
    active_error: BaseException | None,
) -> None:
    """Finish cleanup without replacing an active primary failure."""

    try:
        cleanup = (
            reap_only
            if signal_retirement.retired and signal_retirement.group_absence_proven
            else terminate_and_reap
        )
        cleanup(process)
    except RuntimeError as cleanup_error:
        setattr(cleanup_error, _CLEANUP_INCOMPLETE_ATTRIBUTE, True)
        if active_error is None:
            raise
        setattr(active_error, _CLEANUP_INCOMPLETE_ATTRIBUTE, True)
        active_error.add_note(str(cleanup_error))


def finish_cleanup_after_resource_teardown(
    process: subprocess.Popen[bytes],
    *,
    resource_closers: tuple[Callable[[], None], ...],
    resource_label: str,
    signal_retirement: GroupSignalRetirement,
    terminate_and_reap: Callable[[subprocess.Popen[bytes]], int],
    reap_only: Callable[[subprocess.Popen[bytes]], int],
    active_error: BaseException | None,
) -> None:
    """Close every local resource without bypassing process-group cleanup."""

    resource_error: BaseException | None = None
    for closer in resource_closers:
        try:
            closer()
        except BaseException as error:
            if resource_error is None:
                resource_error = error
            else:
                resource_error.add_note(
                    f"additional {resource_label} failure: {type(error).__name__}"
                )
    if active_error is not None and resource_error is not None:
        active_error.add_note(
            f"{resource_label} failed: {type(resource_error).__name__}"
        )
    finish_cleanup(
        process,
        signal_retirement=signal_retirement,
        terminate_and_reap=terminate_and_reap,
        reap_only=reap_only,
        active_error=active_error or resource_error,
    )
    if active_error is None and resource_error is not None:
        raise resource_error


def has_incomplete_process_group_cleanup(error: BaseException) -> bool:
    """Find a cleanup marker through a bounded exception-cause chain."""

    current: BaseException | None = error
    visited: set[int] = set()
    for _ in range(_CLEANUP_CAUSE_LIMIT):
        if current is None or id(current) in visited:
            return False
        visited.add(id(current))
        if getattr(current, _CLEANUP_INCOMPLETE_ATTRIBUTE, False) is True:
            return True
        current = current.__cause__ or current.__context__
    return False


def incomplete_process_group_cleanup_primary(
    error: BaseException,
) -> BaseException | None:
    """Return the outer command primary while unwrapping cleanup-only errors."""

    if not has_incomplete_process_group_cleanup(error):
        return None
    current: BaseException | None = error
    visited: set[int] = set()
    for _ in range(_CLEANUP_CAUSE_LIMIT):
        if current is None or id(current) in visited:
            return None
        visited.add(id(current))
        if not isinstance(current, ProcessGroupCleanupIncompleteError):
            return current
        current = current.__cause__ or current.__context__
    return None


def raise_if_incomplete_process_group_cleanup(error: BaseException) -> None:
    """Prevent ordinary availability/readiness fallbacks from hiding cleanup."""

    if not has_incomplete_process_group_cleanup(error):
        return
    if isinstance(error, ProcessGroupCleanupIncompleteError):
        raise error
    failure = ProcessGroupCleanupIncompleteError(
        "subprocess process-group cleanup could not be proven complete"
    )
    setattr(failure, _CLEANUP_INCOMPLETE_ATTRIBUTE, True)
    raise failure from error
