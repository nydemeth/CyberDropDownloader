from __future__ import annotations

from pathlib import Path

import pytest

from cyberdrop_dl.utils import css, next_js

TEST_HTML = (Path(__file__).parent / "nextjsv13.html").read_text(encoding="utf8")
TEST_SOUP = css.soup(TEST_HTML)


def test_extract_raw_pushes() -> None:
    pushes = list(next_js._extract_raw_pushes(TEST_SOUP))
    assert len(pushes) == 26
    for push in pushes:
        chunk_id, _, data = push[1:-1].partition(",")
        assert chunk_id == chunk_id.strip()
        assert data == data.strip()


@pytest.mark.parametrize(
    ("push", "expected_type", "expected_value"),
    [
        ("[0]", next_js._FlightType.BOOTSTRAP, "<INIT>"),
        ('[1,"1:$Sreact.fragment"]', next_js._FlightType.PAYLOAD, "1:$Sreact.fragment"),
    ],
)
def test_decode_push(push: str, expected_type: next_js._FlightType, expected_value: object) -> None:
    push_type, value = next_js._decode_push(push)
    assert push_type is expected_type
    assert value == expected_value


def test_extract_flight_data_remove_undefined() -> None:
    assert "$undefined" in TEST_HTML
    assert "$undefined" not in next_js.extract_flight_data(TEST_SOUP)


def test_parse() -> None:
    flight_data = next_js.extract_flight_data(TEST_SOUP)
    chunks = next_js.parse(flight_data)
    assert len(chunks) == 111
    errors = sum(1 for v in chunks.values() if v is next_js._Magic.ERROR)
    assert errors == 1
    assert chunks["1c"] is next_js._Magic.ERROR
