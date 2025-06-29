from __future__ import annotations

import itertools
from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.types import AbsoluteHttpURL, SupportedPaths
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


DATE_SELECTOR = 'h2[class="font-semibold font-sans text-muted-foreground text-xs"]'
API_ENTRYPOINT = AbsoluteHttpURL("https://api.omegascans.org/chapter/query")
JS_SELECTOR = "script:contains('series_id')"
DATE_JS_SELECTOR = "script:contains('created')"
IMAGE_SELECTOR = "p[class*=flex] img"

PRIMARY_URL = AbsoluteHttpURL("https://omegascans.org")


class OmegaScansCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Chapter": "/series/.../...",
        "Series": "/series/...",
        "Direct links": "",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    DOMAIN: ClassVar[str] = "omegascans"
    FOLDER_DOMAIN: ClassVar[str] = "OmegaScans"

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if "chapter" in scrape_item.url.name:
            return await self.chapter(scrape_item)
        if "series" in scrape_item.url.parts:
            return await self.series(scrape_item)
        await self.handle_direct_link(scrape_item)

    @error_handling_wrapper
    async def series(self, scrape_item: ScrapeItem) -> None:
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.DOMAIN, scrape_item.url)

        series_id = None
        js_script = soup.select_one(JS_SELECTOR)
        if not js_script:
            raise ScrapeError(422, "Unable to parse series_id from html")

        series_id = js_script.get_text().split('series_id\\":')[1].split(",")[0]
        scrape_item.setup_as_album("", album_id=series_id)
        # TODO: Add title
        # title: str = ""
        for page in itertools.count(1):
            api_url = API_ENTRYPOINT.with_query(page=page, perPage=30, series_id=series_id)
            async with self.request_limiter:
                json_resp = await self.client.get_json(self.DOMAIN, api_url)

            for chapter in json_resp["data"]:
                chapter_url = scrape_item.url / chapter["chapter_slug"]
                new_scrape_item = scrape_item.create_child(chapter_url)
                self.manager.task_group.create_task(self.run(new_scrape_item))
                scrape_item.add_children()

            if json_resp["meta"]["current_page"] == json_resp["meta"]["last_page"]:
                break

    @error_handling_wrapper
    async def chapter(self, scrape_item: ScrapeItem) -> None:
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.DOMAIN, scrape_item.url)

        if "This chapter is premium" in soup.get_text():
            raise ScrapeError(401, "This chapter is premium")

        scrape_item.part_of_album = True
        title_parts = soup.select_one("title").get_text().split(" - ")
        series_name, chapter_title = title_parts[:2]
        series_title = self.create_title(series_name)
        scrape_item.add_to_parent_title(series_title)
        scrape_item.add_to_parent_title(chapter_title)

        date_str = soup.select(DATE_SELECTOR)[-1].get_text()
        date = self.parse_date(date_str)
        if not date:
            script = soup.select_one(DATE_JS_SELECTOR)
            date_str = script.get_text().split('created_at\\":\\"')[1].split(".")[0]
            date = self.parse_date(date_str)

        scrape_item.possible_datetime = date
        for attribute in ("src", "data-src"):
            for _, link in self.iter_tags(soup, IMAGE_SELECTOR, attribute):
                filename, ext = self.get_filename_and_ext(link.name)
                await self.handle_file(link, scrape_item, filename, ext)

    @error_handling_wrapper
    async def handle_direct_link(self, scrape_item: ScrapeItem) -> None:
        """Handles a direct link."""
        scrape_item.url = scrape_item.url.with_query(None)
        filename, ext = self.get_filename_and_ext(scrape_item.url.name)
        await self.handle_file(scrape_item.url, scrape_item, filename, ext)
