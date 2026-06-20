from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import aiohttp
import inquirer
import inquirer.questions
from inquirer.themes import BlueComposure
from rich.console import Console
from rich.markdown import Markdown
from rich.text import Text

from cyberdrop_dl import __version__, aio, stats
from cyberdrop_dl.hasher import Hasher, hash_directory
from cyberdrop_dl.progress import hyperlink
from cyberdrop_dl.sorter import Sorter
from cyberdrop_dl.utils import text_editor

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from cyberdrop_dl.manager import Manager


_ERROR = Text("ERROR:  ", style="bold red")
_WARNING = Text("WARNING:", style="bold yellow")
_CHANGELOG_URL = "https://raw.githubusercontent.com/Cyberdrop-DL/cyberdrop-dl/refs/heads/main/CHANGELOG.md"
_changelog_content: str = ""


class _ConsoleWrapper:
    def __init__(self, console: Console | None = None) -> None:
        self.console: Console = console or Console()

    def info(self, *objects: object) -> None:
        self.console.print(*objects)

    def warning(self, *objects: object) -> None:
        self.console.print(_WARNING, *objects)

    def error(self, *objects: object) -> None:
        self.console.print(_ERROR, *objects)

    def rule(self, color: str = "blue") -> None:
        self.console.rule(style=color)

    def line(self, count: int = 1) -> None:
        self.console.line(count)

    def input(self, msg: str = "") -> None:
        self.console.input(msg)

    def clear(self) -> None:
        _ = os.system("cls" if os.name == "nt" else "clear")  # noqa: S605


_console = _ConsoleWrapper()


def _changelog() -> str:
    global _changelog_content  # noqa: PLW0603
    if not _changelog_content:
        _changelog_content = aio.run(_fetch_changelog())

    return _changelog_content


def run(manager: Manager) -> None:
    choices: dict[str, Callable[[Manager], bool | None]] = {
        "Download": lambda _: True,
        "Create file hashes": _scan_and_create_hashes,
        "Sort files in download folder": _sort_files,
        "Edit URLs.txt": _edit_urls,
        "Edit config": _edit_config,
        "View changelog": lambda _: _view_changelog(),
        "Exit": lambda _: sys.exit(0),
    }

    while True:
        _app_header(manager)
        answer = _ask_choices(choices)
        done = choices[answer](manager)
        if done:
            break


def _scan_and_create_hashes(manager: Manager) -> None:
    path = _ask_dir(
        "Select the directory to scan",
        default=manager.config.download_folder,
    )
    hasher = Hasher.create(manager.config, manager.database, path)
    hash_stats = aio.run(hash_directory(hasher))
    stats.print(hash_stats)
    _enter_to_continue()


def _sort_files(manager: Manager) -> None:
    sorter = Sorter.from_manager(manager)
    _console.warning(
        f"You are about to sort files from '{sorter.input_dir}' to '{sorter.output_dir}'",
    )
    if _ask_confirmation(explicit=True):
        aio.run(sorter.run())
        _enter_to_continue()


def _should_create_config(file: Path) -> bool:
    _console.warning("A default config file does not exists")
    return _ask_confirmation(f"Do you want to create it at '{file}'?")


def _edit_config(manager: Manager) -> None:
    file = manager.config.source
    if file is None:
        file = manager.appdata.config_file
        if not _should_create_config(file):
            return
        type(manager.config)().save_to(file)

    try:
        text_editor.open(file)
    except ValueError as e:
        _console.error(str(e))
    else:
        _console.warning("You must restart cyberdrop-dl for config changes to take effect")
    finally:
        _enter_to_continue()


def _edit_urls(manager: Manager) -> None:
    try:
        text_editor.open(manager.input_file)
    except ValueError as e:
        _console.error(str(e))

    _enter_to_continue()


async def _fetch_changelog() -> str:
    async with aiohttp.request(
        "GET",
        _CHANGELOG_URL,
        raise_for_status=True,
    ) as response:
        return await response.text()


def _view_changelog() -> None:
    _console.clear()
    try:
        content = _changelog()
    except Exception as e:  # noqa: BLE001
        _console.error("UNABLE TO GET CHANGELOG INFORMATION", repr(e))
        _enter_to_continue()
        return

    with _console.console.pager(links=True):
        _console.info(Markdown(content, justify="left"))


def _app_header(manager: Manager) -> None:
    _console.clear()
    _console.info(f"[bold]cyberdrop-dl ([blue]v{__version__!s}[/blue])[/bold]")
    _console.rule()
    paths = {
        "Config file": manager.config.source,
        "Database file": manager.appdata.db_file,
        "URLs file": manager.input_file,
        "Cache file": manager.appdata.cache_file,
        "Logs": manager.config.logs.effective_log_folder,
        "Main log file": manager.config.logs.files.main,
    }
    padding = max(map(len, paths))
    for name, file in paths.items():
        _console.info(f"{name:<{padding}} :", hyperlink(file) if file else None)

    _console.line()


def _ask_choices[T](choices: Iterable[T]) -> T:
    return _ask(  # pyright: ignore[reportAny]
        inquirer.List(
            "main",
            message="What would you like to do",
            choices=list(choices),
        )
    )


def _ask(question: inquirer.questions.Question) -> Any:
    answers = inquirer.prompt(
        [question],
        raise_keyboard_interrupt=True,
        theme=BlueComposure(),
    )
    assert answers
    return next(iter(answers.values()))


def _ask_text(text: str) -> str:
    return _ask(inquirer.Text("text", message=text))


def _ask_confirmation(text: str = "", *, explicit: bool = False) -> bool:
    if explicit:
        msg = "Type 'YES' to proceed"
        answer = _ask_text(f"{text}. {msg}" if text else msg)
        return answer.strip().casefold() == "yes"
    return _ask(inquirer.Confirm("text", message=text))


def _ask_dir(message: str = "Select dir path", default: Path | None = None) -> Path:

    def is_dir(path: Path) -> None:
        if not path.is_dir():
            raise NotADirectoryError(str(path))

    return _ask_path(message, default, validate=is_dir)


def _ask_file(message: str = "Select file", default: Path | None = None) -> Path:

    def is_file(path: Path) -> None:
        if not path.is_file():
            raise IsADirectoryError(str(path))

    return _ask_path(message, default, validate=is_file)


def _ask_path(
    message: str = "Select path",
    default: Path | None = None,
    *,
    validate: Callable[[Path], None] | None = None,
    must_exists: bool = True,
) -> Path:
    while True:
        try:
            answer = _ask(
                inquirer.Text(
                    "path",
                    message=message,
                    default=default or Path.home(),
                )
            )

            path = Path(answer).expanduser()
            if must_exists and not path.exists():
                raise FileNotFoundError(answer)
            if validate:
                validate(path)

        except OSError as e:
            _console.error(repr(e))
        else:
            return path.resolve()


def _enter_to_continue() -> None:
    if "pytest" in sys.modules:
        return
    _console.rule()
    _console.input("Press <ENTER> to continue")
