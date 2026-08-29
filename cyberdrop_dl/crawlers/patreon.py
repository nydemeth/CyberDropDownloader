from __future__ import annotations

import contextlib
import dataclasses
import json
from typing import TYPE_CHECKING, Any, ClassVar, NotRequired, TypedDict, cast

from typing_extensions import ReadOnly

from cyberdrop_dl.clients.http import HTTPConfig
from cyberdrop_dl.crawlers.crawler import API, Crawler, SupportedPaths
from cyberdrop_dl.exceptions import NoExtensionError, ScrapeError
from cyberdrop_dl.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils import css, extr_text, next_js
from cyberdrop_dl.utils.dataclass import DictDataclass
from cyberdrop_dl.utils.errors import error_handling_wrapper

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Generator, Iterable

    from bs4 import BeautifulSoup

    from cyberdrop_dl.url_objects import ScrapeItem


@dataclasses.dataclass(frozen=True, slots=True, order=True)
class Media:
    id: str
    name: str | None
    url: AbsoluteHttpURL
    attributes: dict[str, Any]
    hash: str | None = None

    __iter__ = DictDataclass.__iter__

    def __json__(self) -> dict[str, Any]:
        me = dict(self)
        del me["attributes"]
        me["url"] = str(self.url)
        return me

    def __post_init__(self) -> None:
        if not self.hash:
            object.__setattr__(self, "hash", _md5_from_url(self.url))


class Asset(TypedDict):
    id: str
    type: str
    attributes: ReadOnly[NotRequired[dict[str, Any]]]
    relationships: ReadOnly[NotRequired[dict[str, Any]]]


class Included(Asset):
    attributes: dict[str, Any]


class Post(Included):
    relationships: dict[str, Any]

    current_user_can_view: bool
    campaign_id: str
    published_at: str
    title: str
    url: str


class PatreonCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Post": (
            "/posts/<slug>-<post-id>",
            "/<creator>/posts/<slug>-<post-id>",
        ),
        "Creator": (
            "/<creator>",
            "/cw/<creator>",
        ),
    }

    DOMAIN: ClassVar[str] = "patreon"
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://www.patreon.com")
    DEFAULT_POST_TITLE_FORMAT: ClassVar[str] = "{date:%Y-%m-%d} - {title}"

    def __post_init__(self) -> None:
        self.api: PatreonV1API = PatreonV1API.from_crawler(self)

    @property
    def separate_posts(self) -> bool:
        return True

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case ["posts", slug] | [_, "posts", slug]:
                post_id = slug.rpartition("-")[-1]
                await self.post(scrape_item, post_id)
            case [creator] | ["cw", creator]:
                await self.creator(scrape_item, creator)
            case _:
                raise ValueError

    @error_handling_wrapper
    async def post(self, scrape_item: ScrapeItem, post_id: str) -> None:
        post = await self.api.post(post_id)
        self._post(
            scrape_item,
            post=_flatten_post(post["data"]),
            included=_flatten_included(post["included"]),
        )

    @error_handling_wrapper
    def _post(self, scrape_item: ScrapeItem, post: Post, included: dict[str, Included]) -> None:
        if not post["current_user_can_view"]:
            raise ScrapeError(402, "You do not have access to this post")

        campaign_name: str = included[post["campaign_id"]]["attributes"]["name"]
        title = self.create_title(campaign_name)
        scrape_item.setup_as_album(title)

        scrape_item.uploaded_at = date = self.parse_iso_date(post["published_at"])
        post_title = self.create_separate_post_title(post["title"], post["id"], date)
        scrape_item.append_folders(post_title)

        self.create_eager_task(self.write_metadata(scrape_item, f"post_{post['id']}", post))

        medias = tuple(_parse_media(post, included))
        unique_medias = tuple(_unique_media(medias))
        self.log.debug(
            "Found %s media assets in post %s (%s unique)\n%s",
            len(medias),
            post["id"],
            len(unique_medias),
            LazyLogMedia(medias),
        )

        for media in unique_medias:
            self.create_task(self._media(scrape_item, media))
            self.create_eager_task(self.write_metadata(scrape_item, f"media_{media.id}", media))
            scrape_item.add_children()

        if embed := post.get("embed"):
            self.log.debug("Found embed in post %s: %s", post["id"], embed)
            new_item = scrape_item.create_child(self.parse_url(embed["url"]))
            self.handle_embed(new_item)
            self.create_eager_task(self.write_metadata(scrape_item, f"embed_{post['id']}", embed))
            scrape_item.add_children()

    @error_handling_wrapper
    async def _media(self, scrape_item: ScrapeItem, media: Media) -> None:
        if media.url.suffix == ".m3u8":
            return await self._m3u8_media(scrape_item, media)

        name = media.name
        if not name:
            async with self.request(media.url) as resp:
                try:
                    name = resp.content_disposition.filename
                except ScrapeError:
                    name = media.url.name or media.url.parent.name

        try:
            filename, ext = self.get_filename_and_ext(name)
        except NoExtensionError:
            name = media.url.name
            filename, ext = self.get_filename_and_ext(name)

        await self.handle_file(
            media.url,
            scrape_item,
            name,
            ext,
            custom_filename=self.create_custom_filename(filename, ext, file_id=media.id),
        )

    async def _m3u8_media(self, scrape_item: ScrapeItem, media: Media) -> None:
        m3u8, info = await self.request_m3u8_playlist(media.url)
        filename = self.create_custom_filename(
            media.hash or media.url.name.removesuffix(".m3u8"),
            ext := ".mp4",
            file_id=media.id,
            resolution=info.resolution,
            video_codec=info.codecs.video,
            audio_codec=info.codecs.audio,
        )
        await self.handle_file(media.url, scrape_item, filename, ext, m3u8=m3u8)

    @error_handling_wrapper
    async def creator(self, scrape_item: ScrapeItem, creator: str) -> None:
        campaign_id = await self.api.campaign_id(creator)
        await self.campaign(scrape_item, campaign_id)

    @error_handling_wrapper
    async def campaign(self, scrape_item: ScrapeItem, campaign_id: str) -> None:
        scrape_item.setup_as_profile("")
        async for resp in self.api.posts(campaign_id):
            included = _flatten_included(resp["included"])
            for post in resp["data"]:
                post = _flatten_post(post)
                new_item = scrape_item.create_child(self.parse_url(post["url"]))
                self._post(new_item, post, included)
                scrape_item.add_children()


