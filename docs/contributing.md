# Contributing

Contributions are welcome!

[tox](https://github.com/tox-dev/tox) is used for full test runs. Packaging
metadata lives in `pyproject.toml` and versions come from `setuptools-scm`.

## Development

To get going locally, simply do this:

```console
git clone https://github.com/zsimic/mgit.git
cd mgit

uv sync

# You have a venv now in ./.venv
source .venv/bin/activate
which python
which mgit
mgit

deactivate
```

## Running The Tests

Fast local checks:

```console
.venv/bin/pytest -q
ruff check
```

Full confidence check:

```console
tox
```

Useful focused tox runs:

- `tox -e py39` for the minimum supported Python version.

- `tox -e py314` for the newest supported Python version.

- `tox -e style` for packaged lint/type checks.

- `tox -e docs` for a strict `README.rst` parse check.

## Test Coverage

Run `tox`, then open `.tox/test-reports/htmlcov/index.html`.
