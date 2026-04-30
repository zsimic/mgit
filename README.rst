mgit
====

Small git-workspace convenience.

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

``mgit`` is a tiny CLI for people who keep several git checkouts side by side.
It gives you a quick read on one repo, or on every repo directly inside a
workspace folder.

The sweet spot is the daily loop:

- Which repos have local changes?
- Which repos have not fetched in a while?
- Which branches are behind, ahead, gone, or ready to clean up?
- After a PR is merged, can I get back to the default branch and prune the old
  local branch safely?

``mgit`` is intentionally not a git replacement. It is a small quality-of-life
layer around common inspection and grooming tasks.


The workflow
============

Run ``mgit`` with no command to inspect the current repo or workspace::

    mgit

Fetch first, then decide what to do::

    mgit f      # fetch --all --prune, then show status
    mgit p      # pull --rebase, only when the repo is safe to pull

Clean up after a branch is merged::

    mgit g      # fetch, return to the default branch, pull, prune stale locals

The short aliases are the intended interface:

- ``status`` / ``s``: show repo or workspace status. This is the default.
- ``fetch`` / ``f``: refresh remote refs, then report status.
- ``pull`` / ``p``: pull with rebase when the worktree is clean.
- ``main`` / ``m``: checkout the default branch, even if it is ``master``.
- ``groom`` / ``g``: local-only cleanup workflow for stale local branches.

You can pass a target path to most commands::

    mgit ~/github
    mgit f ~/github
    mgit g ~/github/mgit

Workspace scans are shallow on purpose: ``mgit ~/github`` inspects direct
children like ``~/github/*/.git`` and does not crawl nested folders.


Output
======

A workspace summary looks like this::

    ~/github: 4 github/zsimic
         mgit: [main] up to date
      pickley: [main] 1 diff, up to date  last fetch 4w 6d ago
        runez: [main] behind 2
    setupmeta: [main] up to date

In one glance you get:

- the current branch
- local diffs and untracked files
- ahead/behind/gone tracking state
- fetch freshness
- stale local branch notes

Use verbose mode when you want paths, not just counts::

    mgit -v
    mgit -v ~/github/mgit

Color is automatic on terminals and can be controlled explicitly::

    mgit --color auto
    mgit --color always
    mgit --color never


Safety model
============

``mgit`` is read-only by default. Status inspection does not change your repos.

Commands that act are explicit:

- ``mgit f`` updates local remote refs with ``git fetch --all --prune``.
- ``mgit p`` pulls with rebase only when pending local changes would not make
  that risky.
- ``mgit g`` is local-only: it does not delete remote branches. It fetches,
  moves back to the default branch, pulls safely, and deletes only local
  branches whose tracked remote branch is gone.

Remote branch deletion and reset-style cleanup are intentionally not part of
the first v2 command set.


Clone routing
=============

The next larger convenience is ``mgit clone``: give it a full repo URL and let
``mgit`` choose the local destination from simple config rules.

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
