from __future__ import annotations

import calendar
import contextlib
import datetime
from dataclasses import dataclass
from typing import TYPE_CHECKING

from yarl import URL

from cyberdrop_dl.clients.errors import NoExtensionError
from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.data_enums_classes.url_objects import FILE_HOST_ALBUM, FILE_HOST_PROFILE
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
    from bs4 import BeautifulSoup, Tag

    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import ScrapeItem


@dataclass
class Post:
    id: int
    title: str
    date: int

    @property
    def number(self):
        return self.id


class NekohouseCrawler(Crawler):
    primary_base_domain = URL("https://nekohouse.su")
    DEFAULT_POST_TITLE_FORMAT = "{date} - {title}"

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "nekohouse", "Nekohouse")
        self.services = ["fanbox", "fantia", "fantia_products", "subscribestar", "twitter"]

        self.post_selector = "article.post-card a"
        self.post_content_selector = "div[class=scrape__files]"
        self.file_downloads_selector = "a[class=scrape__attachment-link]"
        self.post_images_selector = "div[class=fileThumb]"
        self.post_videos_selector = "video[class=post__video] source"
        self.post_timestamp_selector = "time[class=timestamp ]"
        self.post_title_selector = "h1[class=scrape__title] span"
        self.post_content_selector = "div[class=scrape__content]"
        self.post_author_username_selector = "a[class=scrape__user-name]"

        self.maximum_offset = 0

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if "thumbnails" in scrape_item.url.parts:
            parts = [x for x in scrape_item.url.parts if x not in ("thumbnail", "/")]
            new_path = "/".join(parts)
            scrape_item.url = scrape_item.url.with_path(new_path)
            await self.handle_direct_link(scrape_item)
        elif "post" in scrape_item.url.parts:
            post_id = scrape_item.url.parts[-1] if "user" not in scrape_item.url.parts else None
            await self.post(scrape_item, post_id=post_id)
        elif any(x in scrape_item.url.parts for x in self.services):
            await self.profile(scrape_item)
        else:
            await self.handle_direct_link(scrape_item)

    @error_handling_wrapper
    async def profile(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a profile."""
        soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)
        offset, maximum_offset = await self.get_offsets(scrape_item, soup)
        service, user = self.get_service_and_user(scrape_item)
        user_str = await self.get_user_str_from_profile(soup)
        service_call = self.primary_base_domain / service / "user" / user
        scrape_item.set_type(FILE_HOST_PROFILE, self.manager)
        while offset <= maximum_offset:
            async with self.request_limiter:
                service_url = service_call.with_query({"o": offset})
                soup: BeautifulSoup = await self.client.get_soup(self.domain, service_url, origin=scrape_item)
                offset += 50

                posts = soup.select(self.post_selector)
                if not posts:
                    break
                for post in posts:
                    # Create a new scrape item for each post
                    post_url_str: str = post.get("href", "")
                    post_link = self.parse_url(post_url_str)
                    post_id = post_url_str.split("/")[-1]
                    # Call on self.post to scrape the post by creating a new scrape item
                    new_scrape_item = self.create_scrape_item(scrape_item, post_link, add_parent=service_call)
                    await self.post(new_scrape_item, post_id, user, service, user_str)
                    scrape_item.add_children()

    @error_handling_wrapper
    async def post(
        self,
        scrape_item: ScrapeItem,
        post_id: int | None = None,
        user: str | None = None,
        service: str | None = None,
        user_str: str | None = None,
    ) -> None:
        """Scrapes a post."""
        scrape_item.set_type(FILE_HOST_ALBUM, self.manager)
        if any(x is None for x in (post_id, user, service, user_str)):
            service, user, post_id = await self.get_service_user_and_post(scrape_item)
            user_str = await self.get_user_str_from_post(scrape_item)
        await self.get_post_content(scrape_item, post_id, user, service, user_str)

    @error_handling_wrapper
    async def get_post_content(
        self,
        scrape_item: ScrapeItem,
        post: int,
        user: str,
        service: str,
        user_str: str,
    ) -> None:
        """Gets the content of a post and handles collected links."""
        if post == 0:
            return

        post_url = scrape_item.url
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, post_url, origin=scrape_item)
            data = {
                "id": post,
                "user": user or "Unknown",
                "service": service or "Unknown",
                "user_str": user_str or "Unknown",
                "file": [],
                "attachments": [],
            }

            data["title"] = soup.select_one(self.post_title_selector) or "Unknown Title"
            data["content"] = soup.select_one(self.post_content_selector) or None
            data["published"] = soup.select_one(self.post_timestamp_selector) or None

            for key in ("title", "content", "published"):
                with contextlib.suppress(AttributeError):
                    value: Tag = data.get(key)
                    data[key] = value.text.strip()

            for file in soup.select(self.post_images_selector):
                attachment = {
                    "path": file["href"].replace("/data/", "data/"),
                    "name": file["href"].split("?f=")[-1]
                    if "?f=" in file["href"]
                    else file["href"].split("/")[-1].split("?")[0],
                }
                data["attachments"].append(attachment)

            for file in soup.select(self.post_videos_selector):
                attachment = {
                    "path": file["src"].replace("/data/", "data/"),
                    "name": file["src"].split("?f=")[-1]
                    if "?f=" in file["src"]
                    else file["src"].split("/")[-1].split("?")[0],
                }
                data["attachments"].append(attachment)

            for file in soup.select(self.file_downloads_selector):
                attachment = {
                    "path": file["href"].replace("/data/", "data/"),
                    "name": file["href"].split("?f=")[-1]
                    if "?f=" in file["href"]
                    else file["href"].split("/")[-1].split("?")[0],
                }
                data["file"].append(attachment)

        await self.handle_post_content(scrape_item, data, user_str)

    @error_handling_wrapper
    async def handle_post_content(self, scrape_item: ScrapeItem, post: dict[str, str], user_str: str) -> None:
        """Handles the content of a post."""
        date = post.get("published")
        if date:
            date = date.replace("T", " ").strip()
        post_id = post["id"]
        post_title = post.get("title", "")

        scrape_item.album_id = post_id
        scrape_item.part_of_album = True

        async def handle_file(file_obj: dict[str, str]):
            link = self.primary_base_domain / file_obj["path"]
            link = link.with_query({"f": file_obj["name"]})
            await self.create_new_scrape_item(link, scrape_item, user_str, post_title, post_id, date)

        for file in post["attachments"]:
            await handle_file(file)
            scrape_item.add_children()

    @error_handling_wrapper
    async def handle_direct_link(self, scrape_item: ScrapeItem) -> None:
        """Handles a direct link."""
        try:
            filename, ext = get_filename_and_ext(scrape_item.url.query.get("f") or scrape_item.url.name)
        except NoExtensionError:
            # Not sure if this is necessary, is mostly just to keep it similar to kemono
            filename, ext = get_filename_and_ext(scrape_item.url.name)
        await self.handle_file(scrape_item.url, scrape_item, filename, ext)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def create_new_scrape_item(
        self,
        link: URL,
        old_scrape_item: ScrapeItem,
        user: str,
        title: str,
        post_id: str,
        date: str,
        add_parent: URL | None = None,
    ) -> None:
        """Creates a new scrape item with the same parent as the old scrape item."""
        post = Post(id=post_id, title=title, date=date)
        new_title = self.create_title(user)
        new_scrape_item = self.create_scrape_item(
            old_scrape_item,
            link,
            new_title,
            part_of_album=True,
            possible_datetime=post.date,
            add_parent=add_parent,
        )
        self.add_separate_post_title(new_scrape_item, post)
        await self.handle_direct_link(new_scrape_item)

    async def get_maximum_offset(self, soup: BeautifulSoup) -> int:
        """Gets the maximum offset for a scrape item."""
        menu = soup.select_one("menu")
        if menu is None:
            self.maximum_offset = 0
            return 0
        try:
            max_tabs = (
                (int(soup.select_one("div[id=paginator-top] small").text.strip().split(" ")[-1]) + 49) // 50
            ) * 50
        except AttributeError:
            max_tabs = 0
        pagination_links = menu.find_all("a", href=True)
        offsets = [int(x["href"].split("?o=")[-1]) for x in pagination_links]
        offset = max(offsets)
        offset = max(max_tabs, offset)
        self.maximum_offset = offset
        return offset

    async def get_offsets(self, scrape_item: ScrapeItem, soup: BeautifulSoup) -> tuple[int, int]:
        """Gets the offset for a scrape item."""
        current_offset = int(scrape_item.url.query.get("o", 0))
        maximum_offset = await self.get_maximum_offset(soup)
        return current_offset, maximum_offset

    @error_handling_wrapper
    async def get_user_str_from_post(self, scrape_item: ScrapeItem) -> str:
        """Gets the user string from a scrape item."""
        async with self.request_limiter:
            soup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)
        return soup.select_one("a[class=scrape__user-name]").text

    @error_handling_wrapper
    async def get_user_str_from_profile(self, soup: BeautifulSoup) -> str:
        """Gets the user string from a scrape item."""
        return soup.select_one("span[itemprop=name]").text

    @staticmethod
    def get_service_and_user(scrape_item: ScrapeItem) -> tuple[str, str]:
        """Gets the service and user from a scrape item."""
        user = scrape_item.url.parts[3]
        service = scrape_item.url.parts[1]
        return service, user

    @staticmethod
    async def get_service_user_and_post(scrape_item: ScrapeItem) -> tuple[str, str, str]:
        """Gets the service, user and post id from a scrape item."""
        user = scrape_item.url.parts[3]
        service = scrape_item.url.parts[1]
        post = scrape_item.url.parts[5]
        return service, user, post

    @staticmethod
    def parse_datetime(date: str) -> int | None:
        """Parses a datetime string into a unix timestamp."""
        if not date:
            return None
        try:
            parsed_date = datetime.datetime.strptime(date, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            parsed_date = datetime.datetime.strptime(date, "%Y-%m-%d %H:%M:%S.%f")
        return calendar.timegm(parsed_date.timetuple())
