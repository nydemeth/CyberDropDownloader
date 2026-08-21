from __future__ import annotations

import dataclasses
import logging
import os
import shutil
import subprocess
import sys
from typing import TYPE_CHECKING, ClassVar, Protocol

from cyberdrop_dl import env

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG if (env.DEBUG_MODE or env.RUNNING_IN_TERMUX) else logging.ERROR)

_file_browsers: tuple[FileBrowser, ...] | None = None


class FileBrowser(Protocol):
    name: str

    def __call__(self, uri: str) -> bool: ...


def _run_cmd(cmd: tuple[str, ...]) -> bool:
    try:
        with subprocess.Popen(
            cmd,
            close_fds=os.name != "nt",
            start_new_session=True,
            stderr=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
        ) as p:
            try:
                return not p.wait(timeout=8)
            except subprocess.TimeoutExpired:
                return True
    except OSError:
        return False


class WindowsFileBrowser(FileBrowser):
    name: str = "windows-default"

    def __call__(self, uri: str) -> bool:
        try:
            os.startfile(uri)  # noqa: S606
        except OSError:
            return False
        else:
            return True


class SimpleFileBrowser(FileBrowser):
    def __init__(self, exe: str, *args: str, name: str | None = None) -> None:
        self.name: str = name or exe
        self.exe: str = exe
        self.args: tuple[str, ...] = args

    def __repr__(self) -> str:
        return f"<{type(self).__name__}(name={self.name!r})>"

    def __call__(self, uri: str) -> bool:
        cmd = self.exe, *self.args, uri
        return _run_cmd(cmd)


if env.RUNNING_IN_TERMUX:

    class AndroidActivityManager(SimpleFileBrowser):
        USER_ID: ClassVar[str] = env.TERMUX.get("USER_ID", "0")

        def __init__(self, package: str, activity: str) -> None:
            self.name: str = package
            self.package: str = package
            self.activity: str = activity
            super().__init__(
                "am",
                "start",
                "--user",
                self.USER_ID,
                "-a",
                "android.intent.action.VIEW",
                "-n",
                f"{package}/{activity}",
                "-d",
                name=package,
            )

        def __repr__(self) -> str:
            return f"{type(self).__name__}(package={self.package!r}, activity={self.activity!r})"

    @dataclasses.dataclass(slots=True, frozen=True, order=True, kw_only=True)
    class AndroidFileManager:
        name: str
        package: str
        activity: str
        url: str
        skip: str | bool = False

    # Ordered by preference
    ANDROID_FILE_MANAGERS = (
        AndroidFileManager(
            name="Documents UI (AOSP built-in file browser)",  # Android 10+
            package="com.google.android.documentsui",
            activity="com.android.documentsui.DocumentsActivity",
            url="https://source.android.com/docs/core/ota/modular-system/documentsui",
            skip="Can't take custom URI, always opens at /downloads",
        ),
        AndroidFileManager(
            name="Solid Explorer",
            package="pl.solidexplorer2",
            activity="pl.solidexplorer.SolidExplorer",
            url="https://play.google.com/store/apps/details?id=pl.solidexplorer2",
        ),
        AndroidFileManager(
            name="Mixplorer",
            package="com.mixplorer",
            activity="com.mixplorer.activities.BrowseActivity",
            url="https://xdaforums.com/t/app-2-3-mixplorer-v6-x-released-fully-featured-file-manager.1523691/",
        ),
        AndroidFileManager(
            name="Mixplorer Silver",
            package="com.mixplorer.silver",
            activity="com.mixplorer.activities.BrowseActivity",
            url="https://play.google.com/store/apps/details?id=com.mixplorer.silver",
        ),
        AndroidFileManager(
            name="Samsung MyFiles",
            package="com.sec.android.app.myfiles",
            activity="com.sec.android.app.myfiles.ui.MultiInstanceLaunchActivity",
            url="https://play.google.com/store/apps/details?id=com.sec.android.app.myfiles",
        ),
    )


def _get_file_browsers() -> Generator[FileBrowser]:
    if sys.platform == "darwin":
        yield SimpleFileBrowser("open", "-n", name="macos-default")
        return

    if os.name == "nt":
        yield WindowsFileBrowser()
        return

    if env.RUNNING_IN_TERMUX:
        for file_manager in ANDROID_FILE_MANAGERS:
            if not file_manager.skip:
                yield AndroidActivityManager(file_manager.package, file_manager.activity)

        yield SimpleFileBrowser("termux-open")
        return

    if not logger.isEnabledFor(logging.INFO):
        logger.setLevel(logging.INFO)

    if shutil.which("xdg-open"):
        from cyberdrop_dl.utils.text_editor import xdg_query_default

        try:
            name = xdg_query_default("inode/directory").removesuffix(".desktop")
        except Exception:  # noqa: BLE001
            name = None
        yield SimpleFileBrowser("xdg-open", name=name)

    if shutil.which("gio"):
        yield SimpleFileBrowser("gio", "open", "--")


def get_file_browsers() -> tuple[FileBrowser, ...]:
    global _file_browsers  # noqa: PLW0603
    if _file_browsers is None:
        _file_browsers = tuple(_get_file_browsers())
    return _file_browsers


def open_folder(path: Path) -> bool:
    assert path.is_absolute()
    assert path.is_dir()

    file_browsers = get_file_browsers()
    if not file_browsers:
        logger.error("Unable to find any file browser on the system")
        return False

    logger.debug(
        "Opening '%s'. File browsers to try (%s): \n- %s",
        path,
        len(file_browsers),
        "\n- ".join(f.name for f in file_browsers),
    )

    uri = path.as_uri()
    for browser in file_browsers:
        if browser(uri):
            logger.info("Opened '%s' with '%s'", path, browser.name)
            return True

    logger.error("Unable to open '%s' with any file browser", path)
    return False
