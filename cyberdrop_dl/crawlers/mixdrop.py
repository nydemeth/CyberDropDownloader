from __future__ import annotations

import asyncio
import dataclasses
from typing import TYPE_CHECKING, ClassVar, override

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedDomains, SupportedPaths
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils import css, js_unpacker
from cyberdrop_dl.utils.errors import error_handling_wrapper

if TYPE_CHECKING:
    from collections.abc import Generator

    from cyberdrop_dl.url_objects import ScrapeItem


class MixDropCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "File": (
            "/e/<file_id>",
            "/f/<file_id>",
        ),
        "**NOTE**": "Only video files are supported",
    }
    SUPPORTED_DOMAINS: ClassVar[SupportedDomains] = "mxdrop", "mixdrop", "m1xdrop", "miixdrop"
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://mixdrop.sb")
    DOMAIN: ClassVar[str] = "mixdrop"
    FOLDER_DOMAIN: ClassVar[str] = "MixDrop"

    @override
    def _prepare_headers(self, scrape_item: ScrapeItem) -> dict[str, str]:
        return super()._prepare_headers(scrape_item) | {"Referer": "https://m1xdrop.click/"}

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case ["f" | "e", file_id]:
                await self.file(scrape_item, file_id)
            case _:
                raise ValueError

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem, file_id: str) -> None:
        embed_url = self.PRIMARY_URL / "e" / file_id
        if await self.check_complete(embed_url):
            return

        file = await self._request_video(file_id)
        _, ext = self.get_filename_and_ext(file.src.name)
        await self.handle_file(
            embed_url,
            scrape_item,
            file.title,
            ext,
            custom_filename=self.create_custom_filename(file.title, ext, file_id=file_id),
            debrid_link=file.src,
            referer=scrape_item.get_referer() or scrape_item.url,
            thumbnail=file.thumb,
        )

    async def _request_video(self, file_id: str) -> File:
        html = await self.request_text(self.origin / "e" / file_id)
        if _is_not_found(html):
            if _is_not_found(await self.request_text(self.origin / "f" / file_id)):
                raise ScrapeError(404)

            raise ScrapeError(422, "Non video files are not supported")

        return await asyncio.to_thread(_parse_video, file_id, html)


@dataclasses.dataclass(slots=True, frozen=True)
class File:
    id: str
    title: str
    src: AbsoluteHttpURL
    thumb: str | None


def _parse_video(video_id: str, html: str) -> File:
    props = dict(_extract_md_core_props(html))
    return File(
        video_id,
        title=css.select_text(css.soup(html), ".title"),
        src=MixDropCrawler.parse_url(props["wurl"]),
        thumb=props.get("poster"),
    )


def _is_not_found(html: str) -> bool:
    return "WE ARE SORRY" in html and any(
        f"find the {media} you are looking for" in html for media in ("video", "file")
    )


def _extract_md_core_props(html: str) -> Generator[tuple[str, str]]:
    content = js_unpacker.unpack(html)
    for line in content.split(";MDCore."):
        name, _, value = line.partition("=")
        yield name.removeprefix("MDCore."), value.strip('"').strip()
