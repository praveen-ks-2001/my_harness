import os
from pathlib import Path


PROJECT_DIRECTORY = Path(__file__).resolve().parent
HISTORY_DIRECTORY = PROJECT_DIRECTORY / "chat_history"
SYSTEM_MESSAGE_FILE = PROJECT_DIRECTORY / "prompts" / "system_message.md"
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "")
DEFAULT_WORKSPACE_DIRECTORY = PROJECT_DIRECTORY / "workspace"
CONTAINER_WORKSPACE_DIRECTORY = "/workspace"
SANDBOX_IMAGE = "harness-sandbox:local"
TOOL_TIMEOUT_SECONDS = 60
