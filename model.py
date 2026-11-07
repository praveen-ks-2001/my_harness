import config

from tools import TOOL_SCHEMAS


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
