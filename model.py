import config
# Importing tools.registry first runs tools/__init__.py, which registers every tool.
from tools.registry import tool_schemas


TOOL_SCHEMAS = tool_schemas()


def call_model(client, model_input):
    if not config.OPENAI_MODEL:
        raise ValueError("Set OPENAI_MODEL in .env or config.py before calling the model")
    return client.responses.create(
        model=config.OPENAI_MODEL,
        input=model_input,
        tools=TOOL_SCHEMAS,
        reasoning={"summary": "auto"},
        store=False,
    )
