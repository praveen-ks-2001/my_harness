# Harness project map

A small Python terminal agent the user fully understands and controls, built up
incrementally for personal applications (such as a finance analyzer) and custom tools.
It is not meant to replace Claude Code or Codex. The conversation loop runs on the
host; tools run inside Docker against a chosen workspace.

Before planning or changing code, read the user's
[coding preferences](.instructions/coding-preferences.md). Current user instructions
take precedence. Keep changes small and discuss additional architecture before adding it.

## Where to look

| Location | Responsibility |
| --- | --- |
| [main.py](main.py) | Workspace selection, startup, terminal I/O, and the model/tool loop. |
| [model.py](model.py) | OpenAI Responses API call. |
| [conversation.py](conversation.py) | API input items, turn numbering, and JSONL history. |
| [tools/](tools/) | Tool modules registered with `@tool`, listed in [tools/\_\_init\_\_.py](tools/__init__.py). [registry.py](tools/registry.py) builds schemas and validates calls; [runner.py](tools/runner.py) is the container entry point. |
| [sandbox.py](sandbox.py) | Docker lifecycle, command execution, and `Sandbox.call_tool()`. |
| [config.py](config.py) | Grouped settings and automatic `.env` loading. |
| [prompts/system_message.md](prompts/system_message.md) | The agent's system instructions. |
| [Dockerfile](Dockerfile), [.dockerignore](.dockerignore) | Tool environment and restricted build context. |
| [README.md](README.md) | Usage, tool behavior, sandbox details, and history format. |

## Important boundaries

- `Conversation.model_input` contains original API items, including reasoning and tool
  calls. Metadata wrappers are written only to `chat_history/`, never sent to the model.
- Each history file starts with turn-zero session metadata identifying the workspace
  and container. Model output items carry `response_id` in metadata; the last item of
  each model call also carries its token `usage`. A turn advances once per user input, not once per model/tool call.
- Only the selected workspace is shared with Docker, at `/workspace`. The default is
  a reusable local `workspace/`; harness code, credentials, and history stay outside.
- Tool schemas come from type hints and Google-style docstrings; every argument needs
  an `Args:` entry or startup fails. The host only builds schemas; tool functions run
  in Docker, so tool dependencies must also be installed in the Dockerfile.
- Tool arguments reach the container's runner as JSON on stdin, not as a command-line
  argument, because Linux caps each argument at 128 KB.
- One user turn makes at most `MAX_MODEL_CALLS_PER_TURN` model calls, then control
  returns to the user.
- Tools have outbound network access. Install dependencies in the workspace, since
  the container root is read-only. There is no host-execution fallback.

Current tools: `read_file`, `write_file`, `edit_file`, `run_command`, and `current_time`.
Tool-call approval, session resume/compaction, subagents, and tracing remain future work;
their mention is not authorization to implement them. Verification preferences,
commit-message conventions, and the rule to keep this file and the README current
after every code change are in the coding preferences linked above.
