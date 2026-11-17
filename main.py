from openai import OpenAI, OpenAIError

import config
from agent.conversation import Conversation, saved_workspace
from agent.model import stream_model
from compaction.compact import compact_conversation, needs_compaction
from observability.tracing import (
    mark_failed,
    mark_ok,
    record_decision,
    record_tool_result,
    start_tracing,
    trace_compaction,
    trace_session,
    trace_tool,
    trace_tool_decision,
    trace_turn,
)
from sandbox.sandbox import Sandbox
from tasks.task_list import TaskList
from tool_classifier.classifier import Decision, ToolClassifier
from tool_classifier.utils import rejection_message
from utils.terminal import (
    change_classifier_mode,
    choose_session,
    choose_workspace,
    print_classifier_mode,
    print_notice,
    print_replay,
    print_stream,
    print_tool_call,
    print_tool_result,
    read_user_message,
)


def compact(client, conversation, trigger):
    """Compact the conversation and report the result; return False if it failed."""
    tokens_before = conversation.estimated_input_tokens()
    print_notice("COMPACTION", f"Summarizing about {tokens_before:,} tokens ({trigger})...")
    with trace_compaction(trigger, tokens_before) as compaction_span:
        try:
            compact_conversation(client, conversation, trigger)
        except (OpenAIError, RuntimeError) as error:
            print_notice("ERROR", f"Compaction failed: {error}\nType continue to retry, or /compact.")
            compaction_span.set_output(value=f"Failed: {error}")
            mark_failed(compaction_span, message=str(error))
            return False
        result = f"Done: about {conversation.estimated_input_tokens():,} tokens now."
        compaction_span.set_output(value=result)
        mark_ok(compaction_span)
    print(result)
    return True


def run_loop(client, conversation, sandbox, tool_classifier, task_list):
    """Call the model and run its tools until it answers; return the final answer text."""
    for _ in range(config.MAX_MODEL_CALLS_PER_TURN):
        # Compact first if the next call's input would be too large.
        if needs_compaction(conversation):
            compacted = compact(client, conversation, "auto")
            if not compacted:
                return

        # Call the model, streaming its reasoning and answer to the terminal.
        with stream_model(client, conversation.model_input, host_tool_schemas=task_list.tool_schemas) as stream:
            print_stream(stream)
            # Raises RuntimeError unless the response completed.
            response = stream.get_final_response()

        # Keep every output item so the next call has the complete context.
        conversation.append_model_response(response)

        # No tool calls means the model has answered.
        function_calls = [item for item in response.output if item.type == "function_call"]
        if not function_calls:
            return response.output_text

        for item in function_calls:
            print_tool_call(item.name, item.arguments)

            # Decide whether the call runs; task tools only store data in the harness, so they skip the classifier.
            is_task_tool = item.name in task_list.TOOL_NAMES
            if is_task_tool:
                decision = Decision(allowed=True, decided_by="harness")
            else:
                with trace_tool_decision(item.name, item.arguments, tool_classifier.mode) as decision_span:
                    decision = tool_classifier.decide(item, response, conversation)
                    record_decision(decision_span, decision)

            # Run it in the harness or in Docker, and give the model its result.
            if decision.allowed:
                with trace_tool(item.name, item.arguments) as tool_span:
                    if is_task_tool:
                        result = task_list.call_tool(item.name, item.arguments)
                    else:
                        result = sandbox.call_tool(item.name, item.arguments)
                    record_tool_result(tool_span, result=result)
                print_tool_result(result)
            else:
                # The model gets the rejection, and its reason, as this call's result.
                result = rejection_message(decision)
                print_notice("REJECTED", result)
            conversation.append_tool_result(item.call_id, result, decision=decision)

    print_notice("INFO", f"Stopped after {config.MAX_MODEL_CALLS_PER_TURN} model calls in this turn.")
    return None


def start_agent():
    start_tracing()

    with OpenAI() as client:
        # Choose a new session or a saved one; a saved session reuses its workspace.
        resume_directory = choose_session()
        workspace_directory = choose_workspace() if resume_directory is None else saved_workspace(resume_directory)
        tool_classifier = ToolClassifier(client, mode=config.TOOL_CLASSIFIER_MODE)

        print_notice("SANDBOX", "Preparing the Docker image and workspace container...")
        with Sandbox(workspace_directory) as sandbox:
            # Start or rebuild the conversation, then load the session's task list.
            if resume_directory is None:
                conversation = Conversation.start(workspace_directory, sandbox.container_id)
            else:
                conversation = Conversation.resume(resume_directory, sandbox.container_id)
                print_replay(conversation.history_path, turn_count=config.RESUME_REPLAY_TURNS)
            task_list = TaskList(conversation.session_directory / config.TASKS_FILE_NAME, owner="main_agent")

            # Show where history is saved and how to use the session.
            print_notice("HISTORY", str(conversation.history_path))
            print_classifier_mode(tool_classifier)
            print_notice("INFO", "Type quit to exit, or /compact to summarize the conversation so far. Tab completes commands; Up/Down recall earlier messages.")

            # One Phoenix session per run, named after its session folder.
            with trace_session(conversation.session_directory.name):
                while True:
                    try:
                        user_message = read_user_message()
                    except (EOFError, KeyboardInterrupt):
                        print()
                        break

                    # Commands are handled here and never reach the model.
                    if user_message in {"quit", "exit"}:
                        break
                    if not user_message:
                        continue
                    if user_message == "/compact":
                        compact(client, conversation, "manual")
                        continue
                    if user_message.startswith("/tool-classifier"):
                        change_classifier_mode(tool_classifier, user_message)
                        continue

                    # Anything else starts a user turn: run the model until it answers.
                    conversation.append_text_message(user_message, message_type="user")
                    with trace_turn(conversation.turn_number, user_message) as turn_span:
                        final_answer = run_loop(client, conversation, sandbox, tool_classifier, task_list)
                        # No answer when the call limit is hit or compaction fails.
                        if final_answer:
                            turn_span.set_output(value=final_answer)


if __name__ == "__main__":
    try:
        start_agent()
    except (KeyboardInterrupt, EOFError):
        print_notice("INFO", "Session stopped.")
    except (RuntimeError, ValueError, OSError) as error:
        print_notice("ERROR", str(error))
        raise SystemExit(1)
