"""Shared unreaped-process lifecycle checks for bounded subprocess owners."""

from __future__ import annotations

import os
import subprocess
import time
from typing import Callable


class GroupSignalRetirement:
    """Publish when reaping may make a saved process-group ID reusable."""

    def __init__(self) -> None:
        self.retired = False

    def retire(self) -> None:
        self.retired = True


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

    try:
        return process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        try:
            process.kill()
        except OSError:
            pass
        try:
            return process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired as error:
            raise error_type(error_message) from error


def finish_cleanup(
    process: subprocess.Popen[bytes],
    *,
    signal_retired: bool,
    terminate_and_reap: Callable[[subprocess.Popen[bytes]], int],
    reap_only: Callable[[subprocess.Popen[bytes]], int],
    active_error: BaseException | None,
) -> None:
    """Finish cleanup without replacing an active primary failure."""

    try:
        (reap_only if signal_retired else terminate_and_reap)(process)
    except RuntimeError as cleanup_error:
        if active_error is None:
            raise
        active_error.add_note(str(cleanup_error))
