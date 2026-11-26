# Harness project map

A small Python terminal agent the user fully understands and controls, built up
incrementally for personal applications (such as a finance analyzer) and custom tools.
It is not meant to replace Claude Code or Codex. The conversation loop runs on the
host; tools run inside Docker against a chosen workspace.

Before planning or changing code, read the user's
[coding preferences](.instructions/coding-preferences.md). Current user instructions
take precedence. Keep changes small and discuss additional architecture before adding it.
Code is grouped by feature folder (`agent/`, `compaction/`, `observability/`, `offload/`, `sandbox/`, `tasks/`, `tool_classifier/`, `tools/`), and
each feature keeps its prompts in its own `prompts/` subfolder.

## Where to look

| Location | Responsibility |
| --- | --- |
| [main.py](main.py) | `start_agent()` (startup), `user_input_loop()` (input and commands), and `run_loop()` (the model/tool loop). |
| [utils/terminal.py](utils/terminal.py) | All terminal I/O: prompt_toolkit input (history, Tab completion, paste) and Rich output (colored labels, Markdown answers, JSON tool calls). |
| [agent/model.py](agent/model.py) | Streamed OpenAI Responses API call. |
| [agent/conversation.py](agent/conversation.py) | API input items, turn numbering, and JSONL history. `Conversation.start()` creates a session; `Conversation.resume()` rebuilds one from its folder's history file. |
| [agent/prompts/system_message.md](agent/prompts/system_message.md) | The agent's system instructions, in sections: Harness, Workspace, Tools (one line per tool on when to use it), Tasks, Large outputs, Session files, Context management, Session context. `Conversation.start()` fills in the container paths (`{workspace_directory}`, `{sessions_directory}`, `{session_directory}`, `{history_file}`, `{tasks_file}`), `{max_model_calls_per_turn}`, and the output limits (`{tool_output_max_chars}`, `{tool_output_head_chars}`, `{tool_output_tail_chars}`, `{read_file_max_chars}`) from `config.py`. A new tool needs its line in the Tools section. |
| [compaction/compact.py](compaction/compact.py) | When to compact, the summary call, splitting `model_input` into units, and rendering items as XML. |
| [compaction/prompts/](compaction/prompts/) | The summarizer's system prompt (sections: Input, Attached after your summary, Rules, Sections, Next step, Format), its input template, and the continuation template, which points the model to its history file for exact details. |
| [tools/](tools/) | Tool modules registered with `@tool`, listed in [tools/\_\_init\_\_.py](tools/__init__.py). [registry.py](tools/registry.py) builds schemas and validates calls; [runner.py](tools/runner.py) is the container entry point. |
| [tasks/task_list.py](tasks/task_list.py) | `TaskList`: the session's task list in `tasks.json` and its host tools `create_tasks`, `update_task`, `read_tasks` (`TOOL_NAMES`), with schemas from `build_schema()`. |
| [offload/offload.py](offload/offload.py) | `cap_tool_output()`: a result over `TOOL_OUTPUT_MAX_CHARS` is saved to `sessions/<id>/tool_outputs/` and replaced by its head, a marker, and its tail. |
| [tool_classifier/](tool_classifier/) | Decides before each tool call whether it runs: `ToolClassifier.decide()` returns a `Decision(allowed, decided_by, reason)`. Modes `auto` (LLM, `_classify_with_llm`), `allow_all`, `manual`; helpers in `utils.py`, prompts in `prompts/`. |
| [observability/tracing.py](observability/tracing.py) | `start_tracing()` (OpenAI calls auto-traced to local Phoenix) and the `trace_session`/`trace_turn`/`trace_tool`/`trace_compaction` blocks used in `main.py`. |
| [sandbox/sandbox.py](sandbox/sandbox.py) | Docker lifecycle, command execution, and `Sandbox.call_tool()`. |
| [config.py](config.py) | Grouped settings and automatic `.env` loading. |
| [Dockerfile](Dockerfile), [.dockerignore](.dockerignore) | Tool environment and restricted build context. |
| [README.md](README.md) | Usage, tool behavior, sandbox details, and history format. |

## Important boundaries

- `Conversation.model_input` contains original API items, including reasoning and tool
  calls. Metadata wrappers are written only to `sessions/`, never sent to the model.
- Each history file starts with turn-zero session metadata identifying the workspace
  and container. Model output items carry `response_id` in metadata; the last item of
  each model call also carries its token `usage`. A turn advances once per user input, not once per model/tool call.
