from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.crawlers.erome import EromeCrawler
from cyberdrop_dl.url_objects import AbsoluteHttpURL

if TYPE_CHECKING:
    from cyberdrop_dl.url_objects import ScrapeItem


class BetteromeCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Album": "/album/<album_id>/...",
        "Profile": "/u/<name>",
        "Search": "/search?q=<query>",
    }
    DOMAIN: ClassVar[str] = "betterome"
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://betterome.com")

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        with scrape_item.track_changes:
            match scrape_item.url.parts[1:]:
                case ["a", album_id, *_]:
                    scrape_item.url = EromeCrawler.PRIMARY_URL / "a" / album_id
                case ["u", user]:
                    scrape_item.url = EromeCrawler.PRIMARY_URL / user
                case ["search"] if scrape_item.url.query.get("q"):
                    scrape_item.url = scrape_item.url.with_host(EromeCrawler.PRIMARY_URL.host)
                case _:
                    raise ValueError

        self.handle_external_links(scrape_item)
