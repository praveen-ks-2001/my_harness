from pathlib import Path

from openai import OpenAI

import config
from conversation import Conversation
from model import call_model
from sandbox import Sandbox


def run_loop(client, conversation, sandbox):
    for _ in range(config.MAX_MODEL_CALLS_PER_TURN):
        response = call_model(client, conversation.model_input)

        # Keep every output item so the next call has the complete context.
        conversation.append_model_response(response)

        if response.status != "completed":
            raise RuntimeError(f"Model response did not complete: {response.status}")

        called_tool = False
        for item in response.output:
            if item.type == "reasoning":
                for summary in item.summary:
                    print(f"\n[REASONING]\n{summary.text}")

            elif item.type == "message":
                for part in item.content:
                    if part.type == "output_text":
                        print(f"\n[ASSISTANT]\n{part.text}")
                    elif part.type == "refusal":
                        print(f"\n[REFUSAL]\n{part.refusal}")
                    else:
                        print(f"\n[{part.type.upper()}]\nSaved in chat history.")

            elif item.type == "function_call":
                called_tool = True
                print(f"\n[TOOL]\n{item.name}({item.arguments})")
                result = sandbox.call_tool(item.name, item.arguments)
                print(f"\n[TOOL RESULT]\n{result}")
                conversation.append_tool_result(item.call_id, result)

            else:
                print(f"\n[{item.type.upper()}]\nSaved in chat history.")

        if not called_tool:
            return

    print(f"\n[INFO]\nStopped after {config.MAX_MODEL_CALLS_PER_TURN} model calls in this turn.")


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


def start_agent():
    system_message = config.SYSTEM_MESSAGE_FILE.read_text(encoding="utf-8")

    with OpenAI() as client:
        workspace_directory = choose_workspace()
        print("\n[SANDBOX]\nPreparing the Docker image and workspace container...")
        with Sandbox(workspace_directory) as sandbox:
            conversation = Conversation(workspace_directory, sandbox.container_id)
            conversation.append_text_message(system_message, message_type="system")
            print(f"\n[HISTORY]\n{conversation.history_path}\n\n[INFO]\nType quit to exit.")

            while True:
                try:
                    user_message = input("\n[USER]\n").strip()
                except (EOFError, KeyboardInterrupt):
                    print()
                    break

                if user_message in {"quit", "exit"}:
                    break
                if not user_message:
                    continue

                conversation.append_text_message(user_message, message_type="user")
                run_loop(client, conversation, sandbox)


if __name__ == "__main__":
    try:
        start_agent()
    except (KeyboardInterrupt, EOFError):
        print("\n[INFO]\nSession stopped.")
    except (RuntimeError, ValueError, OSError) as error:
        print(f"\n[ERROR]\n{error}")
        raise SystemExit(1)
