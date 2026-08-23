from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, override

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils import css, open_graph
from cyberdrop_dl.utils.errors import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.url_objects import ScrapeItem


class WebmShareCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Video": (
            "/<video_id>",
            "/play/<video_id>",
            "/download-webm/<video_id>",
        ),
        "Search": "/results?q=<query>",
    }

    DOMAIN: ClassVar[str] = "webmshare"
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://webmshare.com")

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case ["results"]:
                query = scrape_item.url.query.get("q")
                if not query:
                    raise ValueError
                await self.search(scrape_item, query)
            case [video_id] if "." not in video_id:
                await self.video(scrape_item, video_id)
            case _:
                raise ValueError

    @classmethod
    @override
    def transform_url(cls, url: AbsoluteHttpURL) -> AbsoluteHttpURL:
        url = super().transform_url(url)
        match url.parts[1:]:
            case ["play" | "download-webm", video_id]:
                return url.origin() / video_id
            case _:
                return url

    async def request_soup_w_form(self, url: AbsoluteHttpURL) -> BeautifulSoup:
        soup = await self.request_soup(url)
        try:
            form = css.parse_form(css.select(soup, "form#is_adult"))
        except css.SelectorError:
            return soup
        return await self.request_soup(self.parse_url(form.action), method=form.method, data=form.inputs)

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem, video_id: str) -> None:
        if await self.check_complete_from_referer(scrape_item.url):
            return

        soup = await self.request_soup_w_form(scrape_item.url)
        title = css.select_text(soup, "h1") or video_id
        added = css.select_text(soup, "span > small:-soup-contains-own(Added)").partition(" ")[-1]
        scrape_item.uploaded_at = self.parse_date(added, "%B %d, %Y")
        src = self.parse_url(open_graph.video(soup))
        _, ext = self.get_filename_and_ext(src.name)

        await self.handle_file(
            src,
            scrape_item,
            title,
            ext,
            custom_filename=self.create_custom_filename(title, ext, file_id=video_id),
            debrid_link=src,
            thumbnail=open_graph.get_image(soup),
        )

    @error_handling_wrapper
    async def search(self, scrape_item: ScrapeItem, query: str) -> None:
        scrape_item.setup_as_profile(self.create_title(f"{query} [search]"))
        if not self.cookies.get("is_adult"):
            async with self._startup_lock:
                if not self.cookies.get("is_adult"):
                    _ = await self.request_soup_w_form(self.PRIMARY_URL / "jRjR8")

        soup = await self.request_soup(scrape_item.url)
        for new_item in self.iter_children(scrape_item, soup, ".container a[href^='/']"):
            self.create_task(self.run(new_item))
