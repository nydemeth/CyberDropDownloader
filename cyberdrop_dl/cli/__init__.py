from cyclopts import Parameter
from cyclopts.core import App
from cyclopts.help import DefaultFormatter

from cyberdrop_dl import __version__
from cyberdrop_dl.cli.clean_up import app as cleanup
from cyberdrop_dl.cli.database import app as database
from cyberdrop_dl.cli.hash import compute_hashes
from cyberdrop_dl.cli.main import download, interactive
from cyberdrop_dl.cli.report import report

app = App(
    name="cyberdrop-dl",
    help="Bulk asynchronous downloader for multiple file hosts",
    version=__version__,
    default_parameter=Parameter(negative_iterable=[], json_dict=False, json_list=False),
    result_action="return_value",
    help_formatter=DefaultFormatter().with_newline_metadata(),
)


@app.command
def show() -> None:
    """Show a list of all supported sites"""
    from cyberdrop_dl import supported_sites

    table = supported_sites.as_rich_table()
    app.console.print(table)


for cmd in download, database, interactive, cleanup, report:
    app.command(cmd)


app.command(compute_hashes, name="hash")
