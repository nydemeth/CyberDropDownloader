from __future__ import annotations

import base64
import functools
import logging
import platform
import ssl
from typing import TYPE_CHECKING

import aiohttp
import wassima

from cyberdrop_dl.utils import TextExtractor

if TYPE_CHECKING:
    import asyncio
    from collections.abc import Generator, Iterable
    from pathlib import Path


logger = logging.getLogger(__name__)

_DNS_CLS: type[aiohttp.AsyncResolver | aiohttp.ThreadedResolver] | None = None


async def _get_dns_resolver(
    loop: asyncio.AbstractEventLoop | None = None,
) -> type[aiohttp.AsyncResolver | aiohttp.ThreadedResolver]:
    """Test aiodns with a DNS lookup."""

    # pycares (the underlying C extension that aiodns uses) installs successfully in most cases,
    # but it fails to actually connect to DNS servers on some platforms (e.g., Android).

    if (system := platform.system()) in {"Windows", "Android"}:
        logger.warning(
            f"Unable to setup asynchronous DNS resolver. Falling back to thread based resolver. Reason: not supported on {system}"
        )
        return aiohttp.ThreadedResolver

    try:
        import aiodns

        async with aiodns.DNSResolver(loop=loop, timeout=5.0) as resolver:
            _ = await resolver.query_dns("github.com", "A")

    except Exception as e:  # noqa: BLE001
        logger.warning(f"Unable to setup asynchronous DNS resolver. Falling back to thread based resolver: {e!r}")
        return aiohttp.ThreadedResolver

    else:
        return aiohttp.AsyncResolver


async def choose_dns_resolver() -> type[aiohttp.AsyncResolver | aiohttp.ThreadedResolver]:
    global _DNS_CLS  # noqa: PLW0603
    if _DNS_CLS is None:
        _DNS_CLS = await _get_dns_resolver()  # pyright: ignore[reportConstantRedefinition]
    return _DNS_CLS


def create_connector(ssl_context: ssl.SSLContext | bool, /) -> aiohttp.TCPConnector:  # noqa: FBT001
    if _DNS_CLS is None:
        raise RuntimeError("DNS resolver is unknown")
    tcp_conn = aiohttp.TCPConnector(ssl=ssl_context, resolver=_DNS_CLS())
    tcp_conn._resolver_owner = True
    return tcp_conn


def create_ssl_context(
    min_ver: ssl.TLSVersion = ssl.TLSVersion.TLSv1_2,
    ca_certs: Iterable[Path] = (),
) -> ssl.SSLContext:
    for file in _list_pem_files(ca_certs):
        _register_pem_file(file)
    ctx = wassima.create_default_ssl_context(hybrid_store=True)
    ctx.minimum_version = min_ver
    return ctx


def resolve_tls_version(name: str) -> ssl.TLSVersion:
    match name:
        case "1.2":
            return ssl.TLSVersion.TLSv1_2
        case "1.3":
            return ssl.TLSVersion.TLSv1_3
        case _:
            raise ValueError(name)


def _list_pem_files(paths: Iterable[Path]) -> Generator[Path]:
    for path in paths:
        if path.is_dir():
            yield from _list_pem_files(path.glob("*.pem"))
        elif path.suffix != ".pem":
            logger.warning("'%s' is not a valid PEM file, ignoring..", path)
            continue
        else:
            yield path


@functools.cache
def root_der_certificates() -> set[bytes]:
    return set(wassima.root_der_certificates())


def _register_pem_file(file: Path) -> None:
    logger.debug("Loading CA certificates from '%s'", file)

    try:
        n_certs = _load_cert_chain(file)
    except UntrustedCAError as e:
        msg, n_certs = e.args
        logger.warning(msg)

    logger.debug("Loaded %s CA certificates from '%s'", n_certs, file)


class UntrustedCAError(ValueError): ...


def _load_cert_chain(file: Path) -> int:
    certs = tuple(_read_cert_chain(file))
    if not certs:
        raise ValueError(f"No valid certificates found in '{file}'")

    trusted_cas = root_der_certificates()
    for idx, cert in enumerate(certs):
        if cert in trusted_cas:
            return idx
        wassima.register_ca(cert)

    raise UntrustedCAError(f"None of the certificates in the chain from '{file}' are trusted by the OS", len(certs))


def _read_cert_chain(path: Path) -> Generator[bytes]:
    for cert in TextExtractor(path.read_text()).repeat(ssl.PEM_HEADER, ssl.PEM_FOOTER):
        yield base64.decodebytes(cert.encode("ascii", "strict"))
