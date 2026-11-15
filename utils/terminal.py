from pathlib import Path

import config


CONTENT_LABELS = {"output_text": "ASSISTANT", "refusal": "REFUSAL"}
STREAMED_TEXT_EVENTS = {
    "response.reasoning_summary_text.delta",
    "response.output_text.delta",
    "response.refusal.delta",
}


def print_stream(stream):
    """Print reasoning summaries and assistant text while the model writes them."""
    for event in stream:
        if event.type == "response.reasoning_summary_part.added":
            print("\n[REASONING]")
        elif event.type == "response.content_part.added":
            label = CONTENT_LABELS.get(event.part.type, event.part.type.upper())
            print(f"\n[{label}]")
        elif event.type in STREAMED_TEXT_EVENTS:
            print(event.delta, end="", flush=True)
        elif event.type in {"response.reasoning_summary_part.done", "response.content_part.done"}:
            print()
        elif event.type == "response.output_item.done":
            # Function calls print when they run; other item types are only saved.
            if event.item.type not in {"reasoning", "message", "function_call"}:
                print(f"\n[{event.item.type.upper()}]\nSaved in chat history.")


def choose_workspace():
    print(f"[WORKSPACE]\nEnter a working folder, or press Enter for {config.DEFAULT_WORKSPACE_DIRECTORY}")
    while True:
        selected_directory = input("\nFolder: ").strip()
        if selected_directory:
            workspace_directory = Path(selected_directory).expanduser().resolve()
        else:
            workspace_directory = config.DEFAULT_WORKSPACE_DIRECTORY.resolve()
            workspace_directory.mkdir(parents=True, exist_ok=True)
        if workspace_directory.is_dir():
            return workspace_directory
        print("\n[ERROR]\nThat folder does not exist. Please choose an existing folder.")
