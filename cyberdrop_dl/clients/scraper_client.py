from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime
from json import dumps as json_dumps
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import cyberdrop_dl.constants as constants
from cyberdrop_dl.clients.response import AbstractResponse
from cyberdrop_dl.exceptions import DDOSGuardError
from cyberdrop_dl.utils.utilities import sanitize_filename

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from curl_cffi.requests.impersonate import BrowserTypeLiteral
    from curl_cffi.requests.session import HttpMethod

    from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
    from cyberdrop_dl.managers.client_manager import ClientManager


class ScraperClient:
    """AIOHTTP / CURL operations for scraping."""

    def __init__(self, client_manager: ClientManager) -> None:
        self.client_manager = client_manager
        self._save_pages_html = client_manager.manager.config_manager.settings_data.files.save_pages_html
        self._pages_folder = self.client_manager.manager.path_manager.pages_folder
        min_html_file_path_len = len(str(self._pages_folder)) + len(constants.STARTUP_TIME_STR) + 10
        self._max_html_stem_len = 245 - min_html_file_path_len

    @contextlib.asynccontextmanager
    async def _limiter(self, domain: str):
        with self.client_manager.request_context(domain):
            domain_limiter = self.client_manager.get_rate_limiter(domain)
            async with self.client_manager.global_rate_limiter, domain_limiter:
                await self.client_manager.manager.states.RUNNING.wait()
                yield

    @contextlib.asynccontextmanager
    async def _request(
        self: object,
        url: AbsoluteHttpURL,
        /,
        method: HttpMethod = "GET",
        headers: dict[str, str] | None = None,
        impersonate: BrowserTypeLiteral | bool | None = None,
        data: Any = None,
        json: Any = None,
        cache_disabled: bool = False,
        **request_params: Any,
    ) -> AsyncGenerator[AbstractResponse]:
        """
        Asynchronous context manager for HTTP requests.

        - If 'impersonate' is specified, uses curl_cffi for the request and updates cookies.
        - Otherwise, uses aiohttp with optional cache control.
        - Yield an AbstractResponse that wraps the underlying response with common methods.
        - On DDOSGuardError, retries the request using FlareSolverr.
        - Saves the HTML content to disk if the config option is enabled.
        - Closes underliying response on exit.
        """
        self = cast("ScraperClient", self)
        request_params["headers"] = self.client_manager._default_headers | (headers or {})
        request_params["data"] = data
        request_params["json"] = json

        async with self.__request_context(url, method, request_params, impersonate, cache_disabled) as resp:
            exc = None
            try:
                yield await self._check_response(resp, url)
            except Exception as e:
                exc = e
                raise
            finally:
                await self.write_soup_to_disk(url, resp, exc)

    @contextlib.asynccontextmanager
    async def __request_context(
        self,
        url: AbsoluteHttpURL,
        method: HttpMethod,
        request_params: dict[str, Any],
        impersonate: BrowserTypeLiteral | bool | None,
        cache_disabled: bool,
    ) -> AsyncGenerator[AbstractResponse]:
        if impersonate:
            self.client_manager.check_curl_cffi_is_available()
            if impersonate is True:
                impersonate = "chrome"
            request_params["impersonate"] = impersonate
            curl_resp = await self.client_manager._curl_session.request(method, str(url), stream=True, **request_params)
            try:
                yield AbstractResponse.from_resp(curl_resp)
                curl_cookies = self.client_manager._curl_session.cookies.get_dict(url.host)
                self.client_manager.cookies.update_cookies(curl_cookies, url)
            finally:
                await curl_resp.aclose()
            return

        async with (
            self.client_manager.cache_control(self.client_manager._session, disabled=cache_disabled),
            self.client_manager._session.request(method, url, **request_params) as aio_resp,
        ):
            yield AbstractResponse.from_resp(aio_resp)

    async def _check_response(self, abs_resp: AbstractResponse, url: AbsoluteHttpURL, data: Any | None = None):
        """Checks the HTTP response status and retries DDOS Guard errors with FlareSolverr.

        Returns an AbstractResponse confirmed to not be a DDOS Guard page."""
        try:
            await self.client_manager.check_http_status(abs_resp)
            return abs_resp
        except DDOSGuardError:
            flare_solution = await self.client_manager.flaresolverr.request(url, data)
            return AbstractResponse.from_flaresolverr(flare_solution)

    async def write_soup_to_disk(self, url: AbsoluteHttpURL, response: AbstractResponse, exc: Exception | None = None):
        """Writes html to a file."""

        if not self._save_pages_html:
            return

        content: str = await response.text()
        try:
            content = cast("str", (await response.soup()).prettify(formatter="html"))
        except Exception:
            pass

        now = datetime.now()
        log_date = now.strftime(constants.LOGS_DATETIME_FORMAT)
        url_str = str(url)
        response_url_str = str(response.url)
        clean_url = sanitize_filename(Path(url_str).as_posix().replace("/", "-"))
        filename = f"{clean_url[: self._max_html_stem_len]}_{log_date}.html"
        file_path = self._pages_folder / filename
        info = {
            "url": url_str,
            "response_url": response_url_str,
            "status_code": response.status,
            "datetime": now.isoformat(),
            "response_headers": dict(response.headers),
        }
        if exc:
            info |= {"error": str(exc), "exception": repr(exc)}

        json_data = json_dumps(info, indent=4, ensure_ascii=False)
        text = f"<!-- cyberdrop-dl scraping result\n{json_data}\n-->\n{content}"
        self.client_manager.manager.task_group.create_task(try_write(file_path, text))

    # Convenience methods for backward compatibility
    async def get_text(self, domain: str, url: AbsoluteHttpURL, **kwargs) -> str:
        """Get text content from a URL."""
        async with self._limiter(domain):
            async with self._request(url, **kwargs) as response:
                return await response.text()

    async def get_soup(self, domain: str, url: AbsoluteHttpURL, **kwargs):
        """Get BeautifulSoup object from a URL."""
        async with self._limiter(domain):
            async with self._request(url, **kwargs) as response:
                return await response.soup()

    async def post_data(self, domain: str, url: AbsoluteHttpURL, data: Any = None, **kwargs) -> Any:
        """Post data to a URL and return JSON response."""
        async with self._limiter(domain):
            async with self._request(url, method="POST", data=data, **kwargs) as response:
                return await response.json()
                
    async def get_json(self, domain: str, url: AbsoluteHttpURL, **kwargs) -> Any:
        """Get JSON response from a URL."""
        async with self._limiter(domain):
            async with self._request(url, **kwargs) as response:
                return await response.json()

    async def get_soup_cffi(self, domain: str, url: AbsoluteHttpURL, **kwargs):
        """Get BeautifulSoup object from a URL using curl_cffi."""
        async with self._limiter(domain):
            async with self._request(url, impersonate=True, **kwargs) as response:
                return await response.soup()

    async def post_data_raw(self, domain: str, url: AbsoluteHttpURL, data: Any = None, **kwargs) -> bytes:
        """Post data to a URL and return raw bytes response."""
        async with self._limiter(domain):
            async with self._request(url, method="POST", data=data, **kwargs) as response:
                return await response.read()

    async def get_head(self, domain: str, url: AbsoluteHttpURL, **kwargs) -> dict[str, str]:
        """Get HEAD response headers from a URL."""
        async with self._limiter(domain):
            async with self._request(url, method="HEAD", **kwargs) as response:
                return dict(response.headers)

    async def _get_response_and_soup(self, domain: str, url: AbsoluteHttpURL, **kwargs) -> tuple[Any, Any]:
        """Get response and soup objects from a URL."""
        async with self._limiter(domain):
            async with self._request(url, **kwargs) as response:
                soup = await response.soup()
                return response, soup

    async def _get_response_and_soup_cffi(self, domain: str, url: AbsoluteHttpURL, **kwargs) -> tuple[Any, Any]:
        """Get response and soup objects from a URL using curl_cffi."""
        async with self._limiter(domain):
            async with self._request(url, impersonate=True, **kwargs) as response:
                soup = await response.soup()
                return response, soup

    async def _get_head(self, domain: str, url: AbsoluteHttpURL, **kwargs):
        """Get HEAD response object from a URL."""
        async with self._limiter(domain):
            async with self._request(url, method="HEAD", **kwargs) as response:
                return response

    async def _get(self, domain: str, url: AbsoluteHttpURL, **kwargs) -> tuple[Any, Any]:
        """Get response and soup objects from a URL (alternative method name)."""
        async with self._limiter(domain):
            async with self._request(url, **kwargs) as response:
                soup = await response.soup()
                return response, soup
                
    @property
    def _session(self):
        """Provide access to the underlying session for backward compatibility."""
        return self.client_manager._session

async def try_write(file: Path, content: str) -> None:
    try:
        await asyncio.to_thread(file.write_text, content, "utf8")
    except OSError:
        pass
