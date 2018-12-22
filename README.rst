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
      pickley: [master] 1 diff, up to date*  last fetch 3w 4d ago
        runez: [master] up to date*  last fetch 3w 4d ago
    setupmeta: [master] up to date*  last fetch 4d 23h ago


Here we can see that I have 4 repos in ``~/dev/github`` (and all 4 come from ``github/zsimic``),
3 of them haven't been fetched in a while.
We can fetch them all at once with ``--fetch`` (or ``-f``)::

    ~/dev/github: mgit --fetch
    ~/dev/github: 4 github/zsimic
         mgit: [master] up to date
      pickley: [master] 1 diff, up to date
        runez: [master] up to date
    setupmeta: [master] up to date


Now all projects have been refreshed, and we can see there's nothing new
(otherwise we'd see a mention of the form ``2 commits behind``).
The output also shows that one of the projects has uncommitted files.

Modified files are shown if only one project is in scope, for example::

    ~/dev/github: mgit pickley
    pickley: [master] 1 diff, up to date
       M tox.ini


Above, we can see that the modified file in question is ``tox.ini`` in that project.
We can get the same effect using the ``-verbose`` (or ``-v``) flag,
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

      Manage git projects en masse

    Options:
      --version                       Show the version and exit.
      --debug                         Show debugging information
      --color / --no-color            Use (or not) colors (on by default on tty)
      --ignore action[:what]          Show/add/remove/clear ignores
      --clean [show|local|remote|all|reset]
                                      Auto-clean branches
      -a, --all                       Examine all repos, even missing git checkouts
      -f, --fetch                     Fetch from all remotes
      -p, --pull                      Pull from tracking remote, clone missing with --all
      -s, --short / -v, --verbose     Short/verbose output
      -cs                             Handy shortcut for '--clean show'
      -cl                             Handy shortcut for '--clean local'
      -cr                             Handy shortcut for '--clean remote'
      -ca                             Handy shortcut for '--clean all'
      -h, --help                      Show this message and exit.

      Advanced usage:
        --clean show                  Show which local/remote branches can be cleaned
        --clean local                 Clean local branches that were deleted from their corresponding remote
        --clean remote                Clean merged remote branches
        --clean all                   Clean local and merged remote branches
        --clean reset                 Do a git --reset --hard + clean -fdx (nuke all changes, get back to pristine state)

        --ignore show                 Show ignores currently in effect
        --ignore add 'hackday.*'      Add an ignore regex, for example here 'hackday.*'
        --ignore remove 'hackday.*'   Remove an ignore regex, for example here 'hackday.*'
        --ignore clean                Remove all ignores


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
