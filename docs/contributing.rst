Contributions are welcome!

tox_ is used for building and testing, ``setup.py`` is kept simple thanks to setupmeta_.

Development
===========

To get going locally, simply do this::

    git clone https://github.com/zsimic/mgit.git
    cd mgit

    tox -e venv

    # You have a venv now in ./.venv, use it, open it with pycharm etc
    source .venv/bin/activate
    which python
    which mgit
    mgit

    deactivate


Running the tests
=================

To run the tests, simply run ``tox``, this will run tests against all python versions you have locally installed.
You can use pyenv_ for example to get python installations.

Run:

* ``tox -e py38`` (for example) to limit test run to only one python version.

* ``tox -e style`` to run style checks only

* etc


Test coverage
=============

Run ``tox``, then open ``.tox/test-reports/htmlcov/index.html``


.. _pyenv: https://github.com/pyenv/pyenv

.. _tox: https://github.com/tox-dev/tox

.. _setupmeta: https://pypi.org/project/setupmeta/
