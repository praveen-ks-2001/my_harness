import json
from datetime import datetime, timezone
from pathlib import Path

import config


class Conversation:
    """Keep the model's messages and their JSONL history together."""

    def __init__(self, workspace_directory, container_id, history_directory=None):
        self.model_input = []
        self.turn_number = 0

        if history_directory is None:
            history_directory = config.HISTORY_DIRECTORY
        history_directory = Path(history_directory)
        history_directory.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S_%f")
        self.history_path = history_directory / f"{timestamp}.jsonl"
        session_record = {
            "metadata": {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "turn_number": 0,
                "message_type": "session",
            },
            "session": {
                "workspace_directory": str(Path(workspace_directory).resolve()),
                "container_workspace_directory": config.CONTAINER_WORKSPACE_DIRECTORY,
                "container_id": container_id,
                "sandbox_image": config.SANDBOX_IMAGE,
                "sandbox_network": config.SANDBOX_NETWORK,
                "model": config.OPENAI_MODEL,
            },
        }
        with self.history_path.open("x", encoding="utf-8") as history_file:
            history_file.write(json.dumps(session_record, ensure_ascii=False) + "\n")

    def append_text_message(self, text, message_type):
        """Build and record a system, developer, user, or assistant text message."""
        if message_type not in {"system", "developer", "user", "assistant"}:
            raise ValueError(f"Unsupported text message type: {message_type}")
        api_item = {"role": message_type, "content": text}
        self._record_item(api_item, message_type)

    def append_response_item(self, item):
        """Preserve a complete SDK output item, including its continuation fields."""
        api_item = item.model_dump(exclude_none=True)
        message_type = api_item.get("role") or api_item["type"]
        self._record_item(api_item, message_type)

    def append_tool_result(self, call_id, output):
        """Build the result item linked to the model's function call."""
        api_item = {"type": "function_call_output", "call_id": call_id, "output": output}
        self._record_item(api_item, "tool_result")

    def _record_item(self, api_item, message_type):
        """Write an enriched history record and keep the original item for the API."""
        turn_number = self.turn_number
        if message_type == "user":
            turn_number += 1

        history_record = {
            "metadata": {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "turn_number": turn_number,
                "message_type": message_type,
            },
            "message": api_item,
        }
        with self.history_path.open("a", encoding="utf-8") as history_file:
            history_file.write(json.dumps(history_record, ensure_ascii=False) + "\n")

        self.model_input.append(api_item)
        self.turn_number = turn_number
