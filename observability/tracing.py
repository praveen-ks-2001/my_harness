from openinference.instrumentation.openai import OpenAIInstrumentor
from phoenix.otel import register

import config


def start_tracing():
    """Record every OpenAI call as a trace in the local Phoenix server.

    After this runs, the OpenAI client is patched automatically: each model call's
    input, output, token usage, and timing is sent to Phoenix without other code changes.
    """
    if not config.TRACING_ENABLED:
        return
    # batch=True sends traces from a background thread, so a stopped Phoenix server
    # never slows down the conversation.
    tracer_provider = register(
        project_name=config.PHOENIX_PROJECT_NAME,
        endpoint=config.PHOENIX_ENDPOINT,
        batch=True,
    )
    OpenAIInstrumentor().instrument(tracer_provider=tracer_provider)
