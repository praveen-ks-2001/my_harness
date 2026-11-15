# Harness project map

A small Python terminal agent the user fully understands and controls, built up
incrementally for personal applications (such as a finance analyzer) and custom tools.
It is not meant to replace Claude Code or Codex. The conversation loop runs on the
host; tools run inside Docker against a chosen workspace.

Before planning or changing code, read the user's
[coding preferences](.instructions/coding-preferences.md). Current user instructions
take precedence. Keep changes small and discuss additional architecture before adding it.
Code is grouped by feature folder (`agent/`, `compaction/`, `sandbox/`, `tools/`), and
each feature keeps its prompts in its own `prompts/` subfolder.

## Where to look

| Location | Responsibility |
| --- | --- |
| [main.py](main.py) | Startup, the user-input loop, and the model/tool loop. |
| [utils/terminal.py](utils/terminal.py) | Workspace prompt and streamed-output printing. |
| [agent/model.py](agent/model.py) | Streamed OpenAI Responses API call. |
| [agent/conversation.py](agent/conversation.py) | API input items, turn numbering, and JSONL history. |
| [agent/prompts/system_message.md](agent/prompts/system_message.md) | The agent's system instructions; `{history_file}` and `{history_directory}` are filled in by `start_agent()`. |
| [compaction/compact.py](compaction/compact.py) | When to compact, the summary call, splitting `model_input` into units, and rendering items as XML. |
| [compaction/prompts/](compaction/prompts/) | The summarizer's system prompt, its input template, and the continuation template. |
| [tools/](tools/) | Tool modules registered with `@tool`, listed in [tools/\_\_init\_\_.py](tools/__init__.py). [registry.py](tools/registry.py) builds schemas and validates calls; [runner.py](tools/runner.py) is the container entry point. |
| [sandbox/sandbox.py](sandbox/sandbox.py) | Docker lifecycle, command execution, and `Sandbox.call_tool()`. |
| [config.py](config.py) | Grouped settings and automatic `.env` loading. |
| [Dockerfile](Dockerfile), [.dockerignore](.dockerignore) | Tool environment and restricted build context. |
| [README.md](README.md) | Usage, tool behavior, sandbox details, and history format. |

## Important boundaries

- `Conversation.model_input` contains original API items, including reasoning and tool
  calls. Metadata wrappers are written only to `chat_history/`, never sent to the model.
- Each history file starts with turn-zero session metadata identifying the workspace
  and container. Model output items carry `response_id` in metadata; the last item of
  each model call also carries its token `usage`. A turn advances once per user input, not once per model/tool call.
- Docker gets two mounts: the selected workspace read/write at `/workspace`, and
  `chat_history/` read-only at `/chat_history` so the model can search its own and past
  sessions. The default workspace is a reusable local `workspace/`; harness code and
  credentials stay outside, and a workspace containing the harness or history is refused.
- History files are named `main_agent_YYYYMMDD_HHMMSS_ffffff.jsonl`. The file tools only
  reach `/workspace`, so the model reads history with `run_command` (`rg`, `jq`, `sed`).
- Tool schemas come from type hints and Google-style docstrings; every argument needs
  an `Args:` entry or startup fails. The host only builds schemas; tool functions run
  in Docker, so tool dependencies must also be installed in the Dockerfile.
- Tool arguments reach the container's runner as JSON on stdin, not as a command-line
  argument, because Linux caps each argument at 128 KB.
- One user turn makes at most `MAX_MODEL_CALLS_PER_TURN` model calls, then control
  returns to the user.
- Before every model call, the input size is estimated as the last call's exact
  `input_tokens + output_tokens` plus characters/4 of items added since. Above
  `CONTEXT_WINDOW_TOKENS * COMPACT_AT_FRACTION`, or on `/compact`, `model_input` becomes
  the system message plus one user-role continuation message (summary + last two units
  verbatim). A unit is one user message and everything until the next one. The history
  gets a `compaction_summary` record, then that message as a normal `user` record that
  keeps the current turn number; only real user input advances the turn. Rebuilding from history means: system message plus
  everything after the last `compaction_summary` record.
- Tools have outbound network access. Install dependencies in the workspace, since
  the container root is read-only. There is no host-execution fallback.

Current tools: `read_file`, `write_file`, `edit_file`, `run_command`, and `current_time`.
Tool-call approval, session resume, subagents, and tracing remain future work;
their mention is not authorization to implement them. Verification preferences,
commit-message conventions, and the rule to keep this file and the README current
after every code change are in the coding preferences linked above.
