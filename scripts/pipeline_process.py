"""Bounded subprocess execution and process-group cleanup on Linux."""

import os
import signal
import subprocess
import threading
import time
from pathlib import Path


class PipelineStopped(Exception):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def stop_group(process):
    """Stop the command and remaining children in its process group."""
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass

    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass

    # The parent may have exited while a child is still running.
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass

    process.wait(timeout=5)


def run_process(command, *, cwd, log_path, timeout, should_cancel):
    """Run an internal command list; never invoke a shell."""
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    environment = dict(os.environ)
    environment.update({
        "NO_COLOR": "1",
        "DVC_NO_ANALYTICS": "1",
        "PYTHONUNBUFFERED": "1",
    })

    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )

    errors = []

    def collect_output():
        try:
            remaining = 1024 * 1024
            truncated = False
            with log_path.open("wb") as handle:
                while True:
                    chunk = process.stdout.read(4096)
                    if not chunk:
                        break
                    written = min(remaining, len(chunk))
                    if written:
                        handle.write(chunk[:written])
                        remaining -= written
                    if written < len(chunk) and not truncated:
                        handle.write(b"\n[Further output omitted: log size limit]\n")
                        truncated = True
        except Exception as error:
            errors.append(error)

    reader = threading.Thread(target=collect_output, daemon=True)
    reader.start()
    deadline = time.monotonic() + timeout

    try:
        while process.poll() is None:
            if should_cancel():
                raise PipelineStopped("cancelled")
            if time.monotonic() >= deadline:
                raise PipelineStopped("timeout")
            time.sleep(0.25)
        return_code = process.returncode
    finally:
        stop_group(process)
        reader.join(timeout=5)
        if not reader.is_alive():
            process.stdout.close()

    if reader.is_alive():
        raise RuntimeError("Process log collector did not stop.")
    if errors:
        raise RuntimeError("Could not write the pipeline log.") from errors[0]
    return return_code
