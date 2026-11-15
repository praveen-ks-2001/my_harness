def reasoning_summary(response):
    """Return the readable reasoning summary written before the tool calls, if any."""
    return "\n\n".join(
        part.text
        for item in response.output if item.type == "reasoning"
        for part in item.summary
    )


def rejection_message(decision):
    """The tool result the model receives instead of running a rejected call."""
    decided_by = {"classifier": "the classifier", "user": "the user"}.get(decision.decided_by, decision.decided_by)
    message = f"Not run: this tool call was rejected by {decided_by}."
    if decision.reason:
        message += f" Reason: {decision.reason}"
    return message
