import json
import os
import signal
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


def current_time(timezone="UTC"):
    return datetime.now(ZoneInfo(timezone)).isoformat()


def _resolve_workspace_path(path):
    workspace_directory = Path.cwd().resolve()
    file_path = (workspace_directory / path).resolve()
    if not file_path.is_relative_to(workspace_directory):
        raise ValueError("File paths must stay inside the workspace")
    return file_path


def read_file(path, start_line=1, end_line=None):
    """Read UTF-8 text with one-based line numbers and optional inclusive bounds."""
    if start_line < 1 or (end_line is not None and end_line < start_line):
        raise ValueError("Line numbers must start at 1, with end_line at or after start_line")
    lines = _resolve_workspace_path(path).read_text(encoding="utf-8").splitlines()
    if not lines:
        return "(empty file)"
    if start_line > len(lines):
        raise ValueError(f"start_line exceeds the file's {len(lines)} lines")
    return "\n".join(
        f"{line_number}: {line}"
        for line_number, line in enumerate(lines[start_line - 1:end_line], start=start_line)
    )


def write_file(path, content):
    """Create a UTF-8 file and its parent folders, refusing to overwrite a file."""
    if not isinstance(content, str):
        raise TypeError("content must be a string")
    file_path = _resolve_workspace_path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with file_path.open("x", encoding="utf-8", newline="") as file:
        file.write(content)
    return f"Created {path}"


def edit_file(path, old_text, new_text):
    """Replace an exact, unique text match in an existing UTF-8 file."""
    if not old_text:
        raise ValueError("old_text must not be empty")
    file_path = _resolve_workspace_path(path)
    with file_path.open("r", encoding="utf-8", newline="") as file:
        content = file.read()
    if old_text not in content:
        raise ValueError("old_text was not found; read the file before editing")
    if content.find(old_text) != content.rfind(old_text):
        raise ValueError("old_text matches more than once; provide a larger, unique snippet")
    updated_content = content.replace(old_text, new_text, 1)
    with file_path.open("w", encoding="utf-8", newline="") as file:
        file.write(updated_content)
    return f"Updated {path}"


def run_command(command):
    """Run Bash in the workspace and report output, exit code, and timeout status."""
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


TOOLS = {
    "current_time": current_time,
    "read_file": read_file,
    "write_file": write_file,
    "edit_file": edit_file,
    "run_command": run_command,
}

TOOL_SCHEMAS = [
    {
        "type": "function",
        "name": "current_time",
        "description": "Get the current date and time in an IANA timezone, such as Asia/Kolkata.",
        "parameters": {
            "type": "object",
            "properties": {"timezone": {"type": "string"}},
            "additionalProperties": False,
        },
        "strict": False,
    },
    {
        "type": "function",
        "name": "read_file",
        "description": (
            "Read a workspace UTF-8 file with line numbers. "
            "Line bounds are one-based and inclusive."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path relative to the workspace."},
                "start_line": {"type": "integer", "minimum": 1, "default": 1},
                "end_line": {"type": ["integer", "null"], "minimum": 1},
            },
            "required": ["path"],
            "additionalProperties": False,
        },
        "strict": False,
    },
    {
        "type": "function",
        "name": "write_file",
        "description": (
            "Create a new workspace UTF-8 file and any missing parent folders. "
            "Refuses to overwrite an existing file; use edit_file for updates."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "New file path relative to the workspace."},
                "content": {"type": "string", "description": "Complete content of the new file."},
            },
            "required": ["path", "content"],
            "additionalProperties": False,
        },
        "strict": False,
    },
    {
        "type": "function",
        "name": "edit_file",
        "description": (
            "Edit an existing workspace UTF-8 file by replacing old_text with new_text. "
            "old_text must match exactly once; use a unique snippet from read_file."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Existing file path relative to the workspace."},
                "old_text": {"type": "string", "minLength": 1},
                "new_text": {"type": "string"},
            },
            "required": ["path", "old_text", "new_text"],
            "additionalProperties": False,
        },
        "strict": False,
    },
    {
        "type": "function",
        "name": "run_command",
        "description": (
            "Run a Bash command in the workspace. Use for listing/searching files, "
            "scripts, package installation, tests, and Git. Returns stdout, stderr, "
            "exit_code, and timed_out. Each call starts in the workspace; "
            "cd does not persist between calls."
        ),
        "parameters": {
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
            "additionalProperties": False,
        },
        "strict": False,
    },
]


def call_tool(sandbox, name, arguments):
    """Send registered tool calls to the container, with the JSON arguments on stdin."""
    try:
        return sandbox.execute(["python", "-I", "/opt/harness/tools.py", name], input_text=arguments)
    except RuntimeError as error:
        return json.dumps({"error": str(error)})


if __name__ == "__main__":
    # This entry point is invoked by Docker, not by the host conversation loop.
    try:
        result = TOOLS[sys.argv[1]](**json.loads(sys.stdin.read()))
        print(result if isinstance(result, str) else json.dumps(result))
    except Exception as error:
        print(json.dumps({"error": str(error)}))
