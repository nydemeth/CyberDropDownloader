from __future__ import annotations

import logging
import re

import yarl

from cyberdrop_dl.exceptions import InvalidURLError
from cyberdrop_dl.url_objects import AbsoluteHttpURL, is_absolute_http_url

logger = logging.getLogger(__name__)


def fix_query_params_encoding(link: str) -> str:
    if "?" not in link:
        return link
    parts, query_and_frag = link.split("?", 1)
    query_and_frag = query_and_frag.replace("+", "%20")
    return f"{parts}?{query_and_frag}"


def fix_multiple_slashes(link_str: str) -> str:
    return re.sub(r"(?:https?)?:?(\/{3,})", "//", link_str)


def str_to_url(link_str: str) -> yarl.URL:
    if not link_str:
        raise InvalidURLError("link_str is empty", url=link_str)

    try:
        clean_link_str = fix_multiple_slashes(fix_query_params_encoding(link_str))
        return yarl.URL(clean_link_str, encoded="%" in clean_link_str)

    except (AttributeError, ValueError, TypeError) as e:
        raise InvalidURLError(str(e), url=link_str) from e


def parse_http_url(
    link_str: AbsoluteHttpURL | yarl.URL | str, relative_to: AbsoluteHttpURL | None = None, *, trim: bool = True
) -> AbsoluteHttpURL:
    """Parse a string into an absolute URL, handling relative URLs, encoding and optionally removes trailing slash (trimming).
    Raises:
        InvalidURLError: If the input string is not a valid URL or if any other error occurs during parsing.
        TypeError: If `relative_to` is `None` and the parsed URL is relative or has no scheme.
    """

    url = str_to_url(link_str) if isinstance(link_str, str) else link_str
    if not url.absolute:
        if not relative_to:
            raise InvalidURLError("Relative URL with no known base", url=link_str)
        url = relative_to.join(url)
    if not url.scheme:
        url = url.with_scheme(relative_to.scheme if relative_to else "https")
    assert is_absolute_http_url(url)
    if not trim:
        return url
    return remove_trailing_slash(url)


def remove_trailing_slash(url: AbsoluteHttpURL) -> AbsoluteHttpURL:
    if url.name or url.path == "/":
        return url
    return url.parent.with_fragment(url.fragment).with_query(url.query)
