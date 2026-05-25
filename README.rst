mgit
====

A small companion for humans who like tidy git checkouts.

.. image:: https://img.shields.io/pypi/v/mgit.svg
    :target: https://pypi.org/project/mgit/
    :alt: Version on pypi

.. image:: https://github.com/zsimic/mgit/workflows/Tests/badge.svg
    :target: https://github.com/zsimic/mgit/actions
    :alt: Tested with Github Actions

.. image:: https://img.shields.io/pypi/pyversions/mgit.svg
    :target: https://pypi.org/project/mgit/
    :alt: Python versions tested


What it is
==========

``mgit`` is a tiny CLI for people who like their git checkouts clean, current,
and easy to scan. It gives you a quick read on one repo, or on every repo
directly inside a workspace folder.

- What state did I leave this checkout in?
- Can I pull, or did I leave work pending here?
- Is a merged branch still hanging around, waiting to be cleaned?
- I just wrapped up a branch; can I safely get back to ``main`` and clear it away?

``mgit`` is not a git replacement. It is the compact, careful layer for those
ordinary moments where you would rather see the answer than reconstruct it
from a handful of commands.


The rhythm
==========

Start with a glance::

    mgit        # show status here, or across a workspace

Refresh or move forward only when you mean to::

    mgit f      # fetch --all --prune, then show the refreshed status
    mgit p      # pull --rebase, but never over pending work

And for the wonderfully common ``PR merged`` moment::

    mgit g      # fetch, return to the default branch, pull, clean this branch

The short names are the intended interface:

- ``status`` / ``s``: show whether anything here needs attention. This is the default.
- ``fetch`` / ``f``: refresh remote refs, then show what changed.
- ``pull`` / ``p``: pull with rebase only when pending work will not be disturbed.
- ``main`` / ``m``: checkout the default branch, even if it is ``master``.
- ``branches`` / ``b``: list local branches with useful small annotations.
- ``groom`` / ``g``: safely finish with the merged branch you are currently on.

The command shape is::

    mgit [-v] [--color auto|always|never] [COMMAND] [FOLDER]

You can pass a folder to most commands::

    mgit ~/github
    mgit f ~/github
    mgit g ~/github/mgit

Workspace scans are shallow on purpose: ``mgit ~/github`` inspects direct
children like ``~/github/*/.git`` and does not crawl nested folders.


What you see
============

A workspace stays pleasantly skimmable::

        mgit: main ✅
     pickley: main ☑️ [+1🪦] ⌛4w 6d
       runez: feature 🪦 ✏️1
    detached: HEAD 👻

In one glance you get:

- the current branch
- local diffs and untracked files
- ahead/behind/gone tracking state
- fetch freshness
- a compact hint that a stale local branch is still lurking

``✅`` means recently refreshed, ``☑️`` means the local picture may be older,
``⌛`` calls out notably stale fetch information, a branch-level ``🪦`` means
its upstream is gone, and ``👻`` means detached ``HEAD``. A bracket such as
``[+2🪦+1]`` says that, besides the current and default branches, two local
branches have been proven cleanable and one remains.

For a single checkout, status also prints the pending paths. Workspace output
keeps to one line per repo, so you can keep checking a directory full of
projects without turning the terminal into a log dump::

    mgit ~/github/mgit

Color is automatic on terminals and can be controlled explicitly::

    mgit --color auto
    mgit --color always
    mgit --color never


Safety model
============

``mgit`` is read-only by default. Asking how things look does not change your repos.

Commands that act are explicit:

- ``mgit f`` updates local remote refs with ``git fetch --all --prune``.
- ``mgit p`` pulls with rebase only when the checkout passes safety checks.
- ``mgit g`` fetches, verifies that the current branch can be cleaned before
  switching branches, pulls safely, and deletes that local branch only. If it
  still exists on ``origin``, it deletes that one remote branch only after
  independently proving that the fetched remote ref is merged or
  content-equivalent to the fetched default branch; an exact-ref lease prevents
  deleting a branch that advanced meanwhile. No other branch is deleted.
  When already on the default branch, it fetches and reports that fact without
  pulling or cleaning branches. Use ``mgit m`` when you only want to switch to
  the default branch.


Coming next
===========

A larger convenience waiting in the wings is ``mgit clone``: give it a full
repo URL and let ``mgit`` choose the local destination from simple config
rules.

Planned config shape::

    locations = [
        { match = "github.com/zsimic/*", dir = "~/github" },
        { match = "github.com/*",        dir = "~/ext" },
        { match = "git.mycompany.com/*", dir = "~/dev" },
    ]

The goal is predictable placement without memorizing where each family of repos
belongs. Status, fetch, pull, main, and groom do not require any mgit config.


Install
=======

Install with pickley_ or pipx_::

    pickley install mgit

or::

    pipx install mgit

Install from a checkout for development::

    git clone https://github.com/zsimic/mgit.git
    cd mgit
    uv sync
    .venv/bin/mgit --help


Develop
=======

Fast local checks::

    .venv/bin/pytest -q
    ruff check

Full confidence check::

    tox


.. _pickley: https://pypi.org/project/pickley/

.. _pipx: https://pypi.org/project/pipx/
