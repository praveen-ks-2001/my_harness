import json
import os
import subprocess
from pathlib import Path
from uuid import uuid4

import config


def _run_docker(*arguments, input_text=None):
    try:
        result = subprocess.run(
            ["docker", *arguments], input=input_text, capture_output=True, text=True,
        )
    except FileNotFoundError:
        raise RuntimeError("Docker is not installed or is not on PATH") from None
    if result.returncode != 0:
        raise RuntimeError(
            result.stderr.strip() or result.stdout.strip()
            or f"Docker {arguments[0]} failed with exit code {result.returncode}"
        )
    return result.stdout.strip()


class Sandbox:
    """Run this session's tools in Docker with one writable host workspace."""

    def __init__(self, workspace_directory):
        self.workspace_directory = Path(workspace_directory).expanduser().resolve()
        if not self.workspace_directory.is_dir():
            raise ValueError(f"Workspace folder does not exist: {self.workspace_directory}")
        # Mounting a parent of the harness would expose its credentials and history.
        for private_directory in (config.PROJECT_DIRECTORY, config.HISTORY_DIRECTORY):
            if private_directory.resolve().is_relative_to(self.workspace_directory):
                raise ValueError("Choose a workspace that does not contain the harness or its history")
        self.container_name = f"harness-{uuid4().hex[:12]}"
        self.container_id = None
        self.image_id = None

    def start(self):
        self.image_id = _run_docker(
            "build", "--quiet", "--tag", config.SANDBOX_IMAGE, str(config.PROJECT_DIRECTORY),
        )
        self.container_id = _run_docker(
            "run", "--detach", "--rm", "--init", "--name", self.container_name,
            "--workdir", config.CONTAINER_WORKSPACE_DIRECTORY,
            "--mount", (
                f"type=bind,source={self.workspace_directory},"
                f"target={config.CONTAINER_WORKSPACE_DIRECTORY}"
            ),
            "--user", f"{os.getuid()}:{os.getgid()}",
            "--read-only", "--tmpfs", "/tmp:rw,nosuid,nodev,size=64m",
            "--network", config.SANDBOX_NETWORK, "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges",
            "--env", "HOME=/tmp", "--env", "PYTHONDONTWRITEBYTECODE=1",
            self.image_id, "sleep", "infinity",
        )

    def execute(self, command, input_text):
        """Execute an argument list in the container; never execute it on the host.

        input_text is sent through stdin, which has no size limit, unlike each
        command-line argument, which Linux caps at 128 KB.
        """
        if self.container_id is None:
            raise RuntimeError("The sandbox is not running")
        return _run_docker(
            "exec", "--interactive",
            "--env", f"TOOL_TIMEOUT_SECONDS={config.TOOL_TIMEOUT_SECONDS}",
            "--workdir", config.CONTAINER_WORKSPACE_DIRECTORY, self.container_id,
            # Allow the command runner time to save its partial output after a timeout.
            "timeout", "--kill-after=5", str(config.TOOL_TIMEOUT_SECONDS + 5), *command,
            input_text=input_text,
        )

    def call_tool(self, name, arguments):
        """Run one tool through the container's tool runner and return its printed result."""
        try:
            # -P keeps files in /workspace from shadowing the tool package's imports.
            return self.execute(["python", "-P", "-m", "tools.runner", name], input_text=arguments)
        except RuntimeError as error:
            return json.dumps({"error": str(error)})

    def stop(self):
        if self.container_id is not None:
            _run_docker("rm", "--force", self.container_id)
            self.container_id = None

    def __enter__(self):
        try:
            self.start()
        except BaseException:
            # An interrupted run may create the container before returning its ID.
            if self.image_id is not None:
                subprocess.run(
                    ["docker", "rm", "--force", self.container_name], capture_output=True,
                )
            raise
        return self

    def __exit__(self, *exc_info):
        self.stop()
