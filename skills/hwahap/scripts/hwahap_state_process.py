"""Bounded process execution for trusted state metadata reads."""
from __future__ import annotations
import selectors
import os
import subprocess
import time
from pathlib import Path
from hwahap_state_runtime import register
register(globals())


def _bounded_process_output(command: list[str], cwd: Path, env: dict[str, str],
                           limit: int, timeout: float) -> bytes:
    process = subprocess.Popen(command, cwd=cwd, env=env, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, start_new_session=True)
    if process.stdout is None:
        process.kill()
        raise OSError("process output unavailable")
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    output = bytearray()
    deadline = time.monotonic() + timeout
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(command, timeout)
            if not selector.select(min(remaining, 0.1)):
                continue
            chunk = os.read(process.stdout.fileno(), min(65536, limit + 1 - len(output)))
            if not chunk:
                break
            output.extend(chunk)
            if len(output) > limit:
                raise ValueError("process output limit exceeded")
        if process.wait(timeout=max(0.01, deadline - time.monotonic())) != 0:
            raise subprocess.CalledProcessError(process.returncode, command)
        return bytes(output)
    finally:
        selector.close()
        if process.poll() is None:
            process.kill()
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                pass
        process.stdout.close()
