from docstring_parser import parse
from pydantic import TypeAdapter, validate_call


TOOLS = {}


def tool(function):
    """Register a type-hinted function with a Google-style docstring as a model tool."""
    if function.__name__ in TOOLS:
        raise ValueError(f"Duplicate tool name: {function.__name__}")
    TOOLS[function.__name__] = function
    return function


def build_schema(function):
    """Build the Responses API schema from a tool's signature and docstring."""
    docstring = parse(function.__doc__ or "")
    if not docstring.description:
        raise ValueError(f"Tool {function.__name__} needs a docstring description")

    parameters = TypeAdapter(function).json_schema()
    argument_descriptions = {param.arg_name: param.description for param in docstring.params}
    for argument_name, argument_schema in parameters["properties"].items():
        if not argument_descriptions.get(argument_name):
            raise ValueError(f"Tool {function.__name__} does not document argument {argument_name}")
        # Pydantic adds titles such as "Start Line"; the description already explains it.
        argument_schema.pop("title", None)
        argument_schema["description"] = argument_descriptions[argument_name]

    return {
        "type": "function",
        "name": function.__name__,
        "description": docstring.description.strip(),
        "parameters": parameters,
        "strict": False,
    }


def tool_schemas():
    return [build_schema(function) for function in TOOLS.values()]


def run_tool(name, arguments):
    """Validate the model's arguments against the tool's type hints, then call it."""
    if name not in TOOLS:
        raise ValueError(f"Unknown tool: {name}")
    return validate_call(TOOLS[name])(**arguments)
