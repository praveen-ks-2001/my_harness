import os
from pathlib import Path

from dotenv import load_dotenv


# Project location and local environment.
PROJECT_DIRECTORY = Path(__file__).resolve().parent
load_dotenv(PROJECT_DIRECTORY / ".env")

# Model settings.
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "")

# Prompt and conversation history.
SYSTEM_MESSAGE_FILE = PROJECT_DIRECTORY / "prompts" / "system_message.md"
HISTORY_DIRECTORY = PROJECT_DIRECTORY / "chat_history"

# Workspace locations.
DEFAULT_WORKSPACE_DIRECTORY = PROJECT_DIRECTORY / "workspace"
CONTAINER_WORKSPACE_DIRECTORY = "/workspace"

# Docker execution.
SANDBOX_IMAGE = "harness-sandbox:local"
SANDBOX_NETWORK = "bridge"
TOOL_TIMEOUT_SECONDS = 60
