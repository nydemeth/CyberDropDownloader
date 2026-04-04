from __future__ import annotations

from typing import TYPE_CHECKING

from rich.live import Live
from rich.markup import escape
from rich.progress import Progress, Task, TaskID
from rich.text import Text

if TYPE_CHECKING:
    from pathlib import Path

    from rich.console import RenderableType


def create_live(renderable: RenderableType) -> Live:
    return Live(
        auto_refresh=True,
        refresh_per_second=20,
        transient=False,
        get_renderable=lambda: renderable,
    )


def hyperlink(file_path: Path, text: str | None = None) -> Text:
    text = escape(text or str(file_path))
    return Text.from_markup(f"[link={file_path.as_uri()}]{text}[/link]", style="blue")


class DictProgress(Progress):
    """A progress with a dict like interface to access tasks"""

    def __getitem__(self, task_id: TaskID) -> Task:
        with self._lock:
            return self._tasks[task_id]

    def __len__(self) -> int:
        with self._lock:
            return len(self._tasks)
