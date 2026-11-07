import json
import sys
from datetime import datetime
from zoneinfo import ZoneInfo


def current_time(timezone="UTC"):
    return datetime.now(ZoneInfo(timezone)).isoformat()


TOOLS = {"current_time": current_time}

TOOL_SCHEMAS = [
    {
        "type": "function",
        "name": "current_time",
        "description": "Get the current date and time in an IANA timezone, such as Asia/Kolkata.",
        "parameters": {
            "type": "object",
            "properties": {"timezone": {"type": "string"}},
            "additionalProperties": False,
        },
        "strict": False,
    }
]


def call_tool(sandbox, name, arguments):
    """Send tool calls to the container, including the example time tool."""
    try:
        return sandbox.execute(["python", "-I", "/opt/harness/tools.py", name, arguments])
    except RuntimeError as error:
        return json.dumps({"error": str(error)})


if __name__ == "__main__":
    # This entry point is invoked by Docker, not by the host conversation loop.
    try:
        result = TOOLS[sys.argv[1]](**json.loads(sys.argv[2]))
        print(result if isinstance(result, str) else json.dumps(result))
    except Exception as error:
        print(json.dumps({"error": str(error)}))
