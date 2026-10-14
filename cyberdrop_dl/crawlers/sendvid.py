from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, final

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.errors import error_handling_wrapper

if TYPE_CHECKING:
    from cyberdrop_dl.url_objects import ScrapeItem


@final
class Selector:
    VIDEO = "#video_container"
    VIDEO_SRC = "video > source#video_source"
    TITLE = "p.video-title"


class SendVidCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Videos": "/<video_id>",
        "Embeds": "/embed/<video_id>",
        "Direct links": "https://videos<x>.sendvid.com/...",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://sendvid.com")
    DOMAIN: ClassVar[str] = "sendvid"
    FOLDER_DOMAIN: ClassVar[str] = "SendVid"

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case [video_id]:
                await self.video(scrape_item, video_id)
            case _:
                raise ValueError

    @classmethod
    def transform_url(cls, url: AbsoluteHttpURL) -> AbsoluteHttpURL:
        url = super().transform_url(url)
        match url.parts[1:]:
            case ["embed", video_id]:
                return url.origin() / video_id
            case [_, *_] if cls.is_subdomain(url):
                video_id = url.name.split(".", 1)[0]
                return cls.PRIMARY_URL / video_id
            case _:
                return url

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem, video_id: str) -> None:
        if await self.check_complete_from_referer(scrape_item.url):
            return

        soup = await self.request_soup(scrape_item.url)
        video = css.select(soup, Selector.VIDEO)
        title = css.select_text(soup, Selector.TITLE)
        src = self.parse_url(css.select(video, Selector.VIDEO_SRC, "src"))

        if not all(map(src.query.get, required := ("validfrom", "validto", "rate", "hash"))):
            msg = f"URL {src} is missing some of the required parameters: {required}"
            raise ScrapeError(401, msg)

        filename, ext = self.get_filename_and_ext(src.name)
        await self.handle_file(
            src.with_query(None),
            scrape_item,
            src.name,
            ext,
            debrid_link=src,
            custom_filename=self.create_custom_filename(title or filename, ext, file_id=video_id),
            thumbnail=css.attr(video, "poster"),
        )
