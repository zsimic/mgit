Manage git projects en masse
============================

.. image:: https://img.shields.io/pypi/v/mgit.svg
    :target: https://pypi.org/project/mgit/
    :alt: Version on pypi

.. image:: https://travis-ci.org/zsimic/mgit.svg?branch=master
    :target: https://travis-ci.org/zsimic/mgit
    :alt: Travis CI

.. image:: https://codecov.io/gh/zsimic/mgit/branch/master/graph/badge.svg
    :target: https://codecov.io/gh/zsimic/mgit
    :alt: codecov

.. image:: https://img.shields.io/pypi/pyversions/mgit.svg
    :target: https://github.com/zsimic/mgit
    :alt: Python versions tested (link to github project)


Overview
========

With ``mgit``, you can pull/fetch several projects at once,
and also auto-cleanup dangling branches (from past pull requests)

Installation
============

Easiest way to get mgit is via pickley_ or pipsi_::

    pickley install mgit

    pipsi install mgit


You can also compile from source::

    git clone https://github.com/zsimic/mgit.git
    cd mgit
    tox -e venv
    source .venv/bin/activate


.. _pickley: https://pypi.org/simple/pickley/

.. _pipsi: https://pypi.org/simple/pipsi/
