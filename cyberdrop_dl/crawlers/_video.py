from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler, URLConfig
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.errors import error_handling_wrapper

if TYPE_CHECKING:
    from cyberdrop_dl.url_objects import ScrapeItem


@Crawler.db_path_builder("url")
@URLConfig(trim=False)
class GenericVideoCrawler(Crawler, is_generic=True):
    SUPPORTED_PATHS: ClassVar[dict[str, str | tuple[str, ...]]] = {"Video": "/..."}

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        await self.video(scrape_item)

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        if await self.check_complete_from_referer(scrape_item.url):
            return

        soup = await self.request_soup(scrape_item.url)
        src = self.parse_url(css.select(soup, "video source", "src"))

        _, ext = self.get_filename_and_ext(src.name, assume_ext=".mp4")
        scrape_item.referer = scrape_item.url

        if ext == ".m3u8":
            await self.generic_m3u8(scrape_item, src)
            return

        await self.direct_file(scrape_item, src)
