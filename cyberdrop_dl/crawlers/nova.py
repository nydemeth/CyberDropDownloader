"""https://pixeldrain.com/api"""

from __future__ import annotations

import asyncio
import dataclasses
from typing import TYPE_CHECKING, Any, ClassVar, Literal, final, override

from cyberdrop_dl.clients.http import HTTPConfig
from cyberdrop_dl.crawlers.crawler import API, Crawler, DownloadConfig, SupportedPaths, auto_task_id
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.models import type_adapter
from cyberdrop_dl.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils import basic_auth
from cyberdrop_dl.utils.errors import error_handling_wrapper

if TYPE_CHECKING:
    from cyberdrop_dl.clients.response import AbstractResponse
    from cyberdrop_dl.url_objects import ScrapeItem


_PRIMARY_URL = AbsoluteHttpURL("https://nova.storage")


@final
@dataclasses.dataclass(slots=True)
class Node:
    type: Literal["file", "dir"]
    path: str
    name: str
    modified: str
    sha256_sum: str
    id: str | None = None
    file_type: str | None = None

    @property
    def dl_url(self) -> AbsoluteHttpURL:
        return (_PRIMARY_URL / "api/filesystem" / self.path.removeprefix("/")).with_query("attach")


@dataclasses.dataclass(slots=True)
class FileSystem:
    children: list[Node]
    base_index: int
    path: list[Node]


@HTTPConfig(rate_limit=(10, 1))
@DownloadConfig(slots=2)
class NovaStorageCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Filesystem": (
            "/d/<id>",
            "/api/filesystem/<path>...",
        ),
        "**NOTE**": "text files will not be downloaded but their content will be parsed for URLs",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = _PRIMARY_URL
    DOMAIN: ClassVar[str] = "nova.storage"
    FOLDER_DOMAIN: ClassVar[str] = "Nova"

    def __post_init__(self) -> None:
        self.api: NovaAPI = NovaAPI.from_crawler(self)
        if self.api.logged_in:
            self.downloader.slots = None

    @override
    def __json_resp_check__(self, json_resp: dict[str, Any], resp: AbstractResponse[Any]) -> None:
        if not json_resp["success"]:
            msg = f"{json_resp['message']} ({json_resp['value']})"
            raise ScrapeError(resp.status, msg)

    @override
    def _prepare_headers(self, scrape_item: ScrapeItem) -> dict[str, str]:
        return super()._prepare_headers(scrape_item) | self.api.headers

    @override
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if self.origin.host != self.PRIMARY_URL.host:
            raise ValueError
        match scrape_item.url.parts[1:]:
            case ["d", *path] if path:
                return await self.filesystem(scrape_item, "/".join(path))
            case _:
                raise ValueError

    @classmethod
    @override
    def transform_url(cls, url: AbsoluteHttpURL) -> AbsoluteHttpURL:
        url = super().transform_url(url)
        match url.parts[1:]:
            case ["api", "filesystem", *rest] if rest:
                return (url.origin() / "d").joinpath(*rest)
            case _:
                return url

    @error_handling_wrapper
    async def filesystem(self, scrape_item: ScrapeItem, path: str) -> None:
        # https://github.com/Fornaxian/pixeldrain_web/blob/8e5ecfc5ce44c0b2b4fafdf9e8201dfc98395e88/svelte/src/filesystem/FilesystemAPI.ts
        fs = await self.api.filesystem(path)
        base_node = fs.path[fs.base_index]
        root = fs.path[0]
        assert root.id
        title = self.create_title(root.name, root.id)
        scrape_item.setup_as_album(title, album_id=root.id)

        if base_node.type == "file":
            fs.children = [base_node]

        await self._filesystem(scrape_item, fs)

    async def _filesystem(self, scrape_item: ScrapeItem, fs: FileSystem) -> None:
        assert scrape_item.album_id
        results = await self.get_album_results(scrape_item.album_id)

        async def subfolder(new_item: ScrapeItem, path: str) -> None:
            with self.catch_errors(new_item):
                fs = await self.api.filesystem(path)
                scrape_item.add_children(0)
                walk_filesystem(fs)

        def walk_filesystem(fs: FileSystem) -> None:
            for node in fs.children:
                if node.name == ".search_index.gz":
                    continue

                url = self.origin / "d" / node.path.removeprefix("/")
                new_scrape_item = scrape_item.create_child(url)

                if node.type == "file":
                    if self.check_album_results(node.dl_url, results):
                        continue

                    subfolders = node.path.split("/")[2:-1]
                    new_scrape_item.append_folders(*subfolders)
                    tg.create_task(self._file(new_scrape_item, node))

                elif node.type == "dir":
                    tg.create_task(subfolder(new_scrape_item, node.path))

                else:
                    self.raise_exc(new_scrape_item, f"Unknown node type: {node.type}")

                scrape_item.add_children()

        async with asyncio.TaskGroup() as tg:
            walk_filesystem(fs)

    @auto_task_id
    @error_handling_wrapper
    async def _file(self, scrape_item: ScrapeItem, file: Node) -> None:
        src = file.dl_url
        if file.file_type and "text/plain" in file.file_type:
            scrape_item.setup_as_album(self.create_title(file.name, file.id))
            text = await self.api.text(src)
            return self._text(scrape_item, text)

        if await self.check_complete_by_hash(src, "sha256", file.sha256_sum):
            return None

        filename, ext = self.get_filename_and_ext(file.name, mime_type=file.file_type)
        scrape_item.uploaded_at = self.parse_iso_date(file.modified)
        await self.handle_file(src, scrape_item, file.name, ext, custom_filename=filename)

    def _text(self, scrape_item: ScrapeItem, text: str) -> None:
        for line in text.splitlines():
            try:
                link = self.parse_url(line)
            except Exception:  # noqa: BLE001, S112
                continue
            new_item = scrape_item.create_child(link)
            self.handle_external_links(new_item)
            scrape_item.add_children()


class NovaAPI(API):
    def __post_init__(self) -> None:
        self.headers: dict[str, str] = {}
        if api_key := self.config.auth.nova.api_key:
            self.headers["Authorization"] = basic_auth("Cyberdrop-DL", api_key)

    @property
    def logged_in(self) -> bool:
        return bool(self.headers)

    async def filesystem(self, path: str) -> FileSystem:
        api_url = (self.PRIMARY_URL / "api/filesystem" / path.removeprefix("/")).with_query("stat")
        resp = await self.text(api_url)
        return type_adapter(FileSystem).validate_json(resp)

    async def text(self, api_url: AbsoluteHttpURL) -> str:
        return await self.request_text(api_url, headers=self.headers)
