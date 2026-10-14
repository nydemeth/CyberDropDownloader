from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, ClassVar, override

from cyberdrop_dl.crawlers.crawler import API, Crawler, SupportedPaths
from cyberdrop_dl.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils import next_js, traversal
from cyberdrop_dl.utils.errors import error_handling_wrapper

if TYPE_CHECKING:
    from cyberdrop_dl.url_objects import ScrapeItem


class TiktikStreamCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Video": (
            "/embed/<video_slug>",
            "/v/<video_slug>",
        ),
    }
    DOMAIN: ClassVar[str] = "tiktikstream"
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://tiktikstream.com")

    @classmethod
    @override
    def transform_url(cls, url: AbsoluteHttpURL) -> AbsoluteHttpURL:
        url = super().transform_url(url).with_query(None)
        match url.parts[1:]:
            case ["embed", video_id]:
                return url.origin() / "v" / video_id
            case _:
                return url

    def __post_init__(self) -> None:
        self.api: TiktikStreamAPI = TiktikStreamAPI.from_crawler(self)

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case ["v", video_slug]:
                await self.video(scrape_item, video_slug)
            case _:
                raise ValueError

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem, slug: str) -> None:
        web_url = self.PRIMARY_URL / "v" / slug
        if await self.check_complete(web_url):
            return

        video = await self.api.video(slug)
        m3u8, info = await self.request_m3u8_playlist(
            video.m3u8,
            headers={"Authorization": f"Bearer {video.token}", "Referer": str(web_url), "Origin": str(self.origin)},
            keep_query=True,
        )
        await self.handle_file(
            web_url,
            scrape_item,
            video.title,
            ext := ".mp4",
            m3u8=m3u8,
            custom_filename=self.create_custom_filename(video.title, ext, file_id=slug, resolution=info.resolution),
            thumbnail=video.thumb,
        )


@dataclasses.dataclass(slots=True, frozen=True)
class Video:
    id: str
    slug: str
    title: str
    token: str
    m3u8: AbsoluteHttpURL
    thumb: AbsoluteHttpURL


class TiktikStreamAPI(API):
    async def video(self, slug: str) -> Video:
        web_url = self.origin / "v" / slug
        soup = await self.request_soup(web_url)
        flight = next_js.extract(soup)
        _, video = traversal.find_obj(flight, "videoId", "title", "suggestions")
        video_uuid = video["videoId"]
        api_url = self.origin / "api/playback/sessions"
        data = await self.request_json(
            api_url,
            "POST",
            headers={"Referer": str(web_url), "Origin": str(self.origin)},
            json={"videoId": video_uuid, "referrer": str(web_url), "embedMode": False},
        )

        return Video(
            id=video_uuid,
            slug=slug,
            title=video["title"],
            token=data["token"],
            m3u8=self.parse_url(data["streamUrl"]),
            thumb=self.origin / "api/videos" / video_uuid / "thumbnail",
        )
