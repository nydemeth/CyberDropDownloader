import inspect
import os
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from rich.text import Text

from cyberdrop_dl import constants
from cyberdrop_dl.constants import NotificationResult
from cyberdrop_dl.managers.config_manager import ConfigManager
from cyberdrop_dl.managers.manager import Manager
from cyberdrop_dl.managers.path_manager import PathManager
from cyberdrop_dl.utils import apprise
from tests.fake_classes.managers import FakeCacheManager

TEST_FILES_PATH = Path(__file__).parent / "test_files/apprise"
FAKE_MANAGER = Manager()
FAKE_MANAGER.cache_manager = FakeCacheManager(FAKE_MANAGER)
FAKE_MANAGER.config_manager = ConfigManager(FAKE_MANAGER)

URL_FAIL = "mailto://test_user:test_email@gmail.com"
APPRISE_ENV_VAR = "APPRISE_TEST_EMAIL_URL"
URL_SUCCESS = os.environ.get(APPRISE_ENV_VAR, "")
URL_SUCCESS_ATTACH_LOGS = f"attach_logs={URL_SUCCESS}"

pytestmark = pytest.mark.skipif(not URL_SUCCESS, reason=f"{APPRISE_ENV_VAR} environment variable is not set")


@dataclass
class AppriseTestCase:
    urls: list[str]
    result: NotificationResult
    include: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    file: Path | None = None
    name: str = "Testing Apprise"


def test_get_apprise_urls() -> None:
    with pytest.raises(ValueError):
        apprise.get_apprise_urls()

    with pytest.raises(ValueError):
        apprise.get_apprise_urls(urls=["url"], file=Path.cwd())

    with pytest.raises(SystemExit):
        apprise.get_apprise_urls(file=TEST_FILES_PATH / "invalid_single_url.txt")

    with pytest.raises(SystemExit):
        apprise.get_apprise_urls(file=TEST_FILES_PATH / "invalid_multiple_urls.txt")

    result = apprise.get_apprise_urls(file=TEST_FILES_PATH / "file_that_does_not_exists.txt")
    assert result == []

    result = apprise.get_apprise_urls(file=TEST_FILES_PATH / "empty_file.txt")
    assert result == []

    result = apprise.get_apprise_urls(file=TEST_FILES_PATH / "valid_single_url.txt")
    assert isinstance(result, list), "Result is not a list"
    assert len(result) == 1, "This should be a single URL"
    assert isinstance(result[0], apprise.AppriseURL), "Parsed URL is not an AppriseURL"

    result = apprise.get_apprise_urls(file=TEST_FILES_PATH / "valid_multiple_urls.txt")
    assert isinstance(result, list), "Result is not a list"
    assert len(result) == 5, "These should be 5 URLs"

    expected_result = [
        apprise.AppriseURL(url="discord://avatar@webhook_id/webhook_token", tags={"no_logs"}),
        apprise.AppriseURL(url="enigma2://hostname", tags={"another_tag", "no_logs"}),
        apprise.AppriseURL(url="mailto://domain.com?user=userid&pass=password", tags={"tag2", "tag_1", "no_logs"}),
        apprise.AppriseURL(url="reddit://user:password@app_id/app_secret/subreddit", tags={"attach_logs"}),
        apprise.AppriseURL(url="windows://", tags={"simplified"}),
    ]

    for index in range(len(result)):
        got = result[index]
        expected = expected_result[index]
        assert isinstance(got, apprise.AppriseURL), f"Parsed URL {got} is not an AppriseURL"
        assert got == expected, f"Parsed URL: {got.raw_url}, Expected URL: {expected.raw_url}"


async def send_notification(test_case: AppriseTestCase) -> None:
    FAKE_MANAGER.config_manager.apprise_urls = []
    if test_case.urls and any(test_case.urls):
        FAKE_MANAGER.config_manager.apprise_urls = apprise.get_apprise_urls(urls=test_case.urls)
    FAKE_MANAGER.path_manager = PathManager(FAKE_MANAGER)
    FAKE_MANAGER.path_manager.main_log = test_case.file or TEST_FILES_PATH / "valid_single_url.txt"
    constants.LOG_OUTPUT_TEXT = Text(test_case.name)
    result, logs = await apprise.send_apprise_notifications(FAKE_MANAGER)
    assert result.value == test_case.result.value, f"Result for this case should be {test_case.result.value}"
    assert isinstance(logs, list), "Invalid return type for logs"
    assert logs, "Logs can't be empty"
    logs_as_str = "\n".join([line.msg for line in logs])
    print(logs_as_str)
    if test_case.include:
        matches = [match.casefold() in logs_as_str.casefold() for match in test_case.include]
        assert all(matches), "Logs do not match expected pattern"
    if test_case.exclude:
        assert not any(match in logs_as_str for match in test_case.exclude), "Logs should not match exclude pattern"


async def test_failed_notification() -> None:
    test_case = AppriseTestCase(
        urls=[URL_FAIL],
        result=NotificationResult.FAILED,
        name=inspect.currentframe().f_code.co_name,  # type: ignore
    )
    await send_notification(test_case)


async def test_successful_notification() -> None:
    test_case = AppriseTestCase(
        urls=[URL_SUCCESS],
        result=NotificationResult.SUCCESS,
        include=["Sent Discord notification", "Discord Payload"],
        name=inspect.currentframe().f_code.co_name,  # type: ignore
    )
    await send_notification(test_case)


async def test_successful_notification_with_successful_attachment() -> None:
    test_case = AppriseTestCase(
        urls=[URL_SUCCESS_ATTACH_LOGS],
        result=NotificationResult.SUCCESS,
        include=["Sent Discord notification", "Discord Payload"],
        name=inspect.currentframe().f_code.co_name,  # type: ignore
    )
    await send_notification(test_case)


async def test_successful_notification_with_failed_attachment() -> None:
    test_case = AppriseTestCase(
        urls=[URL_SUCCESS_ATTACH_LOGS],
        result=NotificationResult.SUCCESS,
        include=["Sent Discord notification", "Discord Payload", "Unable to get copy of main log file"],
        file=TEST_FILES_PATH / "file_that_does_exists.txt",
        name=inspect.currentframe().f_code.co_name,  # type: ignore
    )
    await send_notification(test_case)


async def test_none_notification() -> None:
    test_case = AppriseTestCase(
        urls=[""],
        result=NotificationResult.NONE,
        include=[NotificationResult.NONE.value.plain],
        name=inspect.currentframe().f_code.co_name,  # type: ignore
    )
    await send_notification(test_case)


async def test_partial_notification() -> None:
    test_case = AppriseTestCase(
        urls=[URL_SUCCESS_ATTACH_LOGS, URL_FAIL],
        result=NotificationResult.PARTIAL,
        include=["Connection error while submitting email", "Sent Discord notification"],
        name=inspect.currentframe().f_code.co_name,  # type: ignore
    )
    await send_notification(test_case)
