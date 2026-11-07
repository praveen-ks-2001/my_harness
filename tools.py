import json
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


def call_tool(name, arguments):
    try:
        result = TOOLS[name](**json.loads(arguments))
        return result if isinstance(result, str) else json.dumps(result)
    except Exception as error:
        return json.dumps({"error": str(error)})
