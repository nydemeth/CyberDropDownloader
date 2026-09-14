from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, Any, ClassVar, Final

from cyberdrop_dl.clients.http import HTTPConfig
from cyberdrop_dl.crawlers.crawler import API, Crawler, SupportedPaths
from cyberdrop_dl.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils import dates
from cyberdrop_dl.utils.errors import error_handling_wrapper

if TYPE_CHECKING:
    from cyberdrop_dl.url_objects import ScrapeItem


@HTTPConfig(rate_limit=(4, 1))
class BeegComCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Video": (
            "/<video_id>",
            "/video/<video_id>",
        )
    }
    DOMAIN: ClassVar[str] = "beeg.com"
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://beeg.com")

    def __post_init__(self) -> None:
        self.api: BeegAPI = BeegAPI.from_crawler(self)

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case [video_id]:
                video_id = int(video_id.removeprefix("-"))
                await self.video(scrape_item, video_id)
            case _:
                raise ValueError

    @classmethod
    def transform_url(cls, url: AbsoluteHttpURL) -> AbsoluteHttpURL:
        url = super().transform_url(url)
        match url.parts[1:]:
            case ["video", video_id]:
                return url.origin() / video_id
            case _:
                return url

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem, video_id: int) -> None:
        if await self.check_complete_from_referer(scrape_item.url):
            return

        video = await self.api.video(video_id)
        scrape_item.uploaded_at = video.created_at
        m3u8, info = await self.request_m3u8_playlist(video.m3u8)
        await self.handle_file(
            scrape_item.url,
            scrape_item,
            video.title,
            ext := ".mp4",
            custom_filename=self.create_custom_filename(
                video.title,
                ext,
                file_id=str(video.id),
                resolution=info.resolution,
                video_codec=info.codecs.video,
                audio_codec=info.codecs.audio,
            ),
            m3u8=m3u8,
            thumbnail=video.thumb,
        )


@dataclasses.dataclass(order=True, frozen=True, slots=True)
class Video:
    id: int
    title: str
    created_at: int
    thumb: AbsoluteHttpURL
    m3u8: AbsoluteHttpURL


class BeegAPI(API):
    VIDEO: Final = AbsoluteHttpURL("https://video.beeg.com")
    STORE: Final = AbsoluteHttpURL("https://store.externulls.com")
    THUMBS: Final = AbsoluteHttpURL("https://thumbs.externulls.com")

    async def video(self, video_id: int) -> Video:
        resp: dict[str, Any] = await self.request_json(self.STORE / f"facts/file/{video_id}")
        facts: dict[str, Any] = min(resp["fc_facts"], key=lambda x: int(x["id"]))
        file: dict[str, Any] = resp["file"]
        thumb = next(iter(facts["fc_thumbs"]), 0)

        return Video(
            id=video_id,
            title=next(data for data in file["data"] if data.get("cd_file") == video_id)["cd_value"],
            created_at=int(dates.parse_iso(facts["fc_created"]).timestamp()),
            thumb=self.THUMBS / f"videos/{video_id}/{thumb}.webp",
            m3u8=self.VIDEO / file["hls_resources"]["fl_cdn_multi"],
        )