- Docker gets two mounts: the selected workspace read/write at `/workspace`, and
  `sessions/` read-only at `/sessions` so the model can search its own and past
  sessions. The default workspace is a reusable local `workspace/`; harness code and
  credentials stay outside, and a workspace containing the harness or sessions is refused.
- Each run gets a session folder `sessions/main_agent_YYYYMMDD_HHMMSS_ffffff/` holding
  `history.jsonl`, once tasks exist `tasks.json`, and capped outputs in `tool_outputs/`; the folder name
  identifies the session. `write_file`/`edit_file` only reach `/workspace`; `read_file` also reads `/sessions`.
- Every tool result passes through `cap_tool_output()` in `run_loop`: over `TOOL_OUTPUT_MAX_CHARS` (10,000)
  the model sees the first 2,000 and last 1,000 characters plus a marker with the saved file's path (JSON
  fields such as `stdout` are capped separately); history metadata records `offloaded_to`. `read_file`
  pages at `READ_FILE_MAX_CHARS` (8,000, passed to the container as an env var), with a size header and a
  `start_line` footer; a single line over the limit is cut with a `sed | cut` hint. Markers and footers only
  hint ("slice or search it with bash; see Large outputs"); the full instructions live in the system message.
- Tool schemas come from type hints and Google-style docstrings; every argument needs
  an `Args:` entry or startup fails. The host only builds schemas; tool functions run
  in Docker, so tool dependencies must also be installed in the Dockerfile.
- Tool arguments reach the container's runner as JSON on stdin, not as a command-line
  argument, because Linux caps each argument at 128 KB.
- Before each tool call, `ToolClassifier.decide()` runs (mode from `TOOL_CLASSIFIER_MODE`,
  switchable with `/tool-classifier <mode>`). A rejected call does not run; its
  `function_call_output` is a "Not run: rejected by … Reason: …" message, and the
  decision is saved as `decision` in that tool result's history metadata. The LLM
  classifier sees the last two user messages, the response's reasoning summary, and the
  call, and denies if it fails. `reason` is optional so yes/no-only deciders fit.
- Resuming (chosen at startup) appends to the same history file. `model_input` is rebuilt
  as the system record plus every item after the last `compaction_summary` (or after the
  system record), token counters are replayed from stored `usage` (skipping the
  compaction record's), unanswered function calls get a "Not run" result, and a
  file-only `session_resumed` record holds the new container id and model.
- One user turn makes at most `MAX_MODEL_CALLS_PER_TURN` model calls, then control
  returns to the user.
- Before every model call, the input size is estimated as the last call's exact
  `input_tokens + output_tokens` plus characters/4 of items added since. Above
  `CONTEXT_WINDOW_TOKENS * COMPACT_AT_FRACTION`, or on `/compact`, `model_input` becomes
  the system message plus one user-role continuation message (summary + last two units
  verbatim + `<task_list>` from `TaskList.render()`, rendered by code, never by the summarizer). A unit is one user message and everything until the next one. The history
  gets a `compaction_summary` record, then that message as a normal `user` record that
  keeps the current turn number; only real user input advances the turn. Rebuilding from history means: system message plus
  everything after the last `compaction_summary` record.
- Task tools are host tools: `run_loop` sends names in `TaskList.TOOL_NAMES` to
  `TaskList.call_tool()` instead of Docker, without the classifier (`decided_by: "harness"`).
  A host tool takes only data arguments, never a path, command, or URL. Only the harness
  writes `tasks.json`; statuses are `pending`, `in_progress`, `done`, `blocked`, and
  `update_task` refuses `done` or `blocked` without a `result`.
- Tools have outbound network access. Install dependencies in the workspace, since
  the container root is read-only. There is no host-execution fallback.

Current tools: `read_file`, `write_file`, `edit_file`, `bash`, and `current_time`
(Docker), plus `create_tasks`, `update_task`, and `read_tasks` (host).
Tracing: one Phoenix session per run (`session.id` = session folder name), one trace per
user turn. Each tool call is one tool span, with its `classify <tool>` guardrail span
nested inside. Tool and compaction spans are marked OK or error; a tool result of
`{"error": ...}` counts as failed, while a nonzero `bash` exit does not.
Subagents remain future work;
their mention is not authorization to implement them. Verification preferences,
commit-message conventions, and the rule to keep this file and the README current
after every code change are in the coding preferences linked above.