class LazyLogMedia:
    def __init__(self, media: tuple[Media, ...]) -> None:
        self.media: tuple[Media, ...] = media

    def __json__(self) -> dict[str, dict[str, Any]]:
        return {m.id: m.__json__() for m in self.media}

    def __str__(self):
        return str(self.__json__())


@HTTPConfig(impersonate=True)
class PatreonV1API(API):
    # Public API v1 is retiring on October 7, 2026.
    # https://docs.patreon.com/#apiv2-resource-endpoints
    ENTRYPOINT: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://www.patreon.com/api")

    async def post(self, post_id: str) -> dict[str, Any]:
        url = (self.ENTRYPOINT / "posts" / post_id).with_query(_API_PARAMS)
        return await self.request_json(url)

    async def campaign_id(self, creator: str) -> str:
        async with self.request(self.PRIMARY_URL / creator, impersonate=True) as resp:
            soup = await resp.soup()
            with contextlib.suppress(css.SelectorError):
                bootstrap = _extract_bootstrap(soup)
                return bootstrap["campaign"]["data"]["id"]

            with contextlib.suppress(css.SelectorError):
                url = self.parse_url(css.select(soup, "head link[href*='/campaign/']", "href"))
                return url.parts[url.parts.index("campaign") + 1]

            # TODO: fix next_js chunk parsing
            return _extract_campaign_id(await resp.text())

    def posts(self, campaign_id: str) -> AsyncGenerator[dict[str, Any]]:
        url = (
            (self.ENTRYPOINT / "posts")
            .with_query(_API_PARAMS)
            .extend_query(
                {
                    "filter[campaign_id]": campaign_id,
                }
            )
        )
        return self.pager(url)

    async def pager(self, api_url: AbsoluteHttpURL) -> AsyncGenerator[dict[str, Any]]:
        while True:
            resp = await self.request_json(api_url)
            yield resp

            try:
                cursor = resp["meta"]["pagination"]["cursors"]["next"]
            except LookupError:
                break
            if not cursor:
                break
            api_url = api_url.update_query({"page[cursor]": cursor})


def _extract_campaign_id(content: str) -> str:
    for start, end in [
        (r"{\"value\":{\"campaign\":{\"data\":{\"id\":\"", r"\""),
        (r"\"id\":\"NavigationBar_", '\\"'),
    ]:
        try:
            return extr_text(content, start, end)
        except ValueError:
            pass
    raise ScrapeError(422, "Unable to extract campaign id")


