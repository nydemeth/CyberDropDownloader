import logging

from cyclopts import App

from cyberdrop_dl.config import Config
from cyberdrop_dl.config.appdata import AppData
from cyberdrop_dl.prompts import ask_should_create_config

app = App(name="config", help="Config file operations")
logger = logging.getLogger(__name__)


@app.command()
def file() -> None:
    "Show the default config file path"
    app.console.print(AppData.default().config_file)


@app.command()
def edit() -> None:
    "Open the default config file on a text editor"
    from cyberdrop_dl.utils import text_editor

    file = AppData.default().config_file
    if not file.exists():
        if not ask_should_create_config(file):
            return
        Config().save_to(file)

    text_editor.open(file)


@app.command()
def new() -> None:
    "Create a new config with default options and print it"
    app.console.print(Config().dump_yaml())
