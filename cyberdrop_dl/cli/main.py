from __future__ import annotations

import logging
from contextvars import ContextVar
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import cyclopts.validators
from cyclopts import Parameter
from cyclopts.group import Group

from cyberdrop_dl.cli import CLIargs
from cyberdrop_dl.cli.compat import check_for_v9_files
from cyberdrop_dl.config import Config
from cyberdrop_dl.config.appdata import AppData
from cyberdrop_dl.exceptions import CDLConfigRuntimeErrorsGroup
from cyberdrop_dl.logs import log_spacer, set_console_level, setup_file_logging
from cyberdrop_dl.models import merge_models
from cyberdrop_dl.models.types import HttpURL  # noqa: TC001
from cyberdrop_dl.utils import cleanup

logger = logging.getLogger(__name__)
_INTERACTIVE: ContextVar[bool] = ContextVar("_INTERACTIVE", default=False)

if TYPE_CHECKING:
    from cyclopts.argument import ArgumentCollection

    from cyberdrop_dl.manager import Manager


async def _scrape(manager: Manager) -> None:
    from cyberdrop_dl import ffmpeg, webhook
    from cyberdrop_dl.scrape_mapper import ScrapeMapper
    from cyberdrop_dl.updates import check_latest_pypi
    from cyberdrop_dl.utils import apprise

    manager.log_config_settings()
    if not ffmpeg.is_installed():
        _check_ffmpeg(manager.config)

    log_spacer()
    async with manager.database:
        log_spacer()
        logger.info("Starting CDL...")
        async with ScrapeMapper(manager)() as scrape_mapper:
            stats = await scrape_mapper.run()

        log_spacer()
        await _post_runtime(manager)

        stats_summary = manager.print_stats(stats)

        log_spacer()
        async with manager.http_client.create_aiohttp_session() as session:
            await check_latest_pypi(session)
        log_spacer()
        logger.info("Closing program...")
        logger.info("Finished downloading. Enjoy :)", extra={"color": "green"})

        if webhook_url := manager.config.notifications.webhook:
            await webhook.send_notification(webhook_url, stats_summary)

        if urls := manager.config.notifications.apprise:
            await apprise.send_notifications(urls, stats_summary)


async def _post_runtime(manager: Manager) -> None:
    """Actions to complete after main runtime, and before UI shutdown."""
    logger.info("Running Post-Download Processes\n", extra={"color": "green"})

    if (
        manager.config.hashing.mode.enabled
        and manager.config.hashing.dedupe.enabled
        and not manager.config.ignore_history
    ):
        file_hashes = await manager.hasher.run(manager.completed_downloads)
        await manager.deduper.run(file_hashes)

    if manager.config.sort.enabled:
        await manager.sorter.run()

    _check_partials_and_empty_folders(manager.config)


def _show_interactive_ui(manager: Manager) -> None:
    if not _INTERACTIVE.get():
        return

    from cyberdrop_dl import program_ui

    program_ui.run(manager)


def _main(manager: Manager) -> None:
    from cyberdrop_dl import aio

    set_console_level(manager.config.logs.effective_console_level)
    manager.appdata.mkdirs()
    try:
        with manager():
            _show_interactive_ui(manager)

            with setup_file_logging(
                manager.config.logs.files.main,
                level=manager.config.logs.effective_level,
            ):
                aio.run(_scrape(manager))

    except KeyboardInterrupt:
        logger.info("Exiting (Ctrl + C) ...")


def _validate_inputs(args: ArgumentCollection) -> None:
    try:
        cyclopts.validators.LimitedChoice(min=1, max=1)(args)
    except ValueError as e:
        if "choices may be specified." in str(e):
            raise ValueError("You must provide either URLs or a file with `--input-file`") from None
        raise


inputs_group = Group(sort_key=-1, validator=_validate_inputs)


def interactive(
    *,
    input_file: Annotated[
        Path,
        Parameter(
            alias="-i",
            help="Text/HTML file with URL(s) to download",
            validator=cyclopts.validators.Path(dir_okay=False),
        ),
    ] = Path("URLs.txt"),  # pyright: ignore[reportCallInDefaultInitializer]
    cli: CLIargs | None = None,
) -> None:
    "Show a TUI menu equivalent to the CLI commands"
    _INTERACTIVE.set(True)
    download(input_file=input_file, cli=cli or CLIargs())


def download(
    urls: Annotated[
        tuple[HttpURL, ...],
        Parameter(
            group=inputs_group,
            help="URL(s) to download",
        ),
    ] = (),
    /,
    *,
    input_file: Annotated[
        Path | None,
        Parameter(
            group=inputs_group,
            alias="-i",
            help="Text/HTML file with URL(s) to download",
            validator=cyclopts.validators.Path(exists=True, dir_okay=False),
        ),
    ] = None,
    cli: CLIargs | None = None,
    cli_overrides: Config | None = None,
) -> None:
    "Download URLs"
    check_for_v9_files()
    if input_file:
        input_file = input_file.resolve().absolute()

    from cyberdrop_dl.manager import Manager

    appdata, config = _prepare_appdata_and_config(urls, cli, cli_overrides)
    _main(Manager(cli, appdata, config, input_file))


def _prepare_appdata_and_config(
    urls: tuple[HttpURL, ...] = (),
    cli: CLIargs | None = None,
    cli_overrides: Config | None = None,
) -> tuple[AppData, Config]:

    cli = cli or CLIargs()
    cli.links = urls
    appdata = AppData.create(
        config_file=cli.config_file,
        cache_file=cli.cache_file,
        db_file=cli.database_file,
    )

    default_config = Config.from_file(cli.config_file or appdata.config_file)
    config = merge_models(default_config, cli_overrides) if cli_overrides else default_config
    return appdata, config


def _check_ffmpeg(config: Config) -> None:
    errors: list[Exception] = []
    if config.sort.needs_ffmpeg:
        exc = RuntimeError("Sorting media files requires 'ffmpeg' to be installed")
        exc.add_note("Disable sorting or install ffmpeg")
        errors.append(exc)

    if config.filters.duration.needs_ffmpeg:
        exc = RuntimeError("Filtering files by duration requires 'ffmpeg' to be installed")
        exc.add_note("Disable media duration limits or install ffmpeg")
        errors.append(exc)

    if errors:
        raise CDLConfigRuntimeErrorsGroup("Some config options are impossible to fulfill", errors)


def _check_partials_and_empty_folders(config: Config) -> None:
    logger.info("Checking for partial downloads...")
    if cleanup.has_partial_files(config.download_folder):
        logger.warning("There are partial downloads in the downloads folder")

    if config.delete_partial_files:
        logger.info("Deleting partial downloads...")
        cleanup.rm_partial_files(config.download_folder)

    if not config.delete_empty_folders:
        return

    _delete_empty_files(config)


def _delete_empty_files(config: Config) -> None:
    logger.info("Deleting empty files and folders...")
    cleanup.rm_empty_dirs(config.download_folder)

    sorted_folder = config.sort.output_folder
    if sorted_folder and config.sort.enabled:
        cleanup.rm_empty_dirs(sorted_folder)
