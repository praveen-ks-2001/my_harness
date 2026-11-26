import json
from contextlib import contextmanager
from dataclasses import asdict

from openinference.instrumentation import OITracer, TraceConfig, using_session
from openinference.instrumentation.openai import OpenAIInstrumentor
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from phoenix.otel import register

import config


# Spans from this tracer reach Phoenix once start_tracing() has run; with tracing turned
# off they do nothing, so callers never need to check TRACING_ENABLED.
tracer = OITracer(trace.get_tracer(__name__), TraceConfig())


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


def trace_session(session_id):
    """Tag every span created inside this block, including model calls, with the session id."""
    return using_session(session_id)


@contextmanager
def trace_turn(turn_number, user_message):
    """Open one trace for a user turn; the model, tool, and compaction spans nest inside it."""
    with tracer.start_as_current_span(name=f"turn {turn_number}", openinference_span_kind="agent") as span:
        span.set_input(value=user_message)
        span.set_attribute(key="turn_number", value=turn_number)
        yield span


@contextmanager
def trace_tool(name, arguments):
    """One TOOL span per tool call; the classifier's span and model call nest inside it."""
    with tracer.start_as_current_span(name=name, openinference_span_kind="tool") as span:
        span.set_tool(name=name, parameters=arguments)
        span.set_input(value=arguments, mime_type="application/json")
        yield span


@contextmanager
def trace_compaction(trigger, tokens_before):
    with tracer.start_as_current_span(name="compaction", openinference_span_kind="chain") as span:
        span.set_input(value=f"{trigger} compaction of about {tokens_before:,} tokens")
        span.set_attribute(key="trigger", value=trigger)
        yield span


@contextmanager
def trace_tool_decision(tool_name, arguments, mode):
    """One GUARDRAIL span per tool call: whether the classifier, the user, or nobody allowed it."""
    with tracer.start_as_current_span(name=f"classify {tool_name}", openinference_span_kind="guardrail") as span:
        span.set_input(value=f"{tool_name}({arguments})\nmode: {mode}")
        span.set_attribute(key="classifier_mode", value=mode)
        yield span


def record_decision(span, decision):
    span.set_output(value=json.dumps(asdict(decision)), mime_type="application/json")
    span.set_attribute(key="allowed", value=decision.allowed)
    mark_ok(span)

def record_tool_result(span, result):
    """Save a tool's result on its span; a result like {"error": "..."} marks the span failed."""
    span.set_output(value=result)
    try:
        error = json.loads(result).get("error")
    except (json.JSONDecodeError, AttributeError):
        # Plain text, or JSON that is not an object, is a successful result.
        error = None
    if error:
        mark_failed(span, message=error)
    else:
        mark_ok(span)


def mark_ok(span):
    span.set_status(Status(status_code=StatusCode.OK))


def mark_failed(span, message):
    """Show the span as an error (red) in Phoenix, with the message as the reason."""
    span.set_status(Status(status_code=StatusCode.ERROR, description=message))
