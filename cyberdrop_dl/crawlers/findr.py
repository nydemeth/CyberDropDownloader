from __future__ import annotations

import dataclasses
import itertools
from typing import TYPE_CHECKING, Any, ClassVar

from cyberdrop_dl import aio
from cyberdrop_dl.crawlers.crawler import API, Crawler, SupportedPaths
from cyberdrop_dl.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils.dataclass import deserialize
from cyberdrop_dl.utils.errors import error_handling_wrapper

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Mapping

    from cyberdrop_dl.url_objects import ScrapeItem


class FindrCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Album": "/albums/<album_id>",
        "Search albums": (
            "/search?q=<query>",
            "/api/albums/search?q=<query>",
        ),
        "Search files": (
            "/search?q=<query>&view=files",
            "/api/search?q=<query>",
        ),
    }
    DOMAIN: ClassVar[str] = "findr.to"
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://findr.to")

    def __post_init__(self) -> None:
        self.api: FindrAPI = FindrAPI.from_crawler(self)

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        query = scrape_item.url.query
        match scrape_item.url.parts[1:]:
            case ["albums", album_id] | ["api", "albums", album_id]:
                await self.album(scrape_item, album_id)
            case ["search"] if search := query.get("q"):
                if query.get("view") == "files":
                    await self.files(scrape_item, search)
                else:
                    await self.albums(scrape_item, search)
            case ["api", "albums", "search"] if search := query.get("q"):
                await self.albums(scrape_item, search)
            case ["api", "search"] if search := query.get("q"):
                await self.files(scrape_item, search)
            case _:
                raise ValueError

    @error_handling_wrapper
    async def files(self, scrape_item: ScrapeItem, search_query: str) -> None:
        scrape_item.setup_as_profile(self.create_title(f"{search_query} [files]"))
        sleep = aio.periodic_sleep(10)
        async for file in self.api.search_files(scrape_item.url.query):
            self.handle_external_links(scrape_item.create_child(self.parse_url(file.source_link)))
            scrape_item.add_children()
            await sleep()

    @error_handling_wrapper
    async def albums(self, scrape_item: ScrapeItem, search_query: str) -> None:
        scrape_item.setup_as_profile(self.create_title(f"{search_query} [albums]"))
        sleep = aio.periodic_sleep(10)
        async for album in self.api.search_albums(scrape_item.url.query):
            self.handle_external_links(scrape_item.create_child(self.parse_url(album.original_url)))
            scrape_item.add_children()
            await sleep()

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem, album_id: str) -> None:
        scrape_item.setup_as_profile("")
        album = await self.api.album(album_id)

        if album.provider in self.api.COLLECTION_PROVIDERS:
            children = aio.chain(
                self.api.collections(album_id), (f.source_link async for f in self.api.album_files(album_id))
            )
        else:
            children = aio.chain.yield_this(album.original_url)

        async for child in children:
            self.handle_external_links(scrape_item.create_child(self.parse_url(child)))
            scrape_item.add_children()


@dataclasses.dataclass(slots=True, frozen=True)
class File:
    id: int
    filename: int
    file_size_bytes: int
    source_link: str
    created_at: str
    album_name: str | None = None
    album_id: int | None = None


@dataclasses.dataclass(slots=True, frozen=True)
class Album:
    id: int
    name: str
    original_url: str
    file_count: int
    created_at: str
    updated_at: str
    provider: str


class FindrAPI(API):
    ENTRYPOINT: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://findr.to/api")
    COMMON_QUERY_PARAMS: ClassVar[tuple[str, ...]] = "q", "page", "limit", "sort", "mode"
    FILES_QUERY_PARAMS: ClassVar[tuple[str, ...]] = *COMMON_QUERY_PARAMS, "ext"
    COLLECTION_PROVIDERS: ClassVar[tuple[str, ...]] = ("simpcity",)

    async def album(self, album_id: str) -> Album:
        resp = await self.request_json(self.ENTRYPOINT / "albums" / album_id)
        return deserialize(Album, resp)

    async def collections(self, album_id: str) -> AsyncGenerator[AbsoluteHttpURL]:
        soup = await self.request_soup(self.PRIMARY_URL / "albums" / album_id)
        for album in FindrCrawler.iter_urls(soup, "[id^='album-'] a[href^='/albums/']"):
            yield album

    async def album_files(self, album_id: str) -> AsyncGenerator[File]:
        url = (self.ENTRYPOINT / "albums" / album_id).with_query(limit=100)
        for page in itertools.count(1):
            resp = await self.request_json(url.update_query(page=page))
            for file in resp["files"]:
                yield deserialize(File, file)

            if resp["total_pages"] <= page:
                break

    async def search_files(self, query: Mapping[str, str]) -> AsyncGenerator[File]:
        query = _filter_query(
            query,
            self.FILES_QUERY_PARAMS,
            query_map={
                "max_size_bytes": "maxSizeMb",
                "min_size_bytes": "minSizeMb",
                "sort": "fileSort",
            },
        )
        url = (self.ENTRYPOINT / "search").with_query(query)
        async for resp in self.pager(url):
            for file in resp["files"]:
                yield deserialize(File, file)

    async def search_albums(self, query: Mapping[str, str]) -> AsyncGenerator[Album]:
        query = _filter_query(
            query,
            self.COMMON_QUERY_PARAMS,
            query_map={
                "max_files": "maxFiles",
                "min_files": "minFiles",
                "sort": "albumSort",
            },
        )
        url = (self.ENTRYPOINT / "albums/search").with_query(query)
        async for resp in self.pager(url):
            for album in resp["albums"]:
                yield deserialize(Album, album)

    async def pager(self, url: AbsoluteHttpURL) -> AsyncGenerator[dict[str, Any]]:
        page = int(url.query.get("page", 1))
        while True:
            resp = await self.request_json(url)
            yield resp
            if not resp.get("has_more"):
                break
            page += 1
            url = url.update_query(page=page)


def _filter_query(query: Mapping[str, str], keys: tuple[str, ...], query_map: Mapping[str, str]) -> dict[str, str]:
    new_query = {k: value for k in keys if (value := query.get(k))}
    for name, alias in query_map.items():
        if value := query.get(name) or query.get(alias):
            new_query.setdefault(name, value)

    new_query.setdefault("sort", "date_desc")
    new_query.setdefault("limit", "100")
    return new_query
