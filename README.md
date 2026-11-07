# Harness v1

A small terminal conversation loop with tool calls and JSONL history.

## Run

Copy `.env.example` to `.env` and fill in `OPENAI_API_KEY` and `OPENAI_MODEL`.
Choose a model that supports Responses API function calling and reasoning summaries.

```sh
uv run --env-file .env main.py
```

Type `quit` or `exit` to finish.

## Code flow

- `main.py`: `start_agent()` reads user input; `run_loop()` calls the model until it
  stops requesting tools.
- `conversation.py`: `Conversation` owns the message list, turn number, and history
  file path. Its methods build message dictionaries and record them in context and JSONL.
- `config.py`: history directory, system prompt path, and OpenAI model name. The paths
  are relative to the project directory. The model name is read from `OPENAI_MODEL` in
  the environment; it can also be set directly in this file.
- `model.py`: `call_model()` makes the API request.
- `tools.py`: one example tool, its schema, and a dictionary for finding the function.
- `prompts/system_message.md`: system instructions, read once by `start_agent()`.

The message list is created once, before the input loop, so follow-up questions retain
earlier context. Reasoning summaries and assistant messages are printed when returned.
Tool calls are executed, and their results are included in the next model request.
Terminal labels use uppercase square brackets: `[USER]`, `[REASONING]`, `[ASSISTANT]`,
`[REFUSAL]`, `[TOOL]`, and `[TOOL RESULT]`. Other returned item types are saved and
displayed with their type as the label.
Each label is followed by a blank line before its content.

The loop passes a single `conversation` object between turns:

```python
conversation = Conversation()
conversation.append_text_message("Hello", message_type="user")
response = call_model(client, conversation.model_input)
```

`append_text_message(text, message_type)` builds a message from plain text and its role.
`append_response_item(item)` preserves an already-structured SDK output item, such as
reasoning, an assistant message, or a function call. `append_tool_result(call_id, output)`
builds a function result.

All three pass their API-ready item to `_record_item()`. That method writes a JSONL
record containing metadata and the item, then appends only the original item to
`conversation.model_input`. The metadata wrapper is never sent to the model.
The turn counter and file writing also live in this method. The leading underscore
marks it as an internal helper.

Every run creates `chat_history/YYYY-MM-DD_HH-MM-SS_microseconds.jsonl`.
Each line contains metadata and the original conversation item:

```json
{"metadata":{"timestamp":"2026-11-07T12:00:00+00:00","turn_number":1,"message_type":"user"},"message":{"role":"user","content":"What time is it?"}}
```

`turn_number` starts at 1 for the first user input; the initial system message uses 0.
All model outputs and tool results for a user turn share its number, even when that
turn needs multiple model calls. `message_type` identifies the item, for example
`system`, `user`, `assistant`, `reasoning`, `function_call`, or `tool_result`.
The last turn number tells you how many user turns have been started in the session.

`conversation.model_input` contains only the original API items, without the file metadata.
Items are saved immediately, and `call_id` links each tool result to its call.
The history folder is gitignored. Existing logs keep their original format and metadata.
