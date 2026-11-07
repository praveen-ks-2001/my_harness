import os
from pathlib import Path


PROJECT_DIRECTORY = Path(__file__).resolve().parent
HISTORY_DIRECTORY = PROJECT_DIRECTORY / "chat_history"
SYSTEM_MESSAGE_FILE = PROJECT_DIRECTORY / "prompts" / "system_message.md"
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "")
