import json

import config


def cap_tool_output(result, call_id, session_directory):
    """Return the tool result as the model should see it, and the container paths of any saved full text.

    Text longer than TOOL_OUTPUT_MAX_CHARS keeps only its head and tail; the full text is saved
    in the session's tool_outputs/ folder. In a JSON object, such as bash's result, each
    long string field (stdout, stderr) is capped on its own, so the result stays valid JSON.
    """
    try:
        fields = json.loads(result)
    except json.JSONDecodeError:
        fields = None

    if isinstance(fields, dict):
        saved_paths = []
        for name, value in fields.items():
            if isinstance(value, str) and len(value) > config.TOOL_OUTPUT_MAX_CHARS:
                fields[name], saved_path = _cap_text(value, f"{call_id}.{name}.txt", session_directory)
                saved_paths.append(saved_path)
        capped_result = json.dumps(fields, ensure_ascii=False) if saved_paths else result
        return capped_result, saved_paths

    if len(result) <= config.TOOL_OUTPUT_MAX_CHARS:
        return result, []
    capped_result, saved_path = _cap_text(result, f"{call_id}.txt", session_directory)
    return capped_result, [saved_path]


def _cap_text(text, file_name, session_directory):
    """Save the full text in the session folder and return its head, a marker, and its tail."""
    output_directory = session_directory / config.TOOL_OUTPUTS_DIRECTORY_NAME
    output_directory.mkdir(exist_ok=True)
    (output_directory / file_name).write_text(text, encoding="utf-8")

    # The path as the container sees it, so the model can read the file.
    container_path = (
        f"{config.CONTAINER_SESSIONS_DIRECTORY}/{session_directory.name}/{config.TOOL_OUTPUTS_DIRECTORY_NAME}/{file_name}"
    )
    # A short hint only; the system message's Large outputs section has the full instructions.
    marker = (
        f"\n[… output truncated: {len(text):,} characters, {len(text.splitlines()):,} lines in total. "
        f"Full output: {container_path}. Slice or search it with bash; see Large outputs.]\n"
    )
    return text[:config.TOOL_OUTPUT_HEAD_CHARS] + marker + text[-config.TOOL_OUTPUT_TAIL_CHARS:], container_path
