from openai import OpenAI

import config
from conversation import Conversation
from model import call_model
from tools import call_tool


def run_loop(client, conversation):
    while True:
        response = call_model(client, conversation.model_input)

        # Keep every output item so the next call has the complete context.
        for item in response.output:
            conversation.append_response_item(item)

        if response.status != "completed":
            raise RuntimeError(f"Model response did not complete: {response.status}")

        called_tool = False
        for item in response.output:
            if item.type == "reasoning":
                for summary in item.summary:
                    print(f"\n[REASONING]\n\n{summary.text}")

            elif item.type == "message":
                for part in item.content:
                    if part.type == "output_text":
                        print(f"\n[ASSISTANT]\n\n{part.text}")
                    elif part.type == "refusal":
                        print(f"\n[REFUSAL]\n\n{part.refusal}")
                    else:
                        print(f"\n[{part.type.upper()}]\n\nSaved in chat history.")

            elif item.type == "function_call":
                called_tool = True
                print(f"\n[TOOL]\n\n{item.name}({item.arguments})")
                result = call_tool(item.name, item.arguments)
                print(f"\n[TOOL RESULT]\n\n{result}")
                conversation.append_tool_result(item.call_id, result)

            else:
                print(f"\n[{item.type.upper()}]\n\nSaved in chat history.")

        if not called_tool:
            return


def start_agent():
    system_message = config.SYSTEM_MESSAGE_FILE.read_text(encoding="utf-8")

    with OpenAI() as client:
        conversation = Conversation()
        conversation.append_text_message(system_message, message_type="system")
        print(f"[HISTORY]\n\n{conversation.history_path}\n\n[INFO]\n\nType quit to exit.")

        while True:
            try:
                user_message = input("\n[USER]\n\n").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break

            if user_message in {"quit", "exit"}:
                break
            if not user_message:
                continue

            conversation.append_text_message(user_message, message_type="user")
            run_loop(client, conversation)


if __name__ == "__main__":
    start_agent()
