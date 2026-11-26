import os
from pathlib import Path

from tools.registry import tool


def _resolve_workspace_path(path):
    workspace_directory = Path.cwd().resolve()
    file_path = (workspace_directory / path).resolve()
    if not file_path.is_relative_to(workspace_directory):
        raise ValueError("File paths must stay inside the workspace")
    return file_path


def _resolve_readable_path(path):
    """Resolve a path for reading: inside the workspace, or inside the read-only sessions folder."""
    workspace_directory = Path.cwd().resolve()
    sessions_directory = Path(os.environ["SESSIONS_DIRECTORY"]).resolve()
    file_path = (workspace_directory / path).resolve()
    readable = file_path.is_relative_to(workspace_directory) or file_path.is_relative_to(sessions_directory)
    if not readable:
        raise ValueError("read_file reads only the workspace and the sessions folder")
    return file_path


@tool
def read_file(path: str, start_line: int = 1, end_line: int | None = None) -> str:
    """Read a UTF-8 text file with line numbers, from the workspace or the read-only /sessions folder.

    A header gives the file's size. Each call returns a limited number of characters: a read
    stops at the last whole line that fits and its footer says where to continue.

    Args:
        path: File path relative to the workspace, or an absolute path inside /workspace or /sessions.
        start_line: First line to return, counting from 1.
        end_line: Last line to return, inclusive. Reads as far as the character limit allows when omitted.
    """
    if start_line < 1 or (end_line is not None and end_line < start_line):
        raise ValueError("Line numbers must start at 1, with end_line at or after start_line")
    content = _resolve_readable_path(path).read_text(encoding="utf-8")
    lines = content.splitlines()
    if not lines:
        return f"[{path}: empty file]"
    if start_line > len(lines):
        raise ValueError(f"start_line exceeds the file's {len(lines)} lines")
    max_chars = int(os.environ["READ_FILE_MAX_CHARS"])
    last_requested = len(lines) if end_line is None else min(end_line, len(lines))

    # Take whole lines until the next one would pass the character limit.
    shown = []
    used_chars = 0
    for line_number in range(start_line, last_requested + 1):
        numbered_line = f"{line_number}: {lines[line_number - 1]}"
        if used_chars + len(numbered_line) > max_chars:
            break
        shown.append(numbered_line)
        used_chars += len(numbered_line) + 1

    # A single line longer than the limit is cut; the rest is reachable with bash.
    if not shown:
        line = lines[start_line - 1]
        kept_chars = max_chars - len(f"{start_line}: ")
        shown.append(
            f"{start_line}: {line[:kept_chars]} …[line cut: it has {len(line):,} characters. Slice the rest with bash, "
            f"e.g. sed -n '{start_line}p' {path} | cut -c{kept_chars + 1}-{kept_chars + max_chars}; see Large outputs.]"
        )
    last_shown = start_line + len(shown) - 1

    header = f"[{path}: {len(content):,} characters, {len(lines):,} lines. Showing lines {start_line}-{last_shown}.]"
    if last_shown == len(lines):
        footer = "[End of file]"
    elif last_shown < last_requested:
        end_argument = f", end_line={end_line}" if end_line is not None else ""
        footer = (
            f"[Stopped at line {last_shown}: the {max_chars:,}-character limit was reached. "
            f'To continue: read_file(path="{path}", start_line={last_shown + 1}{end_argument}), '
            f"or search it with bash.]"
        )
    else:
        footer = f"[{len(lines) - last_shown:,} more lines after line {last_shown}.]"
    return "\n".join([header, *shown, footer])


@tool
def write_file(path: str, content: str, overwrite: bool = False) -> str:
    """Write a workspace UTF-8 file, creating missing parent folders.

    Refuses to replace an existing file unless overwrite is true; prefer edit_file for
    small changes.

    Args:
        path: File path relative to the workspace.
        content: Complete content of the file.
        overwrite: Replace the file if it already exists.
    """
    file_path = _resolve_workspace_path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    if overwrite:
        file_existed = file_path.exists()
        with file_path.open("w", encoding="utf-8", newline="") as file:
            file.write(content)
        return f"{'Overwrote' if file_existed else 'Created'} {path}"
    if file_path.exists():
        raise FileExistsError(f"{path} already exists; set overwrite to true to replace it")
    with file_path.open("x", encoding="utf-8", newline="") as file:
        file.write(content)
    return f"Created {path}"


@tool
def edit_file(path: str, old_text: str, new_text: str) -> str:
    """Edit an existing workspace UTF-8 file by replacing old_text with new_text.

    old_text must match exactly once; use a unique snippet from read_file.

    Args:
        path: Existing file path relative to the workspace.
        old_text: Exact, nonempty text to replace.
        new_text: Replacement text.
    """
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
