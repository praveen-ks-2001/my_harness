import os
import signal
import subprocess
from pathlib import Path

from tools.registry import tool


@tool
def run_command(command: str) -> dict:
    """Run a Bash command in the workspace.

    Use for listing/searching files, scripts, package installation, tests, and Git.
    Returns stdout, stderr, exit_code, and timed_out. Each call starts in the workspace;
    cd does not persist between calls.

    Args:
        command: Bash command to run.
    """
    timeout_seconds = int(os.environ["TOOL_TIMEOUT_SECONDS"])
    process = subprocess.Popen(
        ["bash", "-c", command], cwd=Path.cwd(),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace", start_new_session=True,
    )
    timed_out = False
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        stdout, stderr = process.communicate()
    return {
        "stdout": stdout,
        "stderr": stderr,
        "exit_code": 124 if timed_out else process.returncode,
        "timed_out": timed_out,
    }
