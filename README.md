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

At startup, choose **New session** or one of the recent saved sessions (arrow keys, then
Enter); see Resuming a session below. For a new session, enter an existing folder the
tools may read and modify. Press Enter to
create or reuse the default `workspace/` folder in this project. Type `quit` or `exit`
to finish the conversation, or `/compact` to summarize the conversation so far.

The harness builds a small Docker image and starts one container for the session.
Subsequent starts reuse Docker's build cache. The selected host folder is mounted
read/write at `/workspace` inside that container. Paths containing spaces work.
Selecting a folder that contains the harness or its sessions is refused, so those
files and credentials stay outside the tool workspace.

The Python conversation loop and model API client run on the host. All tool calls,
including `current_time`, execute inside Docker, except the task tools, which only
store the model's arguments in the harness (see Tasks below). There is no local
execution fallback if Docker is unavailable. The container is removed on normal exit or when an exception
unwinds the session; workspace files remain on disk.

The container runs as the host user's UID/GID, with outbound networking, a read-only root
filesystem, and temporary writable `/tmp` storage. Besides the workspace, only the
`sessions/` folder is shared, read-only at `/sessions`: the model can search this
session and past ones, but cannot change them. The system message tells it the
current session's folder and history file and to search with `rg` and `jq` instead of
reading whole files. The image contains Python, Bash, Git, ripgrep, jq, timezone data, Pydantic, `docstring-parser`,
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
| `create_tasks(tasks)`, `update_task(task_id, status, result=None)`, `read_tasks(task_id=None)` | Host tools for the session's task list; see Tasks below. |

### Adding a tool

The steps and an example are at the top of [tools/\_\_init\_\_.py](tools/__init__.py).
At startup, `agent/model.py` calls `tool_schemas()` in `tools/registry.py`: Pydantic turns the
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
workspace persist across sessions. Every tool call is checked first; see Tool-call classifier below.

## Code flow

Code is grouped by feature; each folder keeps its own prompts.

```
main.py, config.py        entry point and settings
agent/                    the main model: model.py, conversation.py, prompts/
compaction/               compact.py, prompts/
tool_classifier/          classifier.py, utils.py, prompts/
tasks/                    task_list.py (the task list and its host tools)
observability/            tracing.py (Phoenix traces of model calls)
sandbox/                  sandbox.py (Docker side of the host)
tools/                    tool package that runs inside Docker
utils/terminal.py         terminal input (prompt_toolkit) and output (Rich)
```

- `main.py`: `start_agent()` sets up the session (session choice, sandbox,
  conversation, task list); `user_input_loop()` reads user input and handles commands;
  `run_loop()` calls the model until it stops requesting tools, or until
  `MAX_MODEL_CALLS_PER_TURN` calls have been made in that turn. It then prints an
  `[INFO]` notice and waits for the next user input.
- `config.py`: sessions folder, prompt paths, OpenAI model name, model-call
  limit per turn, compaction threshold, workspace paths, sandbox image/network
  settings, and tool timeout, grouped by purpose. Project paths are relative to the
  project directory. The model name is read from `OPENAI_MODEL` in the environment;
  it can also be set directly in this file.
- `agent/model.py`: `stream_model()` starts a streamed API request.
- `agent/conversation.py`: `Conversation` owns the message list, turn number, session
  folder, and history file path. Its methods build message dictionaries and record them in context and JSONL.
- `agent/prompts/system_message.md`: system instructions, read by `Conversation.start()`,
  which fills in `{sessions_directory}`, `{session_directory}`, and `{history_file}`
  with the container paths.
  A resumed session reuses the system message saved in its file.
- `compaction/compact.py`: `needs_compaction()` and `compact_conversation()`, which also
  makes the tool-free summary call; `compaction/prompts/` holds its system prompt and
  two templates. See Compaction below.
- `tool_classifier/`: `ToolClassifier` decides whether each tool call runs; see Tool-call
  classifier below.
- `observability/tracing.py`: `start_tracing()`, called first in `start_agent()`; see Tracing below.
- `sandbox/sandbox.py`: `Sandbox` builds/starts the container, executes argument lists in
  it, sends tool calls to the container's runner with `call_tool()`, and removes the
  container when the session ends.
- `Dockerfile` and `.dockerignore`: define the tool environment and limit the build
  context to the tool implementation and Dockerfile. They stay at the project root
  because the image needs `tools/`.
- `tools/`: `registry.py` (the `@tool` decorator, `TOOLS`, schema building, and argument
  validation), the tool modules `files.py`, `shell.py`, and `clock.py`, and `runner.py`,
  the entry point Docker runs for each tool call.
- `utils/terminal.py`: all terminal input and output. Input uses prompt_toolkit: Up/Down
  recall earlier messages, Tab completes `/compact` and folder paths, a multi-line
  paste stays one message, and Esc+Enter or Ctrl+J adds a new line (most terminals send
  Shift+Enter as plain Enter, which sends the message). Output uses Rich: colored labels, assistant answers rendered
  as Markdown while they stream, and tool arguments and results shown as highlighted JSON.