def _flatten_included(included: list[Included]) -> dict[str, Included]:
    return {incl["id"]: incl for incl in included}


def _extract_bootstrap(soup: BeautifulSoup) -> dict[str, Any]:
    data = next_js.data(soup)
    envelope = data["props"]["pageProps"]["bootstrapEnvelope"]
    return envelope.get("pageBootstrap") or envelope["bootstrap"]


def _parse_post(post: dict[str, Any]) -> Generator[tuple[str, Any]]:
    yield "id", str(post["id"])
    yield from _parse_attributes(post["attributes"])
    yield "relationships", post["relationships"]
    yield "campaign_id", post["relationships"]["campaign"]["data"]["id"]


def _parse_attributes(attributes: dict[str, Any]) -> Generator[tuple[str, Any]]:
    json_string = "_json_string"
    json_keys = tuple(key for key in attributes if key.endswith(json_string))

    for json_key in json_keys:
        name = json_key.removesuffix(json_string)
        value = attributes.pop(name, None)
        json_value = attributes.pop(json_key, None)
        # TODO: convert to html
        if not value and json_value:
            value = json.loads(json_value)

        yield name, value

    yield from attributes.items()


def _flatten_post(post: dict[str, Any]) -> Post:
    return cast("Post", dict(sorted(_parse_post(post))))  # pyright: ignore[reportInvalidCast]


def _get_post_media(post: Post) -> Generator[str]:
    for name in ("media", "video", "audio", "images", "attachments", "attachments_media"):
        relationships = post["relationships"].get(name, {}).get("data")
        if not relationships:
            continue

        if type(relationships) is not list:
            relationships = [relationships]

        for asset in relationships:
            yield asset["id"]


def _md5_from_url(url: AbsoluteHttpURL) -> str | None:
    for p in reversed(url.parts):
        if len(p) == 32:
            return p


def _unique_media(medias: Iterable[Media]) -> Generator[Media]:
    media_ids: set[str] = set()
    media_hashes: set[str] = set()

    for media in medias:
        if media.id in media_ids:
            continue
        media_ids.add(media.id)
        if media.hash:
            if media.hash in media_hashes:
                continue
            media_hashes.add(media.hash)
        yield media


def _parse_media(post: Post, included: dict[str, Included]) -> Generator[Media]:
    if post_file := post.get("post_file"):
        media_id = str(post_file["media_id"])
        url = PatreonCrawler.parse_url(post_file["url"])
        yield Media(media_id, post_file.get("name"), url, post_file)

    for media_id in _get_post_media(post):
        media = included[media_id]
        attributes = media["attributes"]

        if media["type"] == "media" and (url := attributes.get("download_url")):
            yield Media(media_id, attributes.get("file_name"), PatreonCrawler.parse_url(url), attributes)

    if image := post.get("image"):
        url = PatreonCrawler.parse_url(image.get("large_url") or image["url"])
        if m_hash := _md5_from_url(url):
            yield Media(m_hash, None, url, image)

    # TODO: convert tiptap JSON to HTML or extract media ids from tiptap


_API_PARAMS = (
    (
        "include",
        ",".join(
            (
                "campaign",
                "attachments",
                "attachments_media",
                "audio",
                "video",
                "images",
                "media",
                "native_video_insights",
                "user",
            )
        ),
    ),
    (
        "fields[campaign]",
        ",".join(
            (
                "currency",
                "show_audio_post_download_links",
                "avatar_photo_url",
                "avatar_photo_image_urls",
                "is_nsfw",
                "is_monthly",
                "name",
                "url",
            )
        ),
    ),
    (
        "fields[post]",
        ",".join(
            (
                "content",
                "content_json_string",
                "current_user_can_view",
                "embed",
                "image",
                "is_paid",
                "meta_image_url",
                "post_file",
                "post_metadata",
                "published_at",
                "post_type",
                "thumbnail",
                "thumbnail_url",
                "teaser_text",
                "title",
                "url",
                "moderation_status",
            )
        ),
    ),
    (
        "fields[user]",
        ",".join(
            (
                "image_url",
                "full_name",
                "url",
            )
        ),
    ),
    (
        "fields[media]",
        ",".join(
            (
                "id",
                "image_urls",
                "download_url",
                "metadata",
                "file_name",
            )
        ),
    ),
    ("sort", "-published_at"),
    ("filter[is_draft]", "false"),
    ("json-api-version", "1.0"),
)
