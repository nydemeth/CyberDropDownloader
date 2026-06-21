from typing import Annotated

from cyclopts import Parameter
from cyclopts.types import ResolvedExistingFile

from cyberdrop_dl.models import ConfigModel
from cyberdrop_dl.models.types import HttpURL


@Parameter(name="*")
class CLIarguments(ConfigModel):
    urls: Annotated[tuple[HttpURL, ...], Parameter(show=False)] = ()

    config_file: ResolvedExistingFile | None = None
    "YAML file to use as config"

    cache_file: ResolvedExistingFile | None = None
    "JSON file to use as cache"

    database_file: ResolvedExistingFile | None = None
    "SQLite file to use as database"