The message list is created once, before the input loop, so follow-up questions retain
earlier context. Responses are streamed: `print_stream()` in `utils/terminal.py` prints reasoning
summaries and assistant text as they arrive. Once the response completes,
`stream.get_final_response()` returns the full response, which is saved, and its tool
calls are executed one by one. Their results are included in the next model request.
If a response ends without completing, `get_final_response()` raises and the session stops.
Terminal labels use uppercase square brackets: `[USER]`, `[REASONING]`, `[ASSISTANT]`,
`[REFUSAL]`, `[TOOL]`, `[TOOL RESULT]`, and `[COMPACTION]`. Other returned item types are saved and
displayed with their type as the label.
Each label is followed by its content on a new line.

The loop passes a single `conversation` object between turns:

```python
conversation = Conversation.start(workspace_directory, sandbox.container_id)
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

Every run creates its own folder, `sessions/main_agent_YYYYMMDD_HHMMSS_microseconds/`,
with the conversation history in `history.jsonl` inside it. The first line is a
turn-zero session record, before any conversation items:

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
The sessions folder is gitignored. Existing logs keep their original format and metadata.

## Compaction

Before every model call, `run_loop()` estimates the next input: the last call's exact
`input_tokens + output_tokens`, plus about one token per four characters of items added
since. When that passes `CONTEXT_WINDOW_TOKENS * COMPACT_AT_FRACTION` (70% of 100K by
default, in `config.py`), or when you type `/compact`, the conversation is compacted:

1. The conversation is split into units. A unit is one user message and everything the
   model did in reply (reasoning, tool calls, tool results, answers) until the next one.
2. The summarizer gets `compaction/prompts/system_prompt.md` as its system message and,
   as its user message, `compaction/prompts/input_template.md` filled with the original system message,
   every unit as XML (`<user>`, `<assistant>`, `<function_call>`, `<tool_result>`), and
   the task list. Encrypted reasoning is left out.
3. `model_input` becomes the original system message plus one user message,
   `compaction/prompts/continuation_template.md` filled with the summary, the last two units
   verbatim, and a `<task_list>` block. The loop then carries on, even in the middle of a turn.

The task list block is `TaskList.render()`: the harness's own copy as JSON, written by
code rather than by the summarizer, so it is exact after any number of compactions.
The summarizer is told not to copy it, only to stay consistent with it.

A later compaction summarizes that continuation message along with everything after it.
With two or fewer units there is nothing to shrink, so compaction refuses. If compaction
fails, the turn stops with an `[ERROR]`; type `continue` to retry, or `/compact`.

The history file gets two lines. The first is the compaction record:

```json
{"metadata":{"timestamp":"…","turn_number":3,"message_type":"compaction_summary","trigger":"auto","response_id":"resp_…","usage":{…}},"compaction":{"summary":"…"}}
```

The second is the continuation message, saved as a normal `user` record. It keeps the
current turn number, since only real user input advances the turn. To rebuild what the model currently sees, take the
system message plus every item after the last `compaction_summary` record.

## Tracing

Model calls are traced in [Arize Phoenix](https://docs.arize.com/phoenix), an open-source
observability server that runs locally, so traces never leave your machine. Start it
yourself in another terminal and keep it running:

```sh
docker run --name phoenix -p 127.0.0.1:6006:6006 \
  -v /Users/pk/phoenix_data:/mnt/data \
  -e PHOENIX_WORKING_DIR=/mnt/data \
  -e PHOENIX_ENABLE_AUTH=false \
  arizephoenix/phoenix
```

- `127.0.0.1:6006:6006` makes Phoenix reachable only from this machine.
- `PHOENIX_ENABLE_AUTH=false` turns off the login screen, which recent Phoenix images
  enable by default. With login on, the harness would also need an API key to send traces.
- `-v` keeps the trace database in a normal folder (`/Users/pk/phoenix_data`), so it
  survives removing the container or reinstalling Docker; `PHOENIX_WORKING_DIR` tells
  Phoenix to store its data there.

Next time, start the same container with `docker start phoenix`.
Then run the harness and open http://localhost:6006 to see project `harness`.
`start_tracing()` registers Phoenix as the trace destination and turns on OpenInference's
OpenAI instrumentation, which patches the OpenAI client: every model call, streamed or
not (including the compaction call), is recorded with its input, output, token counts,
and timing. Traces are sent from a background thread.

`main.py` groups the spans with the `with` blocks from `observability/tracing.py`:

```
session  main_agent_<timestamp>      trace_session: the whole run, named after its session folder
└─ turn 1                            trace_turn: one trace per user turn (input and final answer)
   ├─ Response                       model call, traced automatically
   ├─ current_time                   trace_tool: tool name, arguments, result
   ├─ compaction                     trace_compaction: trigger and token estimates
   │  └─ Response                    the summary call
   └─ Response
