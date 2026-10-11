# Contributing

Contributions are welcome. [tox](https://github.com/tox-dev/tox) drives the full test run,
packaging metadata lives in `pyproject.toml`, and versions come from git tags via `setuptools-scm`.

## Get going locally

```shell
git clone https://github.com/zsimic/mgit.git  # or your own fork
cd mgit
uv sync  # creates ./.venv, with mgit installed in editable mode
.venv/bin/mgit --help
```

## Running the tests

`.venv/bin/pytest` for quick iterations, `tox` for the whole thing: the same environments CI runs.
Its `envlist` covers only the oldest and newest supported Python versions, to keep local runs
fast. `tox -l` lists every environment, and `tox.ini` is the authority on what each one does.

For coverage, run `tox`, then open `.tox/test-reports/htmlcov/index.html`.

## Before you open a PR

`tox -e style` must pass, `tox -e reformat` applies the mechanical fixes. Each type checker has a
tox environment named after it (`tox -e <typechecker>`): the ones CI runs (see `.github/workflows/`)
must pass too, the others are a second opinion.
