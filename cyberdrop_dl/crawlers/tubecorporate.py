from __future__ import annotations

import base64
import dataclasses
from typing import TYPE_CHECKING, Any, ClassVar, Final

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedDomains, SupportedPaths
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils.errors import error_handling_wrapper

if TYPE_CHECKING:
    from cyberdrop_dl.url_objects import ScrapeItem

_FORMATS: Final = "_sd.mp4", "_hq.mp4", "_hd.mp4", "_fhd.mp4"


@dataclasses.dataclass(slots=True)
class Video:
    title: str
    thumb: AbsoluteHttpURL
    post_date: str
    src: AbsoluteHttpURL


class TubeCorporateCrawler(Crawler, is_abc=True):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Video": (
            "/videos/<video_id>/...",
            "/embed/<video_id>/...",
        )
    }

    def __init_subclass__(cls, **kwargs: Any) -> None:
        domains = cls.PRIMARY_URL.host, *cls.SUPPORTED_DOMAINS
        domains = *domains, *(d.replace(".com", ".tube") for d in domains)
        old_domains = *cls.OLD_DOMAINS, *(d.replace(".com", ".tube") for d in cls.OLD_DOMAINS)
        cls.SUPPORTED_DOMAINS = tuple(sorted(set(domains)))
        cls.OLD_DOMAINS = tuple(sorted(set(old_domains)))
        super().__init_subclass__(**kwargs)

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case ["videos" | "video" | "embed", video_id, *_]:
                await self.video(scrape_item, video_id)
            case _:
                raise ValueError

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem, video_id: str) -> None:
        if await self.check_complete_from_referer(scrape_item.url):
            return None

        video = await self._request_video(scrape_item.url.origin(), video_id)
        scrape_item.uploaded_at = self.parse_iso_date(video.post_date)
        ext = ".mp4"
        custom_filename = self.create_custom_filename(video.title, ext, file_id=video_id)

        return await self.handle_file(
            scrape_item.url,
            scrape_item,
            video.title,
            ext,
            custom_filename=custom_filename,
            debrid_link=video.src,
            metadata=video,
            referer=scrape_item.url.with_host(video.src.host),
        )

    async def _request_video(self, origin: AbsoluteHttpURL, video_id: str) -> Video:
        async with self.request(
            (origin / "api/videofile.php").with_query(
                video_id=video_id,
                lifetime=8_640_000,
            )
        ) as resp:
            origin = resp.url.origin()  # May have been a redirect. We need the real origin as referer
            src = _select_best_src(_parse_formats(await resp.json()))

        mil_index = int(1e6 * (int(video_id) // 1e6))
        k_index = 1_000 * (int(video_id) // 1_000)
        lifetime = 86_400

        info_url = origin / f"api/json/video/{lifetime}/{mil_index}/{k_index}/{video_id}.json"

        video: dict[str, Any] = (await self.request_json(info_url))["video"]

        return Video(
            title=video["title"],
            thumb=self.parse_url(video["thumbsrc"]),
            post_date=video["post_date"],
            src=self.parse_url(src, origin, trim=False),
        )


def _parse_formats(formats: list[dict[str, str]] | dict[str, str]) -> list[dict[str, str]]:
    if isinstance(formats, list):
        return formats

    if formats.get("error"):
        error = formats["msg"]
        if "not_found" in error:
            error = 404
        elif "private" in error:
            error = 403

        raise ScrapeError(error)

    raise ScrapeError(422, f"Expected list response, got {formats = !r}")


def _select_best_src(formats: list[dict[str, str]]) -> str:
    if len(formats) == 1:
        best = formats[0]
    else:
        try:
            best = max(formats, key=lambda f: _FORMATS.index(f["format"]))
        except ValueError:
            unknown = tuple(name for f in formats if (name := f["format"]) not in _FORMATS)
            raise ScrapeError(422, f"Video has unknown formats: {unknown}") from None

    return _decode_url(best["video_url"])


def _decode_url(url: str) -> str:
    return base64.b64decode(
        url.translate(
            str.maketrans(
                {
                    "\u0405": "S",
                    "\u0406": "I",
                    "\u0408": "J",
                    "\u0410": "A",
                    "\u0412": "B",
                    "\u0415": "E",
                    "\u041a": "K",
                    "\u041c": "M",
                    "\u041d": "H",
                    "\u041e": "O",
                    "\u0420": "P",
                    "\u0421": "C",
                    "\u0425": "X",
                    ",": "/",
                    ".": "+",
                    "~": "=",
                }
            )
        )
    ).decode()


class FuXXXCrawler(TubeCorporateCrawler):
    DOMAIN: ClassVar[str] = "fuxxx"
    FOLDER_DOMAIN: ClassVar[str] = "FuXXX"
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://fuxxx.com")


class HClipsCrawler(TubeCorporateCrawler):
    SUPPORTED_DOMAINS: ClassVar[SupportedDomains] = ("privatehomeclips.com",)
    DOMAIN: ClassVar[str] = "hclips"
    FOLDER_DOMAIN: ClassVar[str] = "HClips"
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://hclips.com")


class HDZogCrawler(TubeCorporateCrawler):
    DOMAIN: ClassVar[str] = "hdzog"
    FOLDER_DOMAIN: ClassVar[str] = "HDZog"
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://hdzog.com")


class HotMovsCrawler(TubeCorporateCrawler):
    DOMAIN: ClassVar[str] = "hotmovs"
    FOLDER_DOMAIN: ClassVar[str] = "HotMovs"
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://hotmovs.com")


class InPornCrawler(TubeCorporateCrawler):
    DOMAIN: ClassVar[str] = "inporn"
    FOLDER_DOMAIN: ClassVar[str] = "InPorn"
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://inporn.com")


class TubePornClassicCrawler(TubeCorporateCrawler):
    DOMAIN: ClassVar[str] = "tubepornclassic"
    FOLDER_DOMAIN: ClassVar[str] = "TubePornClassic"
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://tubepornclassic.com")


class TXXXCrawler(TubeCorporateCrawler):
    OLD_DOMAINS: ClassVar[tuple[str, ...]] = ("videotxxx.com",)
    DOMAIN: ClassVar[str] = "txxx"
    FOLDER_DOMAIN: ClassVar[str] = "TXXX"
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://txxx.com")


class UPorniaCrawler(TubeCorporateCrawler):
    DOMAIN: ClassVar[str] = "upornia"
    FOLDER_DOMAIN: ClassVar[str] = "UPornia"
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://upornia.com")


class VJavCrawler(TubeCorporateCrawler):
    DOMAIN: ClassVar[str] = "vjav"
    FOLDER_DOMAIN: ClassVar[str] = "VJav"
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://vjav.com")


class VoyeurHitCrawler(TubeCorporateCrawler):
    DOMAIN: ClassVar[str] = "voyeurhit"
    FOLDER_DOMAIN: ClassVar[str] = "VoyeurHit"
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://voyeurhit.com")


class VXXXCrawler(TubeCorporateCrawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Video": "/video-<video-id>",
    }
    DOMAIN: ClassVar[str] = "vxxx"
    FOLDER_DOMAIN: ClassVar[str] = "VXXX"
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://vxxx.com")

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case [video_path] if video_path.startswith("video-"):
                video_id = video_path.partition("-")[-1]
                await self.video(scrape_item, video_id)
            case _:
                raise ValueError


class XMilfCrawler(TubeCorporateCrawler):
    DOMAIN: ClassVar[str] = "xmilf"
    FOLDER_DOMAIN: ClassVar[str] = "XMilf"
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://xmilf.com")