```

A span opened inside another becomes its child, so the automatic model-call spans nest
under the turn without extra code. A manual `/compact` happens outside a turn, so it is
its own trace. In Phoenix, the Traces tab lists turns and the Sessions tab lists runs. If Phoenix is not running, the
conversation works normally, but quitting waits about ten seconds while export retries;
set `TRACING_ENABLED = False` in `config.py` to turn tracing off; the `with` blocks then
do nothing. Tool and compaction spans show OK (✓) or error (red, with the reason).
A tool counts as failed when its result is `{"error": ...}`, such as a refused path or
a Docker failure; a `run_command` with a nonzero exit code is a normal result, since the
tool itself worked. Turn spans have no status unless an exception occurs.

## Tool-call classifier

Before each tool call runs, `run_loop()` asks `ToolClassifier.decide()` in
`tool_classifier/classifier.py`. The mode is printed at startup, starts from
`TOOL_CLASSIFIER_MODE` in `config.py`, and can be changed during a session:

| Command | Behavior |
| --- | --- |
| `/tool-classifier auto` | Default. A separate model (`CLASSIFIER_MODEL`) decides each call. |
| `/tool-classifier allow_all` | No checks; every call runs. |
| `/tool-classifier manual` | You answer `y` or `n` for each call, optionally with a note, such as `n, use git clean instead`. |
| `/tool-classifier` | Show the current mode. |

Every decider returns `Decision(allowed, decided_by, reason)`, defined in `classifier.py`.
`reason` is optional, so a future decider that only says yes or no, such as a decision
model, fits the same shape: it is one more `ToolClassifier` method returning a `Decision`.

In `auto` mode, `ToolClassifier._classify_with_llm()` fills `prompts/input_template.md` with the last two
user messages (each cut to 2,000 characters), the reasoning summary of the response
that requested the call, and the call itself, and sends it with
`prompts/system_prompt.md`. The model must answer with structured output:
`{"allowed": true|false, "reason": "..."}`. If the call fails or the answer is
unreadable, the tool call is denied.

A rejected call does not run. The model receives, as that call's result:

```text
Not run: this tool call was rejected by the classifier. Reason: deletes files outside the task.
```

The history file records the decision in that tool result's metadata, for example
`"decision": {"allowed": false, "decided_by": "user", "reason": "use git clean instead"}`.
In Phoenix, each decision is a `GUARDRAIL` span named `classify <tool>`, and the
classifier's model call nests inside it. Task tools skip the classifier (see Tasks).

## Tasks

For work with several steps, the model keeps a task list with three host tools. They
run in the harness, not in Docker: they take only JSON arguments, never a path or a
command, and only store them. `TaskList` in `tasks/task_list.py` holds the list and saves
it to the session folder's `tasks.json` after every change; the container sees that file
read-only at `/sessions/<session>/tasks.json`.

| Tool | Model gives | Returns |
| --- | --- | --- |
| `create_tasks(tasks)` | Each task's `title`, `description`, and `acceptance_criteria` | The new tasks |
| `update_task(task_id, status, result=None)` | `status` (`pending`, `in_progress`, `done`, `blocked`) and `result` | The updated task |
| `read_tasks(task_id=None)` | An optional id | Every task, or that one |

Every returned task has all its fields:

```json
{"id": 1, "title": "…", "description": "…", "acceptance_criteria": "…", "status": "pending", "result": null, "owner": "main_agent"}
```

The harness assigns `id`, the initial `pending` status, and `owner`. `blocked` means the
model tried but cannot finish the task now, for example because a dependency is missing;
it can go back to `in_progress` later. `update_task` refuses `done` or `blocked` without a
nonempty `result` (for blocked: what was tried and what stops it); a rule break or
invalid argument comes back to the model as `{"error": ...}`. The schemas come from the methods' type hints and
docstrings, through the same `build_schema()` as the Docker tools, and
`stream_model()` sends them alongside the Docker tools' schemas. Task tool calls skip
the classifier, since they cannot touch files or the network; their history metadata
records `"decided_by": "harness"`. They still get a tool span in Phoenix. A resumed
session reloads its `tasks.json`, and each compaction puts the current list into the
continuation message (see Compaction).

## Resuming a session

At startup, `choose_session()` in `utils/terminal.py` lists saved sessions, newest
first, `RESUME_SESSIONS_PER_PAGE` at a time, with **Next page →** and **← Previous page**
options. Each row shows when the session was last active, its turn count, and your first
and last message. Sessions from before the turn-zero session record existed (no
workspace recorded) are not listed. Choosing one:

1. Reuses the workspace from its session record (an error if that folder is gone).
2. Starts a fresh sandbox container, since containers are removed on exit.
3. Calls `Conversation.resume()`, which keeps appending to the **same** history file, so
   the Phoenix session (named after the session folder) continues too. It rebuilds `model_input`
   as the saved system message plus every item after the last `compaction_summary`
   record, or after the system message if the session was never compacted. Token
   counters are replayed from the stored `usage`, so the compaction check stays exact.
   A function call left without a result (after a crash or Ctrl-C) gets the result
   "Not run: the session ended before this tool call ran." A file-only
   `session_resumed` record saves the new container id and model.
4. Reprints the last `RESUME_REPLAY_TURNS` turns from the whole file, so you see your
   real conversation even where the model now sees a compaction summary.

The turn number continues from the file, and the classifier starts from
`TOOL_CLASSIFIER_MODE`.

