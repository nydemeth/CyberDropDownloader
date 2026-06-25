# Contributing

## Reporting issues

Search for existing issues before creating a new one. If a bug already has issue, comment on the existing issue
with extra information that might help reproduce or fix the problem. Duplicate issues will be closed with a
reference to the existing issue.

You _should_ [read the wiki](https://script-ware.gitbook.io/cyberdrop-dl/frequently-asked-questions) as it
includes solutions to some common problems.

If your issue is a bug and hasn't been reported, open a new issue at <https://github.com/Cyberdrop-DL/cyberdrop-dl/issues/new/choose>.

## Feature requests

You _may_ request a new feature by [opening an issue](#submitting-an-issue). If you would like to _implement_ a new feature,
you _should_ open an issue or a discussion with a proposal first and at least one use case. You _may_ submit a PR directly if your feature is small
with a narrow scope.

## Setting up the development environment

`cyberdrop-dl` uses `uv` as a project management tool and requires python 3.12+. You can install it from <https://docs.astral.sh/uv/getting-started/installation/>.

You do not need to manually install install python as `uv` will automatically install a compatible python version (if required).

Once you have `uv` installed, follow these steps:

1. Clone the repo

   ```sh
   git clone "https://github.com/Cyberdrop-DL/cyberdrop-dl"
   cd cyberdrop-dl
   ```

1. Install the project and its dependencies

   ```sh
   uv sync --all-extras
   ```

1. Install the pre-commit hooks:

   ```sh
   uv run prek install
   ```

1. Optionally, run the tests suite to make sure your dev environment is setup correctly

```sh
   uv run pytest -v
```

## Code Style

### Standards

- Formatting:

This project uses [ruff](https://docs.astral.sh/ruff) for formatting, linting and import sorting.
We recommend [setting up your IDE](https://docs.astral.sh/ruff/editors/) to format and check with `ruff`, but you can always run

`uv run ruff check --fix` then `uv run ruff format` in the root directory before submitting a pull request.

- Type checking:

Not enforced but highly recommended. The project includes hardcoded config options for [`basedpyright`](https://docs.basedpyright.com/latest)

- Line width:

120 character max

The project includes predefined [settings for the zed editor](https://github.com/Cyberdrop-DL/cyberdrop-dl/tree/main/.zed)
with formatting options and a recipe to quickly launch CDL in debug mode for testing

### Code formatting with pre-commit hooks

This project uses git pre-commit hooks to perform formatting and linting before a commit is created,
to ensure consistent style and catch some common issues early on.

Once installed, hooks will run every time you commit. If the formatting isn't quite right or a linter catches something,
the commit will be rejected and `ruff` will try to fix the files. If `ruff` can not fix all the issues,
you will need to look at the output and fix them manually. When everything is fixed (either by `ruff` itself or manually)
all you need to do is `git add` those files again and retry your commit.

## Implementing new changes

> [!NOTE]
> `cyberdrop-dl` requires python 3.12+. You _must_ not use any syntax features not compatible with it

### Submitting a Pull Request (PR)

> [!IMPORTANT]  
> Before you start writing any code, you _should_ search the [repository](https://github.com/Cyberdrop-DL/cyberdrop-dl/pulls) for an open or closed PR
> that relates to your submission. You don't want to duplicate effort.

- Checkout a _new_ branch before working on any changes, branching from `main`. You _must not_ work directly on `main`
- Implement your changes. Make sure to follow [code style conventions](#code-style). You _should_ add tests for any new functionality you introduce
- Commit your changes using a descriptive commit message
- Fork the repository on GitHub, push your branch to your fork and open a pull request against the `main` branch of base repository.
- Make sure your pull request has a descriptive title and a short description. Sometimes the title of the PR is enough and no description is required
- You _must not_ use AI to generate your PR title/description. Write it with your own words
- Wait for a maintainer to review your PR and then address any comments they might have.

If everything is okay, your changes will be merged into the project.

### Adding support for a new site

There's no standard template for a new crawler, but there are a few conventions. You _should_ look at the code of another (hopefully similar) crawler
and based your crawler on that. A simple crawler to use as base is [CloudFlareStream](cyberdrop_dl/crawlers/cloudflare_stream.py).

- All crawlers _must_ inherit from the [base crawler](cyberdrop_dl/crawlers/crawler.py).
- All Crawlers _must_ have the word `Crawler` at the end of their class name
- All Crawlers _must_ override the `fetch` method. It's the primary method that decides what to do with an URL that matches with that crawler
- You _must_ not call any method that may fail (raise an exception) from within `fetch`
- All async method called from within fetch _must_ be public methods
- All public method _must_ be decorated with `error_handling_wrapper` to catch any unknown error
- You _should_ catch **expected** errors and re-raise them as a `ScrapeError` with an appropiate code and message
- You _should_ use valid HTTP codes for any `ScrapeError`. ex: raise `ScrapeError(410)` if you know a file was deleted
- You _may_ use HTTP code `422` (Unprocessable entity) for **expected** errors if no other HTTP code feels adequate
- You _may_ use a short string instead of an HTTP code to convey a better context for error (if required).
  The string _must_ 20 characters or less as it will be shown on the `Scrape Errors` sections of the TUI
- You _should not_ write logic in a defensive way for **unexpected** errors. If you need to perform an operation that _may_ fail
  but is not **expected** to fail (ex: a dictionary key lookup on an API response), do not try to catch the exception, let it bubble up.
  It will eventually be logged by the `error_handling_wrapper`
- You _should_ model site specific data into dataclasses, if possible
- You _must_ create a new task for any coroutine whose result is not needed to complete the current task
- You _must not_ create `MediaItem` objects manually. You _must_ use the `handle_file` method
- You _should_ look at all methods on the base crawler for possible helper functions. Their doctrings explain expected usage of each one.
- You _may_ add site specific CLI/config options at `cyberdrop_dl/config/crawlers.py`[cyberdrop_dl/config/crawlers.py] to use within the crawler.
- You _should_ not added unless absolutely required
- You _should_ add at least 1 test case for the crawler

#### Creating tests for a new site

1. Create a file with the name `URLs.txt` at the root of the repo
2. Paste all the URLs you want to test inside the file
3. Run [scripts/tools/make_test_cases.py](scripts/tools/make_test_cases.py). If successful, it will generate a file at [tests/crawlers/test_cases](tests/crawlers/test_cases)
4. Check that the scraped data matches the expected result
5. Rename the generated test file, from `test_case_<domain>.py` to just `<domain>.py`
6. Run the test again manually to confirm it it is reproducible:

```sh
uv run pytest -x --test-crawlers <domain>
```
