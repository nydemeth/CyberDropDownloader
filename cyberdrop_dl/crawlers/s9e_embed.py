# https://github.com/s9e/TextFormatter/tree/c3ac3530bb59b9589ba56aed87b7c03874598db8/src/Plugins/MediaEmbed/Configurator/sites
from __future__ import annotations

import dataclasses
from collections.abc import Callable
from typing import TYPE_CHECKING, ClassVar

import yarl

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils.errors import error_handling_wrapper

if TYPE_CHECKING:
    from cyberdrop_dl.url_objects import ScrapeItem


type Resolver = Callable[[Embed, str], AbsoluteHttpURL | str]

SITES: dict[str, Embed] = {}


@dataclasses.dataclass(slots=True, frozen=True)
class Embed:
    name: str
    base: str
    url: AbsoluteHttpURL
    resolve: Resolver

    @classmethod
    def register(cls, sites: dict[str, str]) -> Callable[[Resolver], None]:

        def add(fn: Resolver) -> None:
            for name, base in sites.items():
                assert name not in SITES
                SITES[name] = Embed(name, base, AbsoluteHttpURL(base), fn)

        return add


@Embed.register(
    {
        "twitter": "https://twitter.com/user/status/",
        "threads": "https://www.threads.com/t/",
        "sporcle": "https:/www.sporcle.com/framed/?v=8&pm&fid=5cd9d6ae9c70c&gid=",
        "tiktok": "https://www.tiktok.com/@/video/",
        "reddit": "https://embed.reddit.com/r/",
        "imgur": "https://imgur.com/",
        "telegram": "https://t.me/",
        "instagram": "https://www.instagram.com/p/",
    }
)
def frag_tranform(embed: Embed, frag: str) -> str:
    return embed.base + frag


@Embed.register({"twitch": "https://www.twitch.tv"})
def twitch(_embed: Embed, frag: str) -> str:
    params = dict(yarl.query_to_pairs(frag.replace(";", "&")))
    if video_id := params.get("video_id"):
        return f"https://www.twitch.tv/videos/{video_id}"
    clip_id = params["clip_id"]
    if channel := params.get("channel"):
        return f"https://www.twitch.tv/{channel}/clip/{clip_id}"
    return f"https://clips.twitch.tv/{clip_id}"


@Embed.register({"pinterest": "https://www.pinterest.com/"})
def pinterest(embed: Embed, frag: str) -> AbsoluteHttpURL:
    if frag.isdecimal():
        return embed.url / "pin" / frag
    return embed.url / frag


@Embed.register({"bluesky": "https://bsky.app/"})
def bluesky(embed: Embed, frag: str) -> AbsoluteHttpURL:
    if not frag.startswith(pf := "at://"):
        raise ValueError(frag)
    authority, *_, path = frag.removeprefix(pf).split("/")
    return embed.url / "profile" / authority / "post" / path.partition("?")[0]


class S9EXenforoPluginCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Embed": "/iframe/2/<name>.html#<id>",
    }
    DOMAIN: ClassVar[str] = "s9e.github.io"
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://s9e.github.io")

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case ["iframe", "2", name] if scrape_item.url.fragment:
                try:
                    embed = SITES[name.removesuffix(".html").removesuffix(".min")]
                except LookupError:
                    raise ValueError from None
                self.resolve(scrape_item, embed)
            case _:
                raise ValueError

    @error_handling_wrapper
    def resolve(self, scrape_item: ScrapeItem, embed: Embed) -> None:
        url = self.parse_url(embed.resolve(embed, scrape_item.url.fragment))
        self.handle_external_links(scrape_item.create_child(url))
