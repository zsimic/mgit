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


Example usage
=============

``mgit`` can show you what's the status of all your git projects in a folder, for example my repos::

    ~/dev/github: mgit
    ~/dev/github: 4 github/zsimic
         mgit: [master] up to date
      pickley: [master] 1 diff, up to date*  last fetch 3w 4d ago
        runez: [master] up to date*  last fetch 3w 4d ago
    setupmeta: [master] up to date*  last fetch 4d 23h ago


Here we can see that I have 4 repos in ``~/dev/github``, 3 of them haven't been fetched in a while.
We can fetch them all at once like so::

    ~/dev/github: mgit --fetch
    ~/dev/github: 4 github/zsimic
         mgit: [master] up to date
      pickley: [master] 1 diff, up to date
        runez: [master] up to date
    setupmeta: [master] up to date

Now all projects have been refreshed, and we can see there's nothing new
(otherwise we'd see a mention of the form ``2 commits behind``).
The output also shows that one of the projects has uncommitted files.


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
