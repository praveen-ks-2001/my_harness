# Coding preferences

## Scope and workflow

- Start with the smallest understandable version that handles the requested behavior.
  Add features incrementally as the user asks for them.
- Discuss meaningful architectural choices and their tradeoffs before introducing
  additional structure. A suggestion is not approval to implement extra features.
- Complete changes the user has requested without repeatedly asking for confirmation.
- Avoid speculative infrastructure: command-line argument parsers, provider frameworks,
  plugin systems, tracing, Docker, and subagents should arrive when they are needed.
- Reference repositories provide inspiration for simple modular code. Do not repeatedly
  revisit them unless the current question requires it.

## Readability and naming

- Make the execution flow easy to follow from the entry point through the model call,
  response handling, tool execution, and conversation update.
- Prefer straightforward code that explains itself over clever or compressed code.
- Name variables after their contents and purpose. For example, `model_input` contains
  API-ready items, `api_item` is one such item, and `history_record` includes file metadata.
- Name methods after the input shape or operation they handle. Prefer specific parallel
  names such as `append_text_message`, `append_response_item`, and `append_tool_result`
  over an ambiguous umbrella name beside a more specialized one.
- Avoid vague or grandiose terminology. Use `message_type` instead of shadowing Python's
  built-in `type` when a descriptive argument name is needed.

## Classes and abstraction

- Use a class when related state and behavior belong together. `Conversation` owns
  model input, the turn number, and its history file path.
- Keep message construction inside `Conversation` so the main loop can pass text or
  model output without assembling message dictionaries itself.
- Preserve complete model response items, including reasoning continuation fields and
  tool-call identifiers, rather than rebuilding them from displayed text.
- Share genuinely repeated logic. One recording method can serve the different append
  methods while writing history and updating model input.
- Inline a small helper used by just one function when extracting it adds indirection
  without a clear independent responsibility. The former `_save_message` helper was
  merged into `_record_item` for this reason.
- Do not add layers, base classes, factories, or compatibility aliases solely for
  hypothetical future requirements. A separate file should have a concrete purpose.

## Current project conventions

- Centralize settings such as the history directory, prompt path, and model name in
  `config.py`. Keep secrets in the environment or the ignored `.env` file.
- Store the system instructions in `prompts/system_message.md` and read them at startup.
- Initialize one conversation before the user-input loop so history survives across turns.
- Keep API input and file records distinct: `model_input` contains original API items;
  JSONL records wrap those items with metadata. Never send the metadata wrapper to OpenAI.
- Save history continuously in `chat_history/` with a timestamp filename. Record the
  timestamp, user-turn number, and message type alongside the original item.
- Count a turn once per user input. The initial system message is turn 0; model calls
  and tool results within a user turn retain that turn's number.
- Use uppercase terminal labels in square brackets, with a blank line before content:
  `[USER]`, `[ASSISTANT]`, `[REASONING]`, `[TOOL]`, and `[TOOL RESULT]`.
- Do not create a test folder or persistent test suite unless the user asks to add one.
  Use focused, one-off offline checks when needed to verify changes.
- Keep `examples/` local and ignored by Git unless the user requests otherwise.
