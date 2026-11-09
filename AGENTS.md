# Harness project map

A small Python terminal agent, growing incrementally into a coding assistant. The
conversation loop runs on the host; tools run inside Docker against a chosen workspace.

Before planning or changing code, read the user's
[coding preferences](.instructions/coding-preferences.md). Current user instructions
take precedence. Keep changes small and discuss additional architecture before adding it.

## Where to look

| Location | Responsibility |
| --- | --- |
| [main.py](main.py) | Workspace selection, startup, terminal I/O, and the model/tool loop. |
| [model.py](model.py) | OpenAI Responses API call. |
| [conversation.py](conversation.py) | API input items, turn numbering, and JSONL history. |
| [tools.py](tools.py) | Tool functions, schemas, dispatch, and the container's tool runner. |
| [sandbox.py](sandbox.py) | Docker lifecycle and command execution. |
| [config.py](config.py) | Grouped settings and automatic `.env` loading. |
| [prompts/system_message.md](prompts/system_message.md) | The agent's system instructions. |
| [Dockerfile](Dockerfile), [.dockerignore](.dockerignore) | Tool environment and restricted build context. |
| [README.md](README.md) | Usage, tool behavior, sandbox details, and history format. |

## Important boundaries

- `Conversation.model_input` contains original API items, including reasoning and tool
  calls. Metadata wrappers are written only to `chat_history/`, never sent to the model.
- Each history file starts with turn-zero session metadata identifying the workspace
  and container. A turn advances once per user input, not once per model/tool call.
- Only the selected workspace is shared with Docker, at `/workspace`. The default is
  a reusable local `workspace/`; harness code, credentials, and history stay outside.
- Tools have outbound network access. Install dependencies in the workspace, since
  the container root is read-only. There is no host-execution fallback.

Current tools: `read_file`, `write_file`, `edit_file`, `run_command`, and `current_time`.
Tool-call approval, session resume/compaction, subagents, and tracing remain future work;
their mention is not authorization to implement them. Verification preferences and
commit-message conventions are in the coding preferences linked above.
