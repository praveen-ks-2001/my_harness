import json
from pathlib import Path
from typing import Literal, TypedDict

from pydantic import validate_call

from tools.registry import build_schema


# Statuses that need a result, and what it should say.
RESULT_NEEDED = {
    "done": "what it produced or found, and where it is",
    "blocked": "what you tried and what stops it",
}


class NewTask(TypedDict):
    """The fields the model gives when it creates a task; the harness adds the rest."""

    title: str
    description: str
    acceptance_criteria: str


class TaskList:
    """The agent's task list, saved in its session folder's tasks.json.

    The model changes it only through the methods named in TOOL_NAMES, which are host
    tools: they run in the harness, not in Docker, and only store the model's arguments.
    """

    TOOL_NAMES = ("create_tasks", "update_task", "read_tasks")

    def __init__(self, tasks_path, owner):
        self.tasks_path = Path(tasks_path)
        self.owner = owner
        # A resumed session continues with its saved list.
        self.tasks = json.loads(self.tasks_path.read_text(encoding="utf-8"))["tasks"] if self.tasks_path.exists() else []
        # Built at startup, so a missing Args entry fails at once, as with the Docker tools.
        self.tool_schemas = [build_schema(getattr(self, name)) for name in self.TOOL_NAMES]

    def call_tool(self, name, arguments):
        """Validate the model's JSON arguments, run the task tool, and return its JSON result."""
        try:
            result = validate_call(getattr(self, name))(**json.loads(arguments))
        except ValueError as error:
            result = {"error": str(error)}
        return json.dumps(result, ensure_ascii=False)

    def create_tasks(self, tasks: list[NewTask]) -> dict:
        """Add tasks to your task list, in the order you plan to do them.

        The harness gives each task an id, sets its status to pending, and returns the new
        tasks with every field.

        Args:
            tasks: The tasks to add. Each has a title (a few words), a description (what to
                do and why), and acceptance_criteria (what must be true for the task to
                count as done).
        """
        next_id = max((task["id"] for task in self.tasks), default=0) + 1
        created = [
            {
                "id": next_id + offset,
                "title": task["title"],
                "description": task["description"],
                "acceptance_criteria": task["acceptance_criteria"],
                "status": "pending",
                "result": None,
                "owner": self.owner,
            }
            for offset, task in enumerate(tasks)
        ]
        self.tasks.extend(created)
        self._save()
        return {"tasks": created}

    def update_task(
        self, task_id: int, status: Literal["pending", "in_progress", "done", "blocked"], result: str | None = None,
    ) -> dict:
        """Change a task's status, and record its result once it is done or blocked.

        Returns the updated task with every field.

        Args:
            task_id: ID of the task to update.
            status: pending, in_progress (you are working on it now), done (its acceptance
                criteria are met), or blocked (you tried, but it cannot be finished now, for
                example because something it depends on is missing).
            result: For done, what the task produced or found, and where it is; for
                blocked, what you tried and what stops it. Required for done and blocked;
                replaces any earlier result.
        """
        task = self._find(task_id)
        result_missing = not (result or "").strip()
        if status in RESULT_NEEDED and result_missing:
            raise ValueError(f"A {status} task needs a result: {RESULT_NEEDED[status]}.")
        task["status"] = status
        if result is not None:
            task["result"] = result
        self._save()
        return {"task": task}

    def read_tasks(self, task_id: int | None = None) -> dict:
        """Read your task list: every task, or only the one with task_id.

        Args:
            task_id: ID of one task to read. Reads every task when omitted.
        """
        if task_id is None:
            return {"tasks": self.tasks}
        return {"task": self._find(task_id)}

    def _find(self, task_id):
        for task in self.tasks:
            if task["id"] == task_id:
                return task
        raise ValueError(f"No task with id {task_id}. Existing ids: {[task['id'] for task in self.tasks]}")

    def _save(self):
        self.tasks_path.write_text(json.dumps({"tasks": self.tasks}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
