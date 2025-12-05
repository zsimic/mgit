Contributions are welcome!

tox_ is used for building and testing, ``setup.py`` is kept simple thanks to setupmeta_.

Development
===========

To get going locally, simply do this::

    git clone https://github.com/zsimic/mgit.git
    cd mgit

    uv venv
    uv pip install -r tests/requirements.txt -e .

    # You have a venv now in ./.venv, use it, open it with pycharm etc
    source .venv/bin/activate
    which python
    which mgit
    mgit

    deactivate


Running the tests
=================

To run the tests, simply run ``tox``.

Run:

* ``tox -e py314`` (for example) to limit test run to only one python version.

* ``tox -e style`` to run style checks only

* etc


Test coverage
=============

Run ``tox``, then open ``.tox/test-reports/htmlcov/index.html``


.. _pyenv: https://github.com/pyenv/pyenv

.. _tox: https://github.com/tox-dev/tox

.. _setupmeta: https://pypi.org/project/setupmeta/
