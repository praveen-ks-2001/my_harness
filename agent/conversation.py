import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import config


class Conversation:
    """Keep the model's messages and their JSONL history together.

    Create one with Conversation.start() for a new session, or Conversation.resume()
    to continue a saved one.
    """

    def __init__(self, history_path):
        self.history_path = Path(history_path)
        self.model_input = []
        self.turn_number = 0
        # The last call's exact input size, plus the characters of items added since.
        self.tokens_at_last_call = 0
        self.characters_since_last_call = 0

    @classmethod
    def start(cls, workspace_directory, container_id, history_directory=None):
        """Create a new history file with its turn-zero session record, then add the system message.

        The system message is filled with this session's history file path, as the
        container sees it, so the model can search its own history.
        """
        if history_directory is None:
            history_directory = config.HISTORY_DIRECTORY
        history_directory = Path(history_directory)
        history_directory.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        conversation = cls(history_directory / f"main_agent_{timestamp}.jsonl")
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
        with conversation.history_path.open("x", encoding="utf-8") as history_file:
            history_file.write(json.dumps(session_record, ensure_ascii=False) + "\n")

        system_message = config.SYSTEM_MESSAGE_FILE.read_text(encoding="utf-8").format(
            history_file=f"{config.CONTAINER_HISTORY_DIRECTORY}/{conversation.history_path.name}",
            history_directory=config.CONTAINER_HISTORY_DIRECTORY,
        )
        conversation.append_text_message(system_message, message_type="system")
        return conversation

    @classmethod
    def resume(cls, history_path, container_id):
        """Rebuild the model input from a history file and keep appending to that file.

        The model input is the system message plus everything after the last
        compaction_summary record (or after the system message if there is none),
        exactly what it held when the session ended.
        """
        conversation = cls(history_path)
        records = read_history(history_path)
        conversation.turn_number = max(record["metadata"]["turn_number"] for record in records)

        message_types = [record["metadata"]["message_type"] for record in records]
        system_index = message_types.index("system")
        compaction_indexes = [index for index, message_type in enumerate(message_types) if message_type == "compaction_summary"]
        first_index = compaction_indexes[-1] + 1 if compaction_indexes else system_index + 1
        for record in [records[system_index], *records[first_index:]]:
            if "message" not in record:
                # Session and session_resumed records are file-only.
                continue
            api_item = record["message"]
            conversation.model_input.append(api_item)
            # Same token bookkeeping as during the live session.
            usage = record["metadata"].get("usage")
            if usage:
                conversation.tokens_at_last_call = usage["input_tokens"] + usage["output_tokens"]
                conversation.characters_since_last_call = 0
            else:
                conversation.characters_since_last_call += len(json.dumps(api_item, ensure_ascii=False))

        # The API rejects a function call without a result, which a crash or Ctrl-C can leave.
        answered_call_ids = {item["call_id"] for item in conversation.model_input if item.get("type") == "function_call_output"}
        for item in list(conversation.model_input):
            if item.get("type") == "function_call" and item["call_id"] not in answered_call_ids:
                conversation.append_tool_result(item["call_id"], "Not run: the session ended before this tool call ran.")

        conversation._write_history_record({
            "metadata": {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "turn_number": conversation.turn_number,
                "message_type": "session_resumed",
            },
            "session": {"container_id": container_id, "model": config.OPENAI_MODEL},
        })
        return conversation

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
            extra_metadata = {"response_id": response.id}
            if item is response.output[-1]:
                extra_metadata["usage"] = response.usage.model_dump() if response.usage else None
            self._record_item(api_item, message_type, extra_metadata)

        if response.usage:
            self.tokens_at_last_call = response.usage.input_tokens + response.usage.output_tokens
            self.characters_since_last_call = 0

    def append_tool_result(self, call_id, output, decision=None):
        """Build the result item linked to the model's function call.

        The classifier's decision, if given, is saved in the history metadata only.
        """
        api_item = {"type": "function_call_output", "call_id": call_id, "output": output}
        extra_metadata = {"decision": asdict(decision)} if decision else None
        self._record_item(api_item, "tool_result", extra_metadata)

    def recent_user_messages(self, count):
        """Return the text of the last few user-role messages in the model input."""
        user_texts = [item["content"] for item in self.model_input if item.get("role") == "user"]
        return user_texts[-count:]

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

    def _record_item(self, api_item, message_type, extra_metadata=None):
        """Write an enriched history record and keep the original item for the API."""
        history_record = {
            "metadata": {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "turn_number": self.turn_number,
                "message_type": message_type,
                **(extra_metadata or {}),
            },
            "message": api_item,
        }
        self._write_history_record(history_record)

        self.model_input.append(api_item)
        self.characters_since_last_call += len(json.dumps(api_item, ensure_ascii=False))

    def _write_history_record(self, history_record):
        with self.history_path.open("a", encoding="utf-8") as history_file:
            history_file.write(json.dumps(history_record, ensure_ascii=False) + "\n")


def read_history(history_path):
    """Return every record of a history file, in order."""
    with Path(history_path).open(encoding="utf-8") as history_file:
        return [json.loads(line) for line in history_file if line.strip()]


def saved_workspace(history_path):
    """Return the workspace folder recorded in a history file's session record."""
    workspace_directory = Path(read_history(history_path)[0]["session"]["workspace_directory"])
    if not workspace_directory.is_dir():
        raise ValueError(f"The session's workspace folder no longer exists: {workspace_directory}")
    return workspace_directory


def list_saved_sessions():
    """Return every resumable session, newest first: (path, first and last user message, turns, last active)."""
    history_paths = sorted(config.HISTORY_DIRECTORY.glob("*.jsonl"), key=lambda path: path.stat().st_mtime, reverse=True)
    sessions = []
    for history_path in history_paths:
        records = read_history(history_path)
        # Files from before the turn-zero session record existed cannot be resumed.
        if not records or records[0].get("metadata", {}).get("message_type") != "session":
            continue
        user_messages = []
        previous_type = None
        for record in records:
            message_type = record["metadata"]["message_type"]
            # The continuation message after a compaction is not something the user typed.
            if message_type == "user" and previous_type != "compaction_summary":
                user_messages.append(record["message"]["content"])
            previous_type = message_type
        if not user_messages:
            continue
        last_turn = max(record["metadata"]["turn_number"] for record in records)
        last_active = datetime.fromtimestamp(history_path.stat().st_mtime)
        sessions.append((history_path, user_messages[0], user_messages[-1], last_turn, last_active))
    return sessions
