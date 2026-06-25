from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import functools
import json
import logging
import time
from typing import TYPE_CHECKING, Any, Protocol, TypedDict, cast

from cyberdrop_dl import __version__
from cyberdrop_dl.constants import MISSING

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Generator
    from pathlib import Path
    from types import CoroutineType

logger = logging.getLogger(__name__)
_IN_MEMORY_CACHE: dict[str, Any] = {}


class _CachedValue[T](TypedDict):
    value: T
    ttl: float | None
    created_at: float


def _has_expired(self: _CachedValue[Any]) -> bool:
    if self["ttl"] is None:
        return False
    return time.time() - self["created_at"] >= self["ttl"]


@dataclasses.dataclass(slots=True)
class TTLCacheAdapter[T]:
    _cache: dict[str, Any]
    _keys: tuple[str, ...] = ()
    _root: dict[str, _CachedValue[Any]] = dataclasses.field(init=False, repr=False)

    def create_lookup_path(self, *keys: str) -> str:
        return ".".join([*self._keys, *keys])

    @property
    def root(self) -> dict[str, _CachedValue[Any]]:
        try:
            return self._root
        except AttributeError:
            root = self._cache
            for key in self._keys:
                try:
                    root = root.setdefault(key, {})
                except (KeyError, TypeError, ValueError, AttributeError):
                    logger.exception(f"Invalid cache entry {self.create_lookup_path()}, ignoring")
                    root = {}
                    break

            self._root = root
            return self._root

    def __getitem__(self, key: str, /) -> T:
        cache_hit = self._get(key)
        if cache_hit is MISSING:
            raise KeyError(key)
        return cache_hit["value"]

    def _get(self, key: str) -> _CachedValue[T] | MISSING:  # pyright: ignore[reportInvalidTypeForm]
        try:
            cache_hit = self.root[key]
        except KeyError:
            return MISSING

        try:
            expired = _has_expired(cache_hit)
        except (KeyError, TypeError, ValueError, AttributeError):
            logger.exception(f"Invalid cache entry {self.create_lookup_path(key)}, ignoring")
            expired = True

        if expired:
            del self[key]
            return MISSING
        return cache_hit

    def __delitem__(self, key: str) -> None:
        del self.root[key]

    def get(self, key: str) -> T | None:
        cache_hit = self._get(key)
        return None if cache_hit is MISSING else cache_hit["value"]

    def save(self, key: str, value: T, *, ttl: float | None = None) -> None:
        """NOTE: cached values MUST be JSON serializable"""
        self.root[key] = {
            "value": value,
            "ttl": ttl,
            "created_at": time.time(),
        }

    def __setitem__(self, name: str, value: T) -> None:
        """NOTE: cached values MUST be JSON serializable"""
        self.save(name, value, ttl=None)

    def discard(self, key: str) -> None:
        try:
            del self[key]
        except KeyError:
            return


@contextlib.contextmanager
def cache_context(cache_file: Path, cache: dict[str, Any]) -> Generator[None]:
    try:
        content = cache_file.read_text()
    except FileNotFoundError:
        cache_file.parent.mkdir(exist_ok=True, parents=True)
        cache_file.touch()
    else:
        data = json.loads(content)
        assert type(data) is dict
        cache.update(data)
    try:
        yield
    finally:
        cache["version"] = __version__
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(cache, indent=2, ensure_ascii=False, sort_keys=True))


class CachedAsyncFunc[T](Protocol):
    def __call__(self) -> CoroutineType[Any, Any, T]: ...

    def clear(self) -> None: ...


def cached_fn[T](
    fn: Callable[[], Awaitable[T]],
    cache: TTLCacheAdapter[T] | None = None,
    *,
    key: str | None = None,
    ttl: float | None = None,
) -> CachedAsyncFunc[T]:

    lock = asyncio.Lock()

    *parts, fn_name = ".".join([fn.__module__, fn.__qualname__]).split(".")
    key = key or fn_name
    cache = cache or TTLCacheAdapter(_IN_MEMORY_CACHE, tuple(parts))

    @functools.wraps(fn)
    async def wrapper() -> T:
        try:
            return cache[key]
        except KeyError:
            pass

        async with lock:
            try:
                return cache[key]
            except KeyError:
                pass

            value = await fn()
            cache.save(key, value, ttl=ttl)
            return value

    wrapper.clear = lambda: cache.discard(key)  # pyright: ignore[reportAttributeAccessIssue]
    return cast("CachedAsyncFunc[T]", cast("object", wrapper))
