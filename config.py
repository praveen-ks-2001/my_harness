import os
from pathlib import Path

from dotenv import load_dotenv


# Project location and local environment.
PROJECT_DIRECTORY = Path(__file__).resolve().parent
load_dotenv(PROJECT_DIRECTORY / ".env")

# Model settings.
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "")
MAX_MODEL_CALLS_PER_TURN = 20

# Compaction: summarize the conversation once its input passes this share of the window.
CONTEXT_WINDOW_TOKENS = 100_000
COMPACT_AT_FRACTION = 0.7

# Prompt and conversation history.
SYSTEM_MESSAGE_FILE = PROJECT_DIRECTORY / "agent" / "prompts" / "system_message.md"
COMPACTION_SYSTEM_PROMPT_FILE = PROJECT_DIRECTORY / "compaction" / "prompts" / "system_prompt.md"
COMPACTION_INPUT_TEMPLATE_FILE = PROJECT_DIRECTORY / "compaction" / "prompts" / "input_template.md"
COMPACTION_CONTINUATION_TEMPLATE_FILE = PROJECT_DIRECTORY / "compaction" / "prompts" / "continuation_template.md"
HISTORY_DIRECTORY = PROJECT_DIRECTORY / "chat_history"

# Workspace locations.
DEFAULT_WORKSPACE_DIRECTORY = PROJECT_DIRECTORY / "workspace"
CONTAINER_WORKSPACE_DIRECTORY = "/workspace"
CONTAINER_HISTORY_DIRECTORY = "/chat_history"

# Docker execution.
SANDBOX_IMAGE = "harness-sandbox:local"
SANDBOX_NETWORK = "bridge"
TOOL_TIMEOUT_SECONDS = 60
