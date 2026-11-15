from openai import OpenAI

import config
from conversation import Conversation
from model import stream_model
from sandbox import Sandbox
from utils.terminal import choose_workspace, print_stream


def run_loop(client, conversation, sandbox):
    for _ in range(config.MAX_MODEL_CALLS_PER_TURN):
        with stream_model(client, conversation.model_input) as stream:
            print_stream(stream)
            # Raises RuntimeError unless the response completed.
            response = stream.get_final_response()

        # Keep every output item so the next call has the complete context.
        conversation.append_model_response(response)

        function_calls = [item for item in response.output if item.type == "function_call"]
        if not function_calls:
            return

        for item in function_calls:
            print(f"\n[TOOL]\n{item.name}({item.arguments})")
            result = sandbox.call_tool(item.name, item.arguments)
            print(f"\n[TOOL RESULT]\n{result}")
            conversation.append_tool_result(item.call_id, result)

    print(f"\n[INFO]\nStopped after {config.MAX_MODEL_CALLS_PER_TURN} model calls in this turn.")


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
