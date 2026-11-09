from pathlib import Path

from tools.registry import tool


def _resolve_workspace_path(path):
    workspace_directory = Path.cwd().resolve()
    file_path = (workspace_directory / path).resolve()
    if not file_path.is_relative_to(workspace_directory):
        raise ValueError("File paths must stay inside the workspace")
    return file_path


@tool
def read_file(path: str, start_line: int = 1, end_line: int | None = None) -> str:
    """Read a workspace UTF-8 file with line numbers.

    Args:
        path: File path relative to the workspace.
        start_line: First line to return, counting from 1.
        end_line: Last line to return, inclusive. Reads to the end of the file when omitted.
    """
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
