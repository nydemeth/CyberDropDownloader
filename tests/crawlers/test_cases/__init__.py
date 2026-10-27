import dataclasses
import runpy
from collections.abc import Generator, Sequence
from pathlib import Path
from typing import Any, Required, TypedDict

from pydantic import TypeAdapter


class Result(TypedDict, total=False):
    # Simplified version of media_item
    url: Required[str]
    filename: str | type
    debrid_link: str | type | None
    original_filename: str | type
    referer: str | type
    album_id: str | type | None
    uploaded_at: int | type | None
    download_folder: str | type
    thumbnail: str | type | None
    size: int | type | None
    duration: float | type | None
    parents: tuple[str, ...]
    metadata: object
    extra_info: dict[str, Any]
    id: tuple[str, ...]
    base64_id: str
    headers: dict[str, str]


@dataclasses.dataclass(slots=True)
class CrawlerTestCase:
    domain: str
    url: str
    results: list[Result]
    sort_by: str = "url"
    args: tuple[str, ...] = ()
    description: str | None = None
    fail: bool | str | int = False
    xfail: str | None = None
    skip: str | bool = False
    count: Sequence[int] | int | None = None
    options: list[str] | None = None
    log: str | None = None

    @property
    def test_id(self) -> str:
        return f"{self.domain} - {self.url}"


type TestData = dict[str, TestCaseModule]

_TEST_CASE_ADAPTER = TypeAdapter(CrawlerTestCase)


@dataclasses.dataclass(slots=True, frozen=True, order=True)
class TestCaseModule:
    domain: str
    file: Path
    cases: list[dict[str, Any]] = dataclasses.field(hash=False)


def load_modules() -> Generator[TestCaseModule]:
    for file in (Path(__file__).parent).iterdir():
        if not file.name.startswith("_") and file.suffix == ".py":
            module_globals = runpy.run_path(str(file), run_name=file.stem)

            yield TestCaseModule(module_globals["DOMAIN"], file, module_globals["TEST_CASES"])


def load_cases() -> TestData:
    test_data: TestData = {}
    for module in load_modules():
        if module.domain in test_data:
            raise RuntimeError(
                f"Multiple tests files for {module.domain}: {(module.file, test_data[module.domain].file)}"
            )

        test_data[module.domain] = module

    return test_data


def parse_cases(data: TestData) -> list[CrawlerTestCase]:
    test_cases: list[CrawlerTestCase] = []
    for domain, module in sorted(data.items()):
        test_cases.extend(_TEST_CASE_ADAPTER.validate_python({"domain": domain} | case) for case in module.cases)
    return test_cases


def load() -> list[CrawlerTestCase]:
    return parse_cases(load_cases())
