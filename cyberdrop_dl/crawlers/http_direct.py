from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.constants import FileExt
from cyberdrop_dl.crawlers.crawler import Crawler
from cyberdrop_dl.downloader.http import Downloader
from cyberdrop_dl.exceptions import NoExtensionError
from cyberdrop_dl.filepath import get_filename_and_ext
from cyberdrop_dl.utils.errors import error_handling_wrapper

if TYPE_CHECKING:
    from cyberdrop_dl.url_objects import ScrapeItem


@Crawler.db_path_builder("url")
class DirectHttpFileCrawler(Crawler, is_generic=True):
    DOMAIN: ClassVar[str] = "no_crawler"

    async def __async_post_init__(self) -> None:
        self.downloader = Downloader(self.manager)
        self.downloader.log_prefix = "Download attempt (unsupported domain)"

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        try:
            filename, ext = get_filename_and_ext(scrape_item.url.name)
        except NoExtensionError:
            filename, ext = get_filename_and_ext(scrape_item.url.name, xenforo=True)

        if ext == ".m3u8":
            return await self.m3u8(scrape_item)

        if ext not in FileExt.MEDIA:
            raise ValueError

        scrape_item.append_folders("Loose Files")
        scrape_item.part_of_album = True
        await self.handle_file(
            scrape_item.url,
            scrape_item,
            scrape_item.url.name,
            ext,
            custom_filename=filename,
        )

    @error_handling_wrapper
    async def m3u8(self, scrape_item: ScrapeItem) -> None:
        if await self.check_complete_from_referer(scrape_item.url):
            return

        scrape_item.append_folders("Loose Files")
        scrape_item.part_of_album = True
        url = scrape_item.url
        headers = {"Referer": str(referer)} if (referer := scrape_item.get_referer()) else {}
        m3u8, info = await self.request_m3u8(url, headers=headers)
        name = url.name or url.parent.name
        filename = self.create_custom_filename(
            scrape_item.url.path,
            ext := ".mp4",
            resolution=info and info.resolution,
            video_codec=info and info.codecs.video,
            audio_codec=info and info.codecs.audio,
        )
        await self.handle_file(
            scrape_item.url,
            scrape_item,
            name,
            ext,
            m3u8=m3u8,
            custom_filename=filename,
        )
