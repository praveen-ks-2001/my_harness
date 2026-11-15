import json
from datetime import datetime, timezone
from pathlib import Path

import config


class Conversation:
    """Keep the model's messages and their JSONL history together."""

    def __init__(self, workspace_directory, container_id, history_directory=None):
        self.model_input = []
        self.turn_number = 0
        # The last call's exact input size, plus the characters of items added since.
        self.tokens_at_last_call = 0
        self.characters_since_last_call = 0

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
        if message_type == "user":
            self.turn_number += 1
        api_item = {"role": message_type, "content": text}
        self._record_item(api_item, message_type)

    def append_model_response(self, response):
        """Preserve every output item of one model call, including continuation fields.

        Each item's metadata names the response it came from; the last item's metadata
        also holds the call's token usage.
        """
        for item in response.output:
            api_item = item.model_dump(exclude_none=True)
            message_type = api_item.get("role") or api_item["type"]
            response_metadata = {"response_id": response.id}
            if item is response.output[-1]:
                response_metadata["usage"] = response.usage.model_dump() if response.usage else None
            self._record_item(api_item, message_type, response_metadata)

        if response.usage:
            self.tokens_at_last_call = response.usage.input_tokens + response.usage.output_tokens
            self.characters_since_last_call = 0

    def append_tool_result(self, call_id, output):
        """Build the result item linked to the model's function call."""
        api_item = {"type": "function_call_output", "call_id": call_id, "output": output}
        self._record_item(api_item, "tool_result")

    def estimated_input_tokens(self):
        """Estimate the next call's input: exact tokens so far plus about 4 characters per token."""
        return self.tokens_at_last_call + self.characters_since_last_call // 4

    def replace_with_compaction(self, compaction_response, continuation_text, trigger):
        """Record the summary, then restart model input from the system message and the continuation message."""
        compaction_record = {
            "metadata": {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "turn_number": self.turn_number,
                "message_type": "compaction_summary",
                "trigger": trigger,
                "response_id": compaction_response.id,
                "usage": compaction_response.usage.model_dump() if compaction_response.usage else None,
            },
            "compaction": {"summary": compaction_response.output_text},
        }
        self._write_history_record(compaction_record)

        system_item = self.model_input[0]
        self.model_input = [system_item]
        self.tokens_at_last_call = 0
        self.characters_since_last_call = len(json.dumps(system_item, ensure_ascii=False))
        # Recorded directly, not through append_text_message, so the turn does not advance.
        self._record_item({"role": "user", "content": continuation_text}, "user")

    def _record_item(self, api_item, message_type, response_metadata=None):
        """Write an enriched history record and keep the original item for the API."""
        history_record = {
            "metadata": {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "turn_number": self.turn_number,
                "message_type": message_type,
                **(response_metadata or {}),
            },
            "message": api_item,
        }
        self._write_history_record(history_record)

        self.model_input.append(api_item)
        self.characters_since_last_call += len(json.dumps(api_item, ensure_ascii=False))

    def _write_history_record(self, history_record):
        with self.history_path.open("a", encoding="utf-8") as history_file:
            history_file.write(json.dumps(history_record, ensure_ascii=False) + "\n")
