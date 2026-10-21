from __future__ import annotations

import base64
import dataclasses
import hashlib
import json
from collections import deque
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any, ClassVar, Literal, override

from Crypto.Cipher import AES
from Crypto.Util import Counter

from cyberdrop_dl import aio
from cyberdrop_dl.crawlers.crawler import API, Crawler, SupportedPaths
from cyberdrop_dl.downloader.http import Downloader
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.mediaprops import Codecs
from cyberdrop_dl.url_objects import AbsoluteHttpURL, MediaItem
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.dataclass import deserialize
from cyberdrop_dl.utils.errors import error_handling_wrapper
from cyberdrop_dl.utils.m3u8 import M3U8, Rendition

if TYPE_CHECKING:
    from cyberdrop_dl.url_objects import ScrapeItem

_PT = ContextVar[str]("_PT")
_MEDIA_ID = ContextVar[str]("_MEDIA_ID")
_KEY = ContextVar[bytes]("_KEY")


class UpFileDownloader(Downloader):
    @override
    async def _download_file(self, media_item: MediaItem) -> bool | None:
        downloaded = await super()._download_file(media_item)
        if downloaded:
            key, media_key = _get_keys(media_item.real_url)
            content = await aio.read_bytes(media_item.path)
            await aio.write_bytes(media_item.path, await _decrypt(media_key, content, key))
        return downloaded


def _get_keys(url: AbsoluteHttpURL) -> tuple[bytes, str]:
    key, media_id = _KEY.get(), _MEDIA_ID.get()
    match url.parts[-2:]:
        case [_, "vinit"]:
            media_key = f"init:{media_id}"
        case [_, "img"]:
            media_key = f"img:{media_id}"
        case [_, "thumb"]:
            media_key = f"thumb:{media_id}"
        case ["seg", idx]:
            media_key = f"seg:{media_id}:{idx}"
        case _:
            raise ValueError(f"Unknown media URL {url}")

    UpFileCrawler.get_logger().debug("Decrypting content for file %s, key = %s, media_key = %s", url, key, media_key)
    return key, media_key


@aio.to_thread
def _decrypt(media_key: str, content: bytes, key: bytes) -> bytes:
    hash_bytes = hashlib.sha256(media_key.encode("utf-8")).digest()
    iv = hash_bytes[:8].ljust(16, b"\x00")
    ctr = Counter.new(64, prefix=iv[:8], initial_value=int.from_bytes(iv[8:], "big"))
    return AES.new(key, AES.MODE_CTR, counter=ctr).decrypt(content)


class UpFileCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Share": "/public/<path>...",
        "**NOTES**": "Does NOT support subfolders",
    }
    DOMAIN: ClassVar[str] = "upfile.top"
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://upfile.top")

    def __post_init__(self) -> None:
        self.downloader: UpFileDownloader = self._build_downloader(UpFileDownloader)  # pyright: ignore[reportIncompatibleVariableOverride]
        self.api: UpFileAPI = UpFileAPI.from_crawler(self)

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case ["public", _, *_]:
                await self.share(scrape_item, scrape_item.url.path.removeprefix("/public/"))
            case _:
                raise ValueError

    @error_handling_wrapper
    async def share(self, scrape_item: ScrapeItem, path: str) -> None:
        await self.api.boot(path)
        folder = await self.api.list(path)
        scrape_item.setup_as_album(self.create_title(folder.name, folder.id), album_id=folder.id)
        await self._walk_nodes(scrape_item, folder, path)

    async def _walk_nodes(self, scrape_item: ScrapeItem, folder: Folder, path: str) -> None:
        subfolders: deque[dict[str, Any]] = deque()
        nodes = folder.items

        while True:
            for node in nodes:
                if node["type"] == "folder":
                    self.log.warning("Subfolder ignored: %s", node)
                    subfolders.append(node)
                    continue

                if node["type"] != "file":
                    self.log.warning("Unknown node type: %s", node)
                    continue

                file = File.parse(node, path=path)
                url = scrape_item.url / "m" / file.id
                new_item = scrape_item.create_child(url)
                self.create_eager_task(self._file(new_item, file))
                scrape_item.add_children()

            if not subfolders:
                return

            raise ScrapeError(422, f"Subfolders are not supported:\n {tuple(subfolders)}")
            nodes = (await self.api.list(subfolders.popleft())).items

    @error_handling_wrapper
    async def _file(self, scrape_item: ScrapeItem, file: File) -> None:
        media_url = self.api.ENTRYPOINT / file.path / "m" / file.id
        if await self.check_complete(media_url):
            return

        _MEDIA_ID.set(file.id)
        filename, ext = self.get_filename_and_ext(file.name)
        debrid_url = m3u8 = meta = None
        match file.kind:
            case "video":
                meta = await self.api.video(file.path, file.id)
                m3u8 = Rendition(_create_m3u8(media_url, len(meta.segments), meta.duration), None, None)
            case "image":
                debrid_url = media_url / "img"
            case _:
                raise ScrapeError(422, f"Unsupported file type: {file}")

        await self.handle_file(
            media_url,
            scrape_item,
            file.name,
            ext,
            custom_filename=filename,
            headers=self.api.headers,
            thumbnail=media_url / "thumb" if file.thumb else None,
            debrid_link=debrid_url,
            m3u8=m3u8,
            metadata=meta,
        )

    @override
    def _prepare_media_item(self, media_item: MediaItem) -> None:
        media_item.headers.update(self.api.headers)

    @override
    async def sniff_ext(self, thumbnail: AbsoluteHttpURL, headers: dict[str, str] | None = None) -> str:
        if thumbnail.name == "thumb":
            return ".jpg"
        return await super().sniff_ext(thumbnail, headers)


