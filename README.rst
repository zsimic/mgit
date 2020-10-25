Fetch collections of git projects
=================================

.. image:: https://img.shields.io/pypi/v/mgit.svg
    :target: https://pypi.org/project/mgit/
    :alt: Version on pypi

.. image:: https://github.com/zsimic/mgit/workflows/Tests/badge.svg
    :target: https://github.com/zsimic/mgit/actions
    :alt: Tested with Github Actions

.. image:: https://codecov.io/gh/zsimic/mgit/branch/master/graph/badge.svg
    :target: https://codecov.io/gh/zsimic/mgit
    :alt: Test code codecov

.. image:: https://img.shields.io/pypi/pyversions/mgit.svg
    :target: https://pypi.org/project/mgit/
    :alt: Python versions tested


Overview
========

With ``mgit``, you can pull/fetch several projects at once,
and also auto-cleanup dangling branches (from past pull requests).

A colored output is provided if possible, ``mgit`` should come in handy in general for:

- quickly getting an overview of what's up with N git projects
- fetch/pull N git objects at once
- clone missing projects (useful if you tend to clone projects from same remote in one common folder)


Example usage
=============

``mgit`` can show you what's the status of all your git projects in a folder, for example my repos::

    ~/dev/github: mgit
    ~/dev/github: 4 github/zsimic
         mgit: [master] up to date
      pickley: [master] 1 diff, up to date*  last fetch 1w 4d ago
        runez: [master] up to date*  last fetch 1w 4d ago
    setupmeta: [master] up to date*  last fetch 3d 23h ago


Here we can see that:

- There are 4 git repos in folder ``~/dev/github``

- All 4 come from ``github/zsimic``

- 3 of them haven't been fetched in a while

We can fetch them all at once with ``--fetch`` (or ``-f``)::

    ~/dev/github: mgit --fetch
    ~/dev/github: 4 github/zsimic
         mgit: [master] up to date
      pickley: [master] 1 diff, up to date
        runez: [master] behind 2
    setupmeta: [master] up to date


Now all projects have been refreshed, and we can see there's nothing new in 2 of them,
but one is 2 commits behind (ie: 2 commits are on the remote, not pulled yet).
The output also shows that one of the projects has uncommitted files.

Modified files are shown (by default) if only one project is in scope, for example::

    ~/dev/github: mgit pickley
    pickley: [master] 1 diff, up to date
       M tox.ini


Above, we can see that the modified file in question is ``tox.ini`` in that project.
We can get the same effect using the ``--verbose`` (or ``-v``) flag,
like for example with 2 projects with modified files::

    ~/dev/github: mgit -v
    ~/dev/github: 4 github/zsimic
    mgit: [master] 1 diff, up to date
       M README.rst
    pickley: [master] 1 diff, up to date
       M tox.ini
    runez: [master] up to date
    setupmeta: [master] up to date


Synopsis::

    ~/dev/github: mgit --help
    Usage: mgit [OPTIONS] [TARGET]

      Fetch collections of git projects

    Options:
      --version                       Show the version and exit.
      --debug                         Show debugging information.
      --color / --no-color            Use colors (on by default on ttys)
      --log PATH                      Override log file location.
      --clean [show|local|remote|all|reset]
                                      Auto-clean branches
      -f, --fetch                     Fetch from all remotes
      -p, --pull                      Pull from tracking remote
      -s, --short / -v, --verbose     Short/verbose output
      -cs                             Handy shortcut for '--clean show'
      -cl                             Handy shortcut for '--clean local'
      -cr                             Handy shortcut for '--clean remote'
      -ca                             Handy shortcut for '--clean all'
      -h, --help                      Show this message and exit.

Installation
============

Easiest way to get mgit is via pickley_ or pipx_::

    pickley install mgit


or::

    pipx install mgit


You can also compile from source::

    git clone https://github.com/zsimic/mgit.git
    cd mgit
    tox -e venv

    .venv/bin/mgit --help

    source .venv/bin/activate
    mgit --help


.. _pickley: https://pypi.org/project/pickley/

.. _pipx: https://pypi.org/project/pipx/
