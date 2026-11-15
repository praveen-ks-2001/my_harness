import json
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import PathCompleter, WordCompleter
from prompt_toolkit.key_binding import KeyBindings
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text

import config


# Rich prints colored output; prompt_toolkit reads input with editing, history
# (Up/Down arrows), Tab completion, and multi-line paste kept as one message.
console = Console()

# Terminals send the same key code for Enter and Shift+Enter, so Enter always sends the
# message. Esc then Enter, or Ctrl+J, inserts a new line instead.
newline_keys = KeyBindings()


@newline_keys.add("escape", "enter")
@newline_keys.add("c-j")
def insert_newline(event):
    event.current_buffer.insert_text("\n")


user_prompt = PromptSession(
    completer=WordCompleter(
        [
            "/compact",
            "/tool-classifier",
            "/tool-classifier auto",
            "/tool-classifier allow_all",
            "/tool-classifier manual",
            "quit",
            "exit",
        ],
        sentence=True,
    ),
    key_bindings=newline_keys,
)
approval_prompt = PromptSession()
folder_prompt = PromptSession(completer=PathCompleter(only_directories=True, expanduser=True))

LABEL_STYLES = {
    "USER": "bold green",
    "ASSISTANT": "bold cyan",
    "REASONING": "bold magenta",
    "REFUSAL": "bold red",
    "TOOL": "bold yellow",
    "TOOL RESULT": "bold yellow",
    "COMPACTION": "bold blue",
    "APPROVAL": "bold yellow",
    "REJECTED": "bold red",
    "ERROR": "bold red",
}
CONTENT_LABELS = {"output_text": "ASSISTANT", "refusal": "REFUSAL"}


def print_label(label):
    console.print(Text(f"\n[{label}]", style=LABEL_STYLES.get(label, "bold white")))


def print_notice(label, text):
    """Print a label and a line of plain text, such as [INFO] or [ERROR] messages."""
    print_label(label)
    console.print(Text(text))


def read_user_message():
    print_label("USER")
    return user_prompt.prompt("> ").strip()


def print_stream(stream):
    """Print reasoning summaries and assistant text while the model writes them.

    Assistant text is re-rendered as Markdown on every new piece, so headings, lists,
    and code blocks appear formatted while the answer streams in.
    """
    answer = None
    for event in stream:
        if event.type == "response.reasoning_summary_part.added":
            print_label("REASONING")
        elif event.type == "response.reasoning_summary_text.delta":
            console.print(Text(event.delta, style="dim italic"), end="")
        elif event.type == "response.reasoning_summary_part.done":
            console.print()
        elif event.type == "response.content_part.added":
            label = CONTENT_LABELS.get(event.part.type, event.part.type.upper())
            print_label(label)
            if label == "ASSISTANT":
                answer_text = ""
                answer = Live(Markdown(""), console=console, refresh_per_second=12, vertical_overflow="visible")
                answer.start()
        elif event.type == "response.output_text.delta":
            answer_text += event.delta
            answer.update(Markdown(answer_text))
        elif event.type == "response.refusal.delta":
            console.print(Text(event.delta, style="red"), end="")
        elif event.type == "response.content_part.done":
            if answer is not None:
                answer.stop()
                answer = None
            else:
                console.print()
        elif event.type == "response.output_item.done":
            # Function calls print when they run; other item types are only saved.
            if event.item.type not in {"reasoning", "message", "function_call"}:
                print_notice(event.item.type.upper(), "Saved in chat history.")


def print_tool_call(name, arguments):
    print_label("TOOL")
    console.print(Text(name, style="yellow"))
    console.print(Syntax(pretty_json(arguments), "json", word_wrap=True))


def print_tool_result(result):
    print_label("TOOL RESULT")
    console.print(Panel(Syntax(pretty_json(result), "json", word_wrap=True), border_style="dim"))


def pretty_json(text):
    """Indent JSON for display; return other text unchanged."""
    try:
        return json.dumps(json.loads(text), indent=2, ensure_ascii=False)
    except json.JSONDecodeError:
        return text


def ask_tool_approval():
    """Ask whether the tool call just printed may run; return (allowed, note).

    Accepts y/yes or n/no, optionally followed by a note, such as "n, use a safer command".
    """
    print_label("APPROVAL")
    while True:
        answer = approval_prompt.prompt("Run this tool call? [y/n, optional note] ").strip()
        first_word, _, note = answer.replace(",", " ", 1).partition(" ")
        if first_word.lower() in {"y", "yes"}:
            return True, note.strip()
        if first_word.lower() in {"n", "no"}:
            return False, note.strip()
        print_notice("ERROR", "Please start with y or n.")

def print_classifier_mode(tool_classifier):
    modes = "|".join(tool_classifier.MODES)
    print_notice("INFO", f"Tool classifier: {tool_classifier.mode} (change with /tool-classifier {modes})")


def change_classifier_mode(tool_classifier, user_message):
    """Handle /tool-classifier [mode]: switch the mode if one is given, then show it."""
    words = user_message.split()
    if len(words) == 2 and words[1] in tool_classifier.MODES:
        tool_classifier.mode = words[1]
    elif len(words) != 1:
        print_notice("ERROR", f"Unknown mode. Choose one of: {', '.join(tool_classifier.MODES)}.")
    print_classifier_mode(tool_classifier)

def choose_workspace():
    print_notice("WORKSPACE", f"Enter a working folder (Tab completes paths), or press Enter for {config.DEFAULT_WORKSPACE_DIRECTORY}")
    while True:
        selected_directory = folder_prompt.prompt("Folder: ").strip()
        if selected_directory:
            workspace_directory = Path(selected_directory).expanduser().resolve()
        else:
            workspace_directory = config.DEFAULT_WORKSPACE_DIRECTORY.resolve()
            workspace_directory.mkdir(parents=True, exist_ok=True)
        if workspace_directory.is_dir():
            return workspace_directory
        print_notice("ERROR", "That folder does not exist. Please choose an existing folder.")
