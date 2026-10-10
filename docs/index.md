# mgit internal docs

The *inside view* of the mgit repo, for people (and coding agents) working **on** it. Users want
the [README](../README.rst), which also says what each command does.

mgit is an argparse CLI with `runez` as its only dependency. All of it lives in `src/mgit/`:

- `cli.py` — the commands. Each one is a `CliCommand` subclass registered with `@cli_command`: its
  name comes from the class name, `short_name` is its alias, the docstring's first line its help.
  `FolderTargetCommand.target()` decides between one checkout (`GitDir`) and a workspace folder
  (`ProjectDir`, every git checkout directly inside it). Start reading at `main()`:
  `normalized_cli_args()` is why a bare `mgit`, or `mgit <folder>`, means `status`.
- `git.py` — everything that talks to git. `GitDir` runs the commands and holds two lazily built
  snapshots, `GitStatus` and `GitRefs` (branches as `BranchInfo`), see [design notes](./design.md).
  `Reporter` formats output and aborts.

Tests drive the CLI end to end against throwaway git repos created by the fixtures in
`tests/conftest.py`.

`tox.ini` is the hub: every check is a tox environment, and the GitHub workflows only call them.

## Pages

- [Contributing](./contributing.md) — local setup, running tests and checks.
- [Design notes](./design.md) — the cached git state, and what invalidates it.
