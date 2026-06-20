from pathlib import Path

import pytest

from cyberdrop_dl import program_ui
from cyberdrop_dl.__main__ import run_cdl


def test_startup(capsys: pytest.CaptureFixture[str]) -> None:
    # This is just to test that cyberdrop is able to run in the current python version
    msg = "main UI started successfully"

    def main_ui(*_: object) -> None:
        print(msg)

    with pytest.MonkeyPatch.context() as m:
        m.setattr(program_ui, "run", main_ui)
        run_cdl(["interactive"])
        captured = capsys.readouterr()
        output = captured.out
        assert msg in output


def test_async_startup(tmp_cwd: Path, caplog: pytest.LogCaptureFixture) -> None:
    file = "URLs.txt"
    (tmp_cwd / file).touch()
    run_cdl(("download", "--input-file", file))
    assert "Finished downloading. Enjoy :)" in caplog.text
