import json

import config


def needs_compaction(conversation):
    threshold = config.CONTEXT_WINDOW_TOKENS * config.COMPACT_AT_FRACTION
    return conversation.estimated_input_tokens() > threshold


def compact_conversation(client, conversation, task_list, trigger):
    """Replace the model input with a summary, the last two units verbatim, and the task list.

    A unit is one user message and everything the model did in reply, up to the next
    user message. The summarizer sees every unit, including the last two. The task list
    is rendered by code from the harness's copy, so it is exact however the summary reads.
    """
    system_message = conversation.model_input[0]["content"]
    conversation_items = conversation.model_input[1:]
    units = split_into_units(conversation_items)
    if len(units) <= 2:
        raise RuntimeError(
            f"Nothing to compact: there are {len(units)} unit(s), and the last two are kept verbatim."
        )

    # Summarize everything with a plain, tool-free call: the summarizer only reads and writes text.
    task_list_text = task_list.render()
    system_prompt = config.COMPACTION_SYSTEM_PROMPT_FILE.read_text(encoding="utf-8")
    input_text = config.COMPACTION_INPUT_TEMPLATE_FILE.read_text(encoding="utf-8").format(
        system_message=system_message,
        conversation=render_items(conversation_items),
        task_list=task_list_text,
    )
    response = client.responses.create(
        model=config.OPENAI_MODEL,
        input=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": input_text},
        ],
        store=False,
    )
    summary = response.output_text.strip()
    if not summary:
        raise RuntimeError("The summary came back empty.")

    # Restart the model input from the summary, the last two units, and the task list.
    continuation_text = config.COMPACTION_CONTINUATION_TEMPLATE_FILE.read_text(encoding="utf-8").format(
        summary=summary,
        unit_1=render_items(units[-2]),
        unit_2=render_items(units[-1]),
        task_list=task_list_text,
    )
    conversation.replace_with_compaction(response, continuation_text, trigger)


def split_into_units(items):
    """Group items into units, each starting at a user-role item."""
    units = []
    for item in items:
        if item.get("role") == "user" or not units:
            units.append([])
        units[-1].append(item)
    return units


def render_items(items):
    """Render API items as XML text; reasoning items are encrypted, so they are left out."""
    return "\n".join(render_item(item) for item in items if item.get("type") != "reasoning")


def render_item(item):
    if "role" in item:
        return f"<{item['role']}>\n{message_text(item['content'])}\n</{item['role']}>"
    if item["type"] == "function_call":
        return (
            f'<function_call name="{item["name"]}" call_id="{item["call_id"]}">\n'
            f"{item['arguments']}\n</function_call>"
        )
    if item["type"] == "function_call_output":
        return f'<tool_result call_id="{item["call_id"]}">\n{item["output"]}\n</tool_result>'
    return f"<{item['type']}>\n{json.dumps(item, ensure_ascii=False)}\n</{item['type']}>"


def message_text(content):
    """Return a message's text, whether its content is a string or a list of parts."""
    if isinstance(content, str):
        return content
    return "\n".join(part.get("text") or part.get("refusal") or "" for part in content)
