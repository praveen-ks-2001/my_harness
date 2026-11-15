import json
from dataclasses import dataclass

from openai import OpenAIError

import config
from tool_classifier.utils import reasoning_summary
from utils.terminal import ask_tool_approval


# Structured output: the classifier model must answer with exactly these two fields.
ANSWER_FORMAT = {
    "type": "json_schema",
    "name": "tool_call_decision",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "allowed": {"type": "boolean"},
            "reason": {"type": "string"},
        },
        "required": ["allowed", "reason"],
        "additionalProperties": False,
    },
}
# Keeps a long message, such as a compaction summary, from flooding the classifier.
MAX_CHARACTERS_PER_USER_MESSAGE = 2000


@dataclass
class Decision:
    """Whether a tool call may run, who decided, and why (optional: some deciders only say yes or no)."""

    allowed: bool
    decided_by: str
    reason: str | None = None


class ToolClassifier:
    """Decide before each tool call whether it runs, according to the current mode.

    auto: an LLM decides. allow_all: every call runs. manual: the user decides.
    A new decider, such as a decision model, is one more method returning a Decision.
    """

    MODES = ("auto", "allow_all", "manual")

    def __init__(self, client, mode):
        self.client = client
        self.mode = mode

    def decide(self, tool_call, response, conversation):
        if self.mode == "allow_all":
            return Decision(allowed=True, decided_by="allow_all")
        if self.mode == "manual":
            allowed, note = ask_tool_approval()
            return Decision(allowed=allowed, decided_by="user", reason=note or None)
        return self._classify_with_llm(
            tool_call=tool_call,
            user_messages=conversation.recent_user_messages(count=2),
            reasoning_text=reasoning_summary(response),
        )

    def _classify_with_llm(self, tool_call, user_messages, reasoning_text):
        """Ask a separate model whether the tool call should run; deny if it cannot answer."""
        system_prompt = config.TOOL_CLASSIFIER_SYSTEM_PROMPT_FILE.read_text(encoding="utf-8")
        input_text = config.TOOL_CLASSIFIER_INPUT_TEMPLATE_FILE.read_text(encoding="utf-8").format(
            user_messages="\n".join(
                f"<message>\n{message[:MAX_CHARACTERS_PER_USER_MESSAGE]}\n</message>" for message in user_messages
            ),
            reasoning=reasoning_text or "(no reasoning summary)",
            tool_name=tool_call.name,
            arguments=tool_call.arguments,
        )
        try:
            response = self.client.responses.create(
                model=config.CLASSIFIER_MODEL,
                input=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": input_text},
                ],
                text={"format": ANSWER_FORMAT},
                store=False,
            )
            answer = json.loads(response.output_text)
        except (OpenAIError, json.JSONDecodeError) as error:
            # A broken safety check must not let calls through.
            return Decision(allowed=False, decided_by="classifier", reason=f"Classifier unavailable: {error}")
        return Decision(allowed=answer["allowed"], decided_by="classifier", reason=answer["reason"])
