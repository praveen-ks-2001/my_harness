"""Model tools. Importing a module below runs its @tool decorators and registers its tools.

To add a tool:
1. Write a type-hinted function in a module in this folder and decorate it with @tool.
2. Give it a Google-style docstring with a description and an `Args:` entry for every
   argument. They become the schema the model sees; startup fails if one is missing.
3. For a new module, add its name to the import below.
4. Tools run inside Docker, so install any third-party import in the Dockerfile too.

    @tool
    def current_time(timezone: str = "UTC") -> str:
        \"\"\"Get the current date and time in an IANA timezone.

        Args:
            timezone: IANA timezone name, such as Asia/Kolkata.
        \"\"\"
"""

from tools import clock, files, shell  # noqa: F401
