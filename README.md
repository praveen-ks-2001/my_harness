# Harness v1

A small terminal conversation loop with Docker tool execution and JSONL history.

## Run

Copy `.env.example` to `.env` and fill in `OPENAI_API_KEY` and `OPENAI_MODEL`.
Choose a model that supports Responses API function calling and reasoning summaries.
Docker must be installed and its engine running.

```sh
uv run main.py
```

`config.py` loads the project's `.env` file automatically using `python-dotenv`.
Variables already set in the environment take priority over values in `.env`.

At startup, enter an existing folder the tools may read and modify. Press Enter to
create or reuse the default `workspace/` folder in this project. Type `quit` or `exit`
to finish the conversation.

The harness builds a small Docker image and starts one container for the session.
Subsequent starts reuse Docker's build cache. The selected host folder is mounted
read/write at `/workspace` inside that container. Paths containing spaces work.
Selecting a folder that contains the harness or its history is refused, so those
files and credentials stay outside the tool workspace.

The Python conversation loop and model API client run on the host. All tool calls,
including `current_time`, execute inside Docker. There is no local execution fallback
if Docker is unavailable. The container is removed on normal exit or when an exception
unwinds the session; workspace files remain on disk.

The container runs as the host user's UID/GID, with outbound networking, a read-only root
filesystem, and temporary writable `/tmp` storage. Only the selected host folder is
shared. The image contains Python, timezone data, and the tool implementation; API
credentials, chat history, and the rest of the harness are not copied into it.
No Bash or file-editing tool is exposed to the model yet.

`SANDBOX_NETWORK = "bridge"` in `config.py` allows tools to download packages and access
network services. No container ports are published. Install Python dependencies in a
workspace virtual environment or use `pip install --target /workspace/.packages ...`,
since the container's system directories remain read-only. Packages stored in the
workspace persist across sessions. A tool-call approval model is not implemented yet.

## Code flow

- `main.py`: `start_agent()` reads user input; `run_loop()` calls the model until it
  stops requesting tools. `choose_workspace()` asks for the working folder.
- `conversation.py`: `Conversation` owns the message list, turn number, and history
  file path. Its methods build message dictionaries and record them in context and JSONL.
- `sandbox.py`: `Sandbox` builds/starts the container, executes argument lists in it,
  and removes it when the session ends.
- `Dockerfile` and `.dockerignore`: define the tool environment and limit the build
  context to the tool implementation and Dockerfile.
- `config.py`: history directory, system prompt path, OpenAI model name, workspace
  paths, sandbox image/network settings, and tool timeout, grouped by purpose. Project paths
  are relative to the project directory. The model name is read from `OPENAI_MODEL` in
  the environment; it can also be set directly in this file.
- `model.py`: `call_model()` makes the API request.
- `tools.py`: one example tool, its schema, host-side Docker dispatch, and the
  container's tool-runner entry point.
- `prompts/system_message.md`: system instructions, read once by `start_agent()`.

The message list is created once, before the input loop, so follow-up questions retain
earlier context. Reasoning summaries and assistant messages are printed when returned.
Tool calls are executed, and their results are included in the next model request.
Terminal labels use uppercase square brackets: `[USER]`, `[REASONING]`, `[ASSISTANT]`,
`[REFUSAL]`, `[TOOL]`, and `[TOOL RESULT]`. Other returned item types are saved and
displayed with their type as the label.
Each label is followed by its content on a new line.

The loop passes a single `conversation` object between turns:

```python
conversation = Conversation(workspace_directory, sandbox.container_id)
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
The first line is a turn-zero session record, before any conversation items:

```json
{
  "metadata": {
    "timestamp": "2026-11-08T12:00:00+00:00",
    "turn_number": 0,
    "message_type": "session"
  },
  "session": {
    "workspace_directory": "/absolute/path/to/project",
    "container_workspace_directory": "/workspace",
    "container_id": "the-session-container-id",
    "sandbox_image": "harness-sandbox:local",
    "sandbox_network": "bridge",
    "model": "your-model-id"
  }
}
```

This session record is saved only to the file, never added to model input. Subsequent
lines contain metadata and the original conversation item:

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