@dataclasses.dataclass(slots=True, frozen=True)
class File:
    id: str
    path: str
    type: Literal["file"]
    name: str
    thumb: bool
    status: str
    kind: str

    parse = classmethod(deserialize)


@dataclasses.dataclass(slots=True, frozen=True)
class Folder:
    id: str
    name: str
    items: list[dict[str, Any]]
    type: Literal["folder"] = "folder"


@dataclasses.dataclass(slots=True, frozen=True)
class VideoMeta:
    segments: list[int]
    codecs: Codecs
    duration: int
    width: int
    height: int


class UpFileAPI(API):
    ENTRYPOINT: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://upfile.top/api/s")

    @property
    def headers(self) -> dict[str, str]:
        return {"x-pt": _PT.get(), "cache": "no-store"}

    async def boot(self, path: str) -> None:
        url = self.PRIMARY_URL / "public" / path
        html = await self.request_text(url)
        soup = await css.asoup(html, parse_only="script")
        boot = json.loads(css.select_text(soup, "#boot"))
        _PT.set(boot["pt"])
        init = await self.request_json(self.ENTRYPOINT / path / "init", "POST", json={}, headers=self.headers)
        _KEY.set(base64.b64decode(init["key"]))

    async def list(self, path: str) -> Folder:
        url = self.ENTRYPOINT / path / "list"
        data = await self.request_json(url, headers=self.headers)
        return deserialize(Folder, data["folder"], items=data["items"])

    async def video(self, path: str, media_id: str) -> VideoMeta:
        play = self.ENTRYPOINT / path / "play"
        data = await self.request_json(play, "POST", json={"id": media_id}, headers=self.headers)
        return deserialize(VideoMeta, meta := data["meta"], codecs=Codecs.parse(meta["codecs"]))


def _create_m3u8(url: AbsoluteHttpURL, segments: int, duration: int) -> M3U8:
    target_duration = int(duration) + (1 if duration % 1 > 0 else 0)

    def lines():
        yield "#EXTM3U"
        yield f"#EXT-X-TARGETDURATION:{target_duration}"
        yield "#EXT-X-VERSION:3"
        yield "#EXT-X-MEDIA-SEQUENCE:0"
        yield "#EXT-X-PLAYLIST-TYPE:VOD"
        yield f"#EXTINF:{duration:.6f},"
        yield "vinit"

        for idx in range(segments):
            yield f"#EXTINF:{duration:.6f},"
            yield f"seg/{idx}"

        yield "#EXT-X-ENDLIST"

    content = "\n".join(lines())
    return M3U8(content, base_uri=url, media_type="video", source=url)
