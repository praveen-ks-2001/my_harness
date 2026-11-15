from openai import OpenAI, OpenAIError

import config
from agent.conversation import Conversation
from agent.model import stream_model
from compaction.compact import compact_conversation, needs_compaction
from observability.tracing import start_tracing, trace_compaction, trace_session, trace_tool, trace_turn
from sandbox.sandbox import Sandbox
from utils.terminal import choose_workspace, print_stream


def compact(client, conversation, trigger):
    """Compact the conversation and report the result; return False if it failed."""
    tokens_before = conversation.estimated_input_tokens()
    print(f"\n[COMPACTION]\nSummarizing about {tokens_before:,} tokens ({trigger})...")
    with trace_compaction(trigger, tokens_before) as compaction_span:
        try:
            compact_conversation(client, conversation, trigger)
        except (OpenAIError, RuntimeError) as error:
            print(f"\n[ERROR]\nCompaction failed: {error}\nType continue to retry, or /compact.")
            compaction_span.set_output(value=f"Failed: {error}")
            return False
        result = f"Done: about {conversation.estimated_input_tokens():,} tokens now."
        compaction_span.set_output(value=result)
    print(result)
    return True


def run_loop(client, conversation, sandbox):
    """Call the model and run its tools until it answers; return the final answer text."""
    for _ in range(config.MAX_MODEL_CALLS_PER_TURN):
        if needs_compaction(conversation):
            compacted = compact(client, conversation, "auto")
            if not compacted:
                return

        with stream_model(client, conversation.model_input) as stream:
            print_stream(stream)
            # Raises RuntimeError unless the response completed.
            response = stream.get_final_response()

        # Keep every output item so the next call has the complete context.
        conversation.append_model_response(response)

        function_calls = [item for item in response.output if item.type == "function_call"]
        if not function_calls:
            return response.output_text

        for item in function_calls:
            print(f"\n[TOOL]\n{item.name}({item.arguments})")
            with trace_tool(item.name, item.arguments) as tool_span:
                result = sandbox.call_tool(item.name, item.arguments)
                tool_span.set_output(value=result)
            print(f"\n[TOOL RESULT]\n{result}")
            conversation.append_tool_result(item.call_id, result)

    print(f"\n[INFO]\nStopped after {config.MAX_MODEL_CALLS_PER_TURN} model calls in this turn.")
    return None


def start_agent():
    start_tracing()
    system_message = config.SYSTEM_MESSAGE_FILE.read_text(encoding="utf-8")

    with OpenAI() as client:
        workspace_directory = choose_workspace()
        print("\n[SANDBOX]\nPreparing the Docker image and workspace container...")
        with Sandbox(workspace_directory) as sandbox:
            conversation = Conversation(workspace_directory, sandbox.container_id)
            container_history_file = f"{config.CONTAINER_HISTORY_DIRECTORY}/{conversation.history_path.name}"
            system_message = system_message.format(
                history_file=container_history_file,
                history_directory=config.CONTAINER_HISTORY_DIRECTORY,
            )
            conversation.append_text_message(system_message, message_type="system")
            print(f"\n[HISTORY]\n{conversation.history_path}\n\n[INFO]\nType quit to exit, or /compact to summarize the conversation so far.")

            # One Phoenix session per run, named after its history file.
            with trace_session(conversation.history_path.stem):
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
                    if user_message == "/compact":
                        compact(client, conversation, "manual")
                        continue

                    conversation.append_text_message(user_message, message_type="user")
                    with trace_turn(conversation.turn_number, user_message) as turn_span:
                        final_answer = run_loop(client, conversation, sandbox)
                        # No answer when the call limit is hit or compaction fails.
                        if final_answer:
                            turn_span.set_output(value=final_answer)


if __name__ == "__main__":
    try:
        start_agent()
    except (KeyboardInterrupt, EOFError):
        print("\n[INFO]\nSession stopped.")
    except (RuntimeError, ValueError, OSError) as error:
        print(f"\n[ERROR]\n{error}")
        raise SystemExit(1)
