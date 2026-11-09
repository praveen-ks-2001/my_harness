# Harness v1

A small terminal agent with Docker tool execution and JSONL history. It is a base for
personal applications and custom tools, where every part of the agent's behavior is
visible and under your control.

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
shared. The image contains Python, Bash, Git, ripgrep, timezone data, Pydantic, `docstring-parser`,
and the `tools/` package; API
credentials, chat history, and the rest of the harness are not copied into it.

## Tools

| Tool | Behavior |
| --- | --- |
| `read_file(path, start_line=1, end_line=None)` | Read UTF-8 text with one-based line numbers; optional bounds are inclusive. |
| `write_file(path, content, overwrite=False)` | Write a UTF-8 file and missing parent folders; replace an existing file only when `overwrite` is true. |
| `edit_file(path, old_text, new_text)` | Replace an exact, nonempty text match that occurs only once. |
| `run_command(command)` | Run Bash from the workspace and return stdout, stderr, exit code, and timeout status. |
| `current_time(timezone="UTC")` | Return the current time in an IANA timezone. |

### Adding a tool

The steps and an example are at the top of [tools/\_\_init\_\_.py](tools/__init__.py).
At startup, `model.py` calls `tool_schemas()` in `tools/registry.py`: Pydantic turns the
type hints and defaults into JSON Schema, and `docstring-parser` adds the description and
each `Args:` entry. A tool without a description, or with an undocumented argument,
stops startup with an error. Before a tool runs, Pydantic checks the model's arguments
against its type hints and returns any mismatch to the model as an error.

Tools run inside Docker, so a tool's third-party imports must also be installed in the
`Dockerfile`, pinned to the same versions as `uv.lock`.

### How a call reaches the container

`Sandbox.call_tool()` runs `docker exec --interactive ... python -P -m tools.runner <name>`
and sends the model's JSON arguments on stdin. Only the tool name is a command-line
argument, so large `write_file` content is not limited by Linux's 128 KB cap on a
single argument. `-P` stops files in `/workspace` from shadowing the tool package's
imports. The image sets `PYTHONPATH=/opt/harness` so the package is importable, which
also makes it importable from workspace scripts.

File paths are relative to the workspace, or absolute paths inside it. The file tools
resolve paths and refuse traversal or symlinks that lead outside the workspace.
`edit_file` preserves existing line endings and refuses missing or ambiguous matches.

`run_command` supports shell syntax, scripts, searches (`rg`), Git, and package installation.
Every call starts in the workspace; a `cd` does not persist into the next call.
Nonzero exits are returned to the model as command results rather than hidden:

```json
{"stdout":"","stderr":"command error","exit_code":1,"timed_out":false}
```

Commands use `TOOL_TIMEOUT_SECONDS` from `config.py`. On timeout, the command's process
group is killed and any captured output is returned with `exit_code: 124` and
`timed_out: true`. The Docker execution timeout gives the runner five extra seconds
to return that result.

`SANDBOX_NETWORK = "bridge"` in `config.py` allows tools to download packages and access
network services. No container ports are published. Install Python dependencies in a
workspace virtual environment or use `pip install --target /workspace/.packages ...`,
since the container's system directories remain read-only. Packages stored in the
workspace persist across sessions. A tool-call approval model is not implemented yet.

## Code flow

- `main.py`: `start_agent()` reads user input; `run_loop()` calls the model until it
  stops requesting tools, or until `MAX_MODEL_CALLS_PER_TURN` calls have been made in
  that turn. It then prints an `[INFO]` notice and waits for the next user input.
  `choose_workspace()` asks for the working folder.
- `conversation.py`: `Conversation` owns the message list, turn number, and history
  file path. Its methods build message dictionaries and record them in context and JSONL.
- `sandbox.py`: `Sandbox` builds/starts the container, executes argument lists in it,
  sends tool calls to the container's runner with `call_tool()`, and removes the
  container when the session ends.
- `Dockerfile` and `.dockerignore`: define the tool environment and limit the build
  context to the tool implementation and Dockerfile.
- `config.py`: history directory, system prompt path, OpenAI model name, model-call
  limit per turn, workspace
  paths, sandbox image/network settings, and tool timeout, grouped by purpose. Project paths
  are relative to the project directory. The model name is read from `OPENAI_MODEL` in
  the environment; it can also be set directly in this file.
- `model.py`: `stream_model()` starts a streamed API request.
- `tools/`: `registry.py` (the `@tool` decorator, `TOOLS`, schema building, and argument
  validation), the tool modules `files.py`, `shell.py`, and `clock.py`, and `runner.py`,
  the entry point Docker runs for each tool call.
- `prompts/system_message.md`: system instructions, read once by `start_agent()`.

The message list is created once, before the input loop, so follow-up questions retain
earlier context. Responses are streamed: `print_stream()` in `main.py` prints reasoning
summaries and assistant text as they arrive. Once the response completes,
`stream.get_final_response()` returns the full response, which is saved, and its tool
calls are executed one by one. Their results are included in the next model request.
If a response ends without completing, `get_final_response()` raises and the session stops.
Terminal labels use uppercase square brackets: `[USER]`, `[REASONING]`, `[ASSISTANT]`,
`[REFUSAL]`, `[TOOL]`, and `[TOOL RESULT]`. Other returned item types are saved and
displayed with their type as the label.
Each label is followed by its content on a new line.

The loop passes a single `conversation` object between turns:

```python
conversation = Conversation(workspace_directory, sandbox.container_id)
conversation.append_text_message("Hello", message_type="user")
with stream_model(client, conversation.model_input) as stream:
    print_stream(stream)
    response = stream.get_final_response()
conversation.append_model_response(response)
```

`append_text_message(text, message_type)` builds a message from plain text and its role.
`append_model_response(response)` preserves each already-structured SDK output item of
one model call, such as reasoning, an assistant message, or a function call.
`append_tool_result(call_id, output)`
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

Items returned by a model call also carry that call's `response_id` in their metadata,
and the call's last item carries its token `usage`:

```json
{"metadata":{"timestamp":"…","turn_number":1,"message_type":"assistant","response_id":"resp_…","usage":{"input_tokens":1200,"input_tokens_details":{"cache_write_tokens":0,"cached_tokens":0},"output_tokens":85,"output_tokens_details":{"reasoning_tokens":64},"total_tokens":1285}},"message":{"id":"msg_…","type":"message","role":"assistant","content":[…]}}
```

Summing `usage` across the file gives the session's token use.

`conversation.model_input` contains only the original API items, without the file metadata.
Items are saved immediately, and `call_id` links each tool result to its call.
The history folder is gitignored. Existing logs keep their original format and metadata.
