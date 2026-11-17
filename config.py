import os
from pathlib import Path

from dotenv import load_dotenv


# Project location and local environment.
PROJECT_DIRECTORY = Path(__file__).resolve().parent
load_dotenv(PROJECT_DIRECTORY / ".env")

# Model settings.
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "")
MAX_MODEL_CALLS_PER_TURN = 20

# Resuming: sessions per page in the startup menu, and turns reprinted after choosing one.
RESUME_SESSIONS_PER_PAGE = 10
RESUME_REPLAY_TURNS = 10

# Compaction: summarize the conversation once its input passes this share of the window.
CONTEXT_WINDOW_TOKENS = 100_000
COMPACT_AT_FRACTION = 0.7

# Tool-call classifier mode: auto | allow_all | manual.
TOOL_CLASSIFIER_MODE = "auto"
CLASSIFIER_MODEL = "gpt-6-luna"

# Prompt files.
SYSTEM_MESSAGE_FILE = PROJECT_DIRECTORY / "agent" / "prompts" / "system_message.md"
COMPACTION_SYSTEM_PROMPT_FILE = PROJECT_DIRECTORY / "compaction" / "prompts" / "system_prompt.md"
COMPACTION_INPUT_TEMPLATE_FILE = PROJECT_DIRECTORY / "compaction" / "prompts" / "input_template.md"
COMPACTION_CONTINUATION_TEMPLATE_FILE = PROJECT_DIRECTORY / "compaction" / "prompts" / "continuation_template.md"
TOOL_CLASSIFIER_SYSTEM_PROMPT_FILE = PROJECT_DIRECTORY / "tool_classifier" / "prompts" / "system_prompt.md"
TOOL_CLASSIFIER_INPUT_TEMPLATE_FILE = PROJECT_DIRECTORY / "tool_classifier" / "prompts" / "input_template.md"

# Session folders: one per run, holding its history; the container sees them read-only.
SESSIONS_DIRECTORY = PROJECT_DIRECTORY / "sessions"
CONTAINER_SESSIONS_DIRECTORY = "/sessions"
HISTORY_FILE_NAME = "history.jsonl"

# Workspace locations.
DEFAULT_WORKSPACE_DIRECTORY = PROJECT_DIRECTORY / "workspace"
CONTAINER_WORKSPACE_DIRECTORY = "/workspace"

# Tracing in a local Phoenix server; the README's Tracing section has the docker run command.
TRACING_ENABLED = True
PHOENIX_PROJECT_NAME = "harness"
PHOENIX_ENDPOINT = "http://localhost:6006/v1/traces"

# Docker execution.
SANDBOX_IMAGE = "harness-sandbox:local"
SANDBOX_NETWORK = "bridge"
TOOL_TIMEOUT_SECONDS = 60
