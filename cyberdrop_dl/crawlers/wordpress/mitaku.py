from __future__ import annotations

from typing import ClassVar, override

from cyberdrop_dl.url_objects import AbsoluteHttpURL, ScrapeItem

from . import WordPressHTMLCrawler


class MitakuCrawler(WordPressHTMLCrawler):
    DOMAIN: ClassVar[str] = "mitaku.net"
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://mitaku.net")
    WP_USE_REGEX: ClassVar[bool] = True
    NEXT_PAGE_SELECTOR: ClassVar[str] = ".wp-pagenavi .current + a[href]"

    @override
    async def fetch(self, scrape_item: ScrapeItem) -> None:  # pyright: ignore[reportIncompatibleMethodOverride]
        match scrape_item.url.parts[1:]:
            case ["ero-cosplay", _]:
                await self.post(scrape_item)
            case _:
                await super().fetch(scrape_item)
