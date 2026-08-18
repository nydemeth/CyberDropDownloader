from __future__ import annotations

import asyncio
import contextlib
import dataclasses
from typing import TYPE_CHECKING, Self

from myjdapi import myjdapi

from cyberdrop_dl.exceptions import JDownloaderError

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

    from myjdapi.myjdapi import Jddevice

    from cyberdrop_dl.config import Config
    from cyberdrop_dl.url_objects import AbsoluteHttpURL


@dataclasses.dataclass(frozen=True, slots=True)
class JDDeprecatedAPI:
    host: str = ""
    port: int = 3128


@dataclasses.dataclass(frozen=True, slots=True)
class JDConfig:
    enabled: bool
    username: str | None
    password: str | None
    device: str | None
    download_dir: Path
    autostart: bool
    whitelist: tuple[str, ...]
    deprecated_api: JDDeprecatedAPI | None = None


@dataclasses.dataclass(slots=True)
class JDownloader:
    """Class that handles connecting and sending links to JDownloader."""

    config: JDConfig
    _enabled: bool = dataclasses.field(init=False)
    _device: Jddevice | None = dataclasses.field(default=None, init=False)

    @classmethod
    def from_config(cls, config: Config, /) -> Self:
        download_dir = config.jdownloader.download_folder or config.download_folder
        d_conf = (
            JDDeprecatedAPI(
                host=d_url.host,
                port=d_url.explicit_port or 3128,
            )
            if (d_url := config.jdownloader.deprecated_api)
            else None
        )

        return cls(
            JDConfig(
                enabled=config.jdownloader.enabled,
                device=config.auth.jdownloader.device,
                username=config.auth.jdownloader.username,
                password=config.auth.jdownloader.password,
                download_dir=download_dir.resolve(),
                autostart=config.jdownloader.autostart,
                whitelist=tuple(config.jdownloader.whitelist),
                deprecated_api=d_conf,
            )
        )

    @property
    def enabled(self) -> bool:
        return self._enabled

    def __post_init__(self) -> None:
        self._enabled = self.config.enabled

    def is_enabled_for(self, url: AbsoluteHttpURL) -> bool:
        if not self.enabled:
            return False
        if not self.config.whitelist:
            return True

        return any(domain in url.host for domain in self.config.whitelist)

    @contextlib.contextmanager
    def _wrap_errors(self) -> Generator[None]:
        try:
            yield
        except myjdapi.MYJDDeviceNotFoundException:
            raise JDownloaderError(f"Device not found ({self.config.device})") from None
        except myjdapi.MYJDApiException as e:
            raise JDownloaderError(str(e)) from e

    async def _connect(self) -> None:
        if not self._enabled or self._device is not None:
            return

        with self._wrap_errors():
            api = myjdapi.Myjdapi()
            api.set_app_key("CYBERDROP-DL")
            self._device = await _get_device(api, self.config)

    async def connect(self) -> None:
        try:
            return await self._connect()
        except Exception:
            self._enabled = False
            raise

    async def send(self, url: AbsoluteHttpURL, title: str, download_path: Path | None = None) -> None:
        """Sends links to JDownloader."""

        assert self._device is not None
        assert self.enabled
        with self._wrap_errors():
            download_folder = self.config.download_dir
            if download_path:
                download_folder /= download_path

            await asyncio.to_thread(
                self._device.linkgrabber.add_links,
                [
                    {
                        "autostart": self.config.autostart,
                        "links": str(url),
                        "packageName": title or "Cyberdrop-DL",
                        "destinationFolder": str(download_folder),
                        "overwritePackagizerRules": True,
                    },
                ],
            )


async def _get_device(api: myjdapi.Myjdapi, config: JDConfig):
    if config.deprecated_api:
        await asyncio.to_thread(api.direct_connect, config.deprecated_api.host, config.deprecated_api.port)
        return api.get_device()

    if config.username and config.password and config.device:
        await asyncio.to_thread(api.connect, config.username, config.password)
        return api.get_device(config.device)

    raise JDownloaderError("JDownloader credentials were not provided")
