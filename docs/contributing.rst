Contributions are welcome!

tox_ is used for full test runs. Packaging metadata lives in
``pyproject.toml`` and versions come from ``setuptools-scm``.

Development
===========

To get going locally, simply do this::

    git clone https://github.com/zsimic/mgit.git
    cd mgit

    uv sync

    # You have a venv now in ./.venv
    source .venv/bin/activate
    which python
    which mgit
    mgit

    deactivate


Running the tests
=================

Fast local checks::

    .venv/bin/pytest -q
    ruff check

Full confidence check::

    tox

Useful focused tox runs:

* ``tox -e py39`` for the minimum supported Python version.

* ``tox -e py314`` for the newest supported Python version.

* ``tox -e style`` for packaged lint/type checks.


Test coverage
=============

Run ``tox``, then open ``.tox/test-reports/htmlcov/index.html``


.. _pyenv: https://github.com/pyenv/pyenv

.. _tox: https://github.com/tox-dev/tox
