from __future__ import annotations

import os
from pathlib import Path

from mgit.cli import normalized_cli_args


def test_command_help(cli):
    cli.run("--help")
    assert cli.succeeded
    assert "Commands:" in cli.logged
    assert "status (s)" in cli.logged

    cli.run("s --help")
    assert cli.succeeded
    assert "usage: mgit status" in cli.logged
    assert "Show repo or workspace status." in cli.logged
    assert "folder" in cli.logged


def test_cli_arg_normalization():
    assert normalized_cli_args([]) == ["status"]
    assert normalized_cli_args(["workspace"]) == ["status", "workspace"]
    assert normalized_cli_args(["f", "workspace"]) == ["fetch", "workspace"]
    assert normalized_cli_args(["--color=always", "g", "checkout"]) == ["--color=always", "groom", "checkout"]


def test_abort_reporting(cli):
    cli.run("--color")
    assert cli.failed
    assert "argument --color: expected one argument" in cli.logged.stderr

    cli.run("-z")
    assert cli.failed
    assert "error: unrecognized arguments: -z" in cli.logged.stderr

    cli.run("--color never missing")
    assert cli.failed
    assert "No folder" in cli.logged

    Path("folder").mkdir()
    cli.run("main folder")
    assert cli.failed
    assert "main only supports one git checkout" in cli.logged

    cli.run("folder")
    assert cli.failed
    assert "no git folders" in cli.logged


def test_workspace_status_lists_child_checkouts(cli, git):
    git.init("my-workspace/short")
    git.init("my-workspace/longer-name")

    cli.run("my-workspace")

    assert cli.succeeded
    assert "my-workspace:" in cli.logged
    assert "short: main ✅" in cli.logged
    assert "longer-name: main ✅" in cli.logged


def test_single_status_shows_pending_paths_and_discovers_parent_checkout(cli, git):
    repo = git.init("repo")
    repo.write_file("README.md", "changed")
    repo.write_file("new.txt", "new")

    cli.run("repo")
    assert cli.succeeded
    assert "main ☑️ ✏️1 🆕1" in cli.logged
    assert "README.md" in cli.logged
    assert "new.txt" in cli.logged

    (repo.cwd / "foo").mkdir()
    os.chdir(repo.cwd / "foo")
    cli.run()
    assert cli.succeeded
    assert "README.md" in cli.logged
    assert "new.txt" in cli.logged

    cli.run(".")
    assert cli.failed
    assert "repo/foo: no git folders" in cli.logged


def test_verbose_enables_debug_logging(cli, git):
    git.init("repo")

    cli.run("repo")
    assert cli.succeeded
    assert "DEBUG Running:" not in cli.logged

    cli.run("-v repo")
    assert cli.succeeded
    assert "DEBUG Running:" in cli.logged


def test_branches_workspace_lists_local_branches(cli, git):
    git.init("workspace/one")
    two = git.init("workspace/two")
    two.checkout("-b", "topic")

    cli.run("branches workspace")

    assert cli.succeeded
    assert "one:" in cli.logged
    assert "two:" in cli.logged
    assert "* topic" in cli.logged
    assert "[default]" in cli.logged
    assert "[orphaned]" in cli.logged


def test_pull_workspace_recaps_each_checkout(cli, git):
    foo_source = git.seeded_set("foo-source")
    bar_source = git.seeded_set("bar-source")
    foo = git.clone(foo_source.remote_url, "workspace/foo")
    git.clone(bar_source.remote_url, "workspace/bar-baz")
    foo_source.seed.commit_file("next.txt", "next", "next")
    foo_source.seed.push()
    foo.run_git("fetch")

    cli.run("pull workspace")

    assert cli.succeeded
    assert "foo: main ✅ (was behind 1)" in cli.logged
    assert "bar-baz: main ✅ (was up-to-date)" in cli.logged
    assert foo.run_git("rev-parse", "HEAD") == foo.run_git("rev-parse", "origin/main")


def test_main_checks_out_default_branch(cli, git):
    repo = git.init("repo")
    repo.checkout("-b", "feature")

    cli.run("m repo")

    assert cli.succeeded
    assert repo.current_branch == "main"
