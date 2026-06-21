from typing import Annotated

from cyclopts import App, Parameter
from cyclopts.types import ResolvedExistingFile

from cyberdrop_dl.config.appdata import AppData

app = App(name="database", help="Commands for managing the database")


@app.command()
def transfer(
    db_path: Annotated[
        ResolvedExistingFile,
        Parameter(help="Path to the SQLite database file to migrate"),
    ],
    *,
    force: Annotated[
        bool,
        Parameter(
            help="Skip the 'already latest' early-exit check and run all migration steps regardless of detected version"
        ),
    ] = False,
) -> None:
    """Migrate an old database to the latest schema version."""
    from cyberdrop_dl.database.transfer import run as transfer_db

    transfer_db(db_path, force=force)


@app.command()
def file() -> None:
    "Show path of default database"
    app.console.print(AppData.default().db_file)
