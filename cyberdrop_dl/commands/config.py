from cyclopts import App

from cyberdrop_dl.commands import CLIarguments, open_folder
from cyberdrop_dl.config import Config
from cyberdrop_dl.config.appdata import AppData
from cyberdrop_dl.prompts import ask_should_create_config

app = App(name="config", help="Config file operations")


@app.command()
def file(*, cli: CLIarguments | None = None) -> None:
    "Show path to the config file"
    file = (cli and cli.config_file) or AppData.default().config_file
    app.console.print(file)


@app.command()
def edit(*, cli: CLIarguments | None = None) -> None:
    "Open the default config file on a text editor"
    from cyberdrop_dl.utils import text_editor

    file = cli and cli.config_file
    if not file:
        file = AppData.default().config_file
        if not file.exists():
            if not ask_should_create_config(file):
                return
            Config().save_to(file)

    text_editor.open(file)


@app.command()
def new() -> None:
    "Create a new config with default options and print it"
    app.console.print(Config().dump_yaml(), soft_wrap=True)


@app.command(name="dir", alias="folder")
def folder(*, cli: CLIarguments | None = None) -> None:
    "Open folder with config file in default file explorer"
    file = (cli and cli.config_file) or AppData.default().config_file

    open_folder(file.parent)
