from __future__ import annotations

import contextlib
import dataclasses
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

from cyberdrop_dl import aio
from cyberdrop_dl.url_objects import AbsoluteHttpURL, ScrapeItem

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Generator, Iterable


type URLSource = Path | Iterable[AbsoluteHttpURL]
REGEX_LINKS = re.compile(r"(?:http.*?)(?=($|\n|\r\n|\r|\s|\"|\[/URL]|']\[|]\[|\[/img]))")

logger = logging.getLogger(__name__)


@dataclasses.dataclass(slots=True)
class ScrapeSource:
    source: URLSource
    name: str = ""

    def __post_init__(self) -> None:
        if not self.name:
            self.name = str(self.source) if isinstance(self.source, Path) else "--links (CLI args)"

    def _items(self) -> AsyncGenerator[ScrapeItem]:
        if isinstance(self.source, Path):
            return _load_urls_from_file(self.source)

        return _load_cli_links(self.source)

    def items(self) -> contextlib.aclosing[AsyncGenerator[ScrapeItem]]:
        return contextlib.aclosing(self._items())


async def _load_urls_from_file(file: Path) -> AsyncGenerator[ScrapeItem]:
    async for group_name, urls in _parse_input_file_groups(file):
        for url in urls:
            item = ScrapeItem.from_url(url)
            if group_name:
                item.append_folders(group_name)
                item.part_of_album = True
            yield item


async def _parse_input_file_groups(input_file: Path) -> AsyncGenerator[tuple[str, list[AbsoluteHttpURL]]]:
    if not await aio.is_file(input_file):
        yield ("", [])
        return

    block_quote = False
    current_group_name = ""
    async with aio.open(input_file, encoding="utf8") as f:
        async for line in f:
            if line.startswith(("---", "===")):  # New group begins here
                current_group_name = line.replace("---", "").replace("===", "").strip()

            if current_group_name:
                yield (current_group_name, list(_regex_links(line)))
                continue

            block_quote = not block_quote if line == "#\n" else block_quote
            if not block_quote:
                yield ("", list(_regex_links(line)))


async def _load_cli_links(links: Iterable[AbsoluteHttpURL]) -> AsyncGenerator[ScrapeItem]:
    for url in links:
        yield ScrapeItem.from_url(url)


def _regex_links(line: str) -> Generator[AbsoluteHttpURL]:
    """Regex grab the links from the URLs.txt file.

    This allows code blocks or full paragraphs to be copy and pasted into the URLs.txt.
    """

    line = line.strip()
    if line.startswith("#"):
        return

    http_urls = (url.group().replace(".md.", ".") for url in re.finditer(REGEX_LINKS, line))
    for link in http_urls:
        try:
            encoded = "%" in link
            yield AbsoluteHttpURL(link, encoded=encoded)
        except Exception as e:  # noqa: BLE001
            logger.error(f"Unable to parse URL from input file: {link} {e:!r}")
