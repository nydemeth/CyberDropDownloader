from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl import aio
from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils import css, dates
from cyberdrop_dl.utils.errors import error_handling_wrapper

if TYPE_CHECKING:
    from cyberdrop_dl.url_objects import ScrapeItem


class XMinusCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Track": "/track/<track-id>/<name>",
    }
    DOMAIN: ClassVar[str] = "x-minus"
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://x-minus.pro")
    MEDIA_HOST: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://m4.xmst.cc")

    def request_download(self, track: Track) -> AbsoluteHttpURL:
        return (self.MEDIA_HOST / "dl/minus" / track.id).with_query(
            t668=_compute_token(
                int(track.id),
                track.media_token,
                track.player_token,
            ),
            trackname=track.name,
        )

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case ["track", track_id, *_]:
                await self.track(scrape_item, track_id)
            case _:
                raise ValueError

    @error_handling_wrapper
    async def track(self, scrape_item: ScrapeItem, track_id: str) -> None:
        if await self.check_complete(scrape_item.url):
            return

        track = await _parse_track(await self.request_text(scrape_item.url), track_id)
        scrape_item.uploaded_at = track.uploaded
        name = f"{track.artist} - {track.title}"
        await self.handle_file(
            scrape_item.url,
            scrape_item,
            name,
            ext := ".mp3",
            debrid_link=self.request_download(track),
            custom_filename=self.create_custom_filename(name, ext, file_id=track.id),
            metadata=track,
        )


@dataclasses.dataclass(slots=True, frozen=True, kw_only=True)
class Track:
    id: str
    name: str
    title: str
    artist: str
    uploaded: int
    media_token: str
    player_token: str
    lyrics: str | None = None


@aio.to_thread
def _parse_track(html: str, track_id: str) -> Track:
    soup = css.soup(html)
    uploaded = css.select_text(soup, ".minustrack-info tr:-soup-contains('Uploaded') span:last-child")

    try:
        lyrics = "\n".join(filter(None, css.select_text(soup, "#lyrics-original", strip=False).splitlines()))
    except css.SelectorError:
        lyrics = None

    return Track(
        id=track_id,
        title=css.select(soup, ".list.in-tab.tracklist", "data-tit"),
        name=css.select(soup, ".button.dw-link .no-ajax", "data-fn"),
        artist=css.select_text(soup, ".card-tit.notranslate a"),
        uploaded=int(dates.parse_format(uploaded, "%B %d, %Y").timestamp()),
        lyrics=lyrics,
        media_token=css.select(soup, f"#m{track_id}", "data-k"),
        player_token=css.select(soup, "#player-data", "data-k"),
    )


def _compute_token(track_id: int, media_token: str, player_token: str) -> str:
    # https://x-minus.pro/assets/js/common.v330.min.js, get_url
    a = sum(map(ord, player_token)) + 1_004 + track_id
    c = int((track_id - 150000 + 24235) / 333)
    return f"{a:x}zyxwz{track_id}.9z{media_token}z{c}"
