"""Container entry point for one tool call; the host conversation loop never runs this.

Sandbox.call_tool() runs `python -P -m tools.runner <tool name>` inside Docker and sends
the model's JSON arguments on stdin. The result is printed for the host to read.
"""

import json
import sys

from tools.registry import run_tool


if __name__ == "__main__":
    try:
        result = run_tool(sys.argv[1], json.loads(sys.stdin.read()))
        print(result if isinstance(result, str) else json.dumps(result))
    except Exception as error:
        print(json.dumps({"error": str(error)}))
