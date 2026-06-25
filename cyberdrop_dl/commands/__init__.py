import dataclasses
from collections.abc import Sequence
from pathlib import Path
from typing import Annotated

from cyclopts import Parameter, Token, validators

from cyberdrop_dl.models.types import HttpURL


def _resolve_path(type_: type[Path], tokens: Sequence[Token]) -> Path:
    assert len(tokens) == 1
    return type_(tokens[0].value).resolve()


def file_validator(ext: str | tuple[str, ...], *, exists: bool = True) -> Parameter:
    return Parameter(validator=validators.Path(exists=exists, dir_okay=False, ext=ext), converter=_resolve_path)


type YAMLFile = Annotated[Path, file_validator((".yaml", ".yml"))]
type JSONFile = Annotated[Path, file_validator(".json")]
type SQLiteFile = Annotated[Path, file_validator(".db")]


@Parameter(name="*")
@dataclasses.dataclass(slots=True)
class CLIarguments:
    urls: Annotated[tuple[HttpURL, ...], Parameter(show=False)] = ()

    config_file: YAMLFile | None = None
    "YAML file to use as config"

    cache_file: JSONFile | None = None
    "JSON file to use as cache"

    database_file: SQLiteFile | None = None
    "SQLite file to use as database"
