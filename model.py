import config
# Importing tools.registry first runs tools/__init__.py, which registers every tool.
from tools.registry import tool_schemas


TOOL_SCHEMAS = tool_schemas()


def stream_model(client, model_input):
    """Start a streamed model call; use it in a `with` block and iterate its events."""
    if not config.OPENAI_MODEL:
        raise ValueError("Set OPENAI_MODEL in .env or config.py before calling the model")
    return client.responses.stream(
        model=config.OPENAI_MODEL,
        input=model_input,
        tools=TOOL_SCHEMAS,
        reasoning={"summary": "auto"},
        store=False,
    )
