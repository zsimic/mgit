from __future__ import annotations

import os
import subprocess
from pathlib import Path
from textwrap import dedent

import runez

from mgit.cli import normalized_cli_args


def git(cwd: str | Path | None, *args, check=True) -> str:
    cmd = ["git"]
    if cwd:
        cmd.append("-C")
        cmd.append(str(cwd))

    cmd.extend(args)
    proc = subprocess.run(cmd, check=check, capture_output=True, text=True)  # noqa: S603
    return proc.stdout.strip()


def git_init(*args):
    git(None, "init", *args)


def git_clone(*args):
    git(None, "clone", *args)


def make_checkout(base: Path | str):
    base = runez.to_path(base)
    base.mkdir(parents=True, exist_ok=True)
    remote = base / "remote.git"
    seed = base / "seed"
    work = base / "work"

    git_init("--bare", "--initial-branch=main", str(remote))
    git_init("--initial-branch=main", str(seed))
    git(seed, "config", "user.email", "tester@example.com")
    git(seed, "config", "user.name", "Test User")
    (seed / "README.md").write_text("hello\n")
    git(seed, "add", "README.md")
    git(seed, "commit", "-m", "initial")
    remote_url = str(remote.resolve())
    git(seed, "remote", "add", "origin", remote_url)
    git(seed, "push", "-u", "origin", "main")
    git_clone(remote_url, str(work))
    git(work, "config", "user.email", "tester@example.com")
    git(work, "config", "user.name", "Test User")
    return work


def make_repo(path: Path | str):
    path = runez.to_path(path)
    git_init("--initial-branch=main", str(path))
    git(path, "config", "user.email", "tester@example.com")
    git(path, "config", "user.name", "Test User")
    (path / "README.md").write_text("Some description\n")
    git(path, "add", "README.md")
    git(path, "commit", "-m", "initial")
    return path


def make_stale_tracked_branch(work: Path):
    git(work, "checkout", "-b", "stale")
    git(work, "push", "-u", "origin", "stale")
    git(work, "checkout", "main")
    git(work, "push", "origin", "--delete", "stale")
    git(work, "checkout", "stale")


def commit_file(work: Path, name, text, message):
    (work / name).write_text(text)
    git(work, "add", name)
    git(work, "commit", "-m", message)


def make_unmerged_stale_tracked_branch(work: Path):
    git(work, "checkout", "-b", "unmerged")
    commit_file(work, "unmerged.txt", "still in progress\n", "unmerged work")
    git(work, "push", "-u", "origin", "unmerged")
    git(work, "checkout", "main")
    git(work, "push", "origin", "--delete", "unmerged")
    git(work, "checkout", "unmerged")


def make_squashed_stale_tracked_branch(work: Path):
    git(work, "checkout", "-b", "squashed")
    commit_file(work, "one.txt", "one\n", "one")
    commit_file(work, "two.txt", "two\n", "two")
    git(work, "push", "-u", "origin", "squashed")
    git(work, "checkout", "main")
    git(work, "merge", "--squash", "squashed")
    git(work, "commit", "-m", "squash squashed")
    git(work, "push", "origin", "main")
    git(work, "push", "origin", "--delete", "squashed")
    git(work, "checkout", "squashed")


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
    assert cli.exit_code == 1
    assert "No folder" in cli.logged

    Path("folder").mkdir()
    cli.run("main folder")
    assert cli.failed
    assert cli.exit_code == 2
    assert "main only supports one git checkout" in cli.logged

    cli.run("folder")
    assert cli.failed
    assert cli.exit_code == 1
    assert "no git folders" in cli.logged


def test_workspace_status_alignment(cli):
    make_repo("my-workspace/short")
    make_repo("my-workspace/longer-name")

    expected = dedent("""\
        my-workspace:
        longer-name: [main] up to date  no remotes; current branch 'main' is orphaned
              short: [main] up to date  no remotes; current branch 'main' is orphaned
    """)

    cli.run("my-workspace")
    assert cli.succeeded
    assert cli.logged.stdout.contents() == expected

    cli.run("-v my-workspace")
    assert cli.succeeded
    assert cli.logged.stdout.contents() == expected


def test_single_status_shows_pending_paths(cli):
    repo = make_repo("repo")
    (repo / "README.md").write_text("changed\n")
    (repo / "new.txt").write_text("new\n")

    # Refer to folder 'repo' specifically
    cli.run("repo")
    assert cli.succeeded
    assert "README.md" in cli.logged
    assert "new.txt" in cli.logged

    # Using '.', we end up with a ProjectDir with exactly one checkout
    cli.run(".")
    assert cli.succeeded
    assert "repo: [main] 1 diff, 1 untracked, up to date  no remotes; current branch 'main' is orphaned" in cli.logged

    # Grooming refused with pending changes
    cli.run("g repo")
    assert cli.failed
    assert "can't groom; pending changes; 1 diff; 1 untracked" in cli.logged

    # Convenience case: find .git/ from parent folder
    (repo / "foo").mkdir()
    os.chdir("repo/foo")
    cli.run(".")
    assert cli.succeeded
    assert "repo: [main] 1 diff, 1 untracked, up to date  no remotes; current branch 'main' is orphaned" in cli.logged

    # Running fetch from subfolder -> no op here
    cli.run("f")
    assert cli.succeeded


def test_verbose_enables_debug_logging(cli):
    make_repo("repo")

    cli.run("repo")
    assert cli.succeeded
    assert "DEBUG Running:" not in cli.logged

    cli.run("-v repo")
    assert cli.succeeded
    assert "DEBUG Running:" in cli.logged


def test_branches_single_repo(cli):
    make_repo("repo")
    git("repo", "checkout", "-b", "feature")

    cli.run("b repo")

    assert cli.succeeded
    assert cli.logged.stdout.contents() == dedent("""\
        * feature  [orphaned]
          main     [default]
    """)


def test_branches_workspace(cli):
    make_repo("workspace/one")
    make_repo("workspace/two")
    git("workspace/two", "checkout", "-b", "topic")

    cli.run("branches workspace")

    assert cli.succeeded
    assert cli.logged.stdout.contents() == dedent("""\
        one:
          * main  [default]
        two:
            main   [default]
          * topic  [orphaned]
    """)


def test_main_checks_out_default_branch(cli):
    work = make_checkout("checkout")
    git(work, "checkout", "-b", "feature")

    cli.run("m checkout/work")

    assert cli.succeeded
    assert git(work, "branch", "--show-current") == "main"


def test_groom_deletes_stale_tracked_branch(cli):
    work = make_checkout("checkout")
    make_stale_tracked_branch(work)

    cli.run("g checkout/work")

    assert cli.succeeded
    assert "deleted stale" in cli.logged
    assert git(work, "branch", "--show-current") == "main"
    assert not git(work, "branch", "--list", "stale")

    # Groom a 2nd time is a no-op
    cli.run("g checkout/work")
    assert cli.succeeded
    assert cli.logged.stdout.contents().strip() == "work: [main] up to date  already on main branch; no stale local branches"


def test_groom_preserves_unmerged_stale_tracked_branch(cli):
    work = make_checkout("checkout")
    make_unmerged_stale_tracked_branch(work)

    cli.run("g checkout/work")

    assert cli.failed
    assert cli.exit_code == 1
    assert "current branch can't be cleaned" in cli.logged
    assert git(work, "branch", "--show-current") == "unmerged"
    assert git(work, "branch", "--list", "unmerged")


def test_groom_deletes_squashed_stale_tracked_branch(cli):
    work = make_checkout("checkout")
    make_squashed_stale_tracked_branch(work)

    cli.run("g checkout/work")

    assert cli.succeeded
    assert "deleted squashed" in cli.logged
    assert git(work, "branch", "--show-current") == "main"
    assert not git(work, "branch", "--list", "squashed")


def test_groom_reports_already_on_default_branch(cli):
    work = make_checkout("checkout")

    cli.run("g checkout/work")

    assert cli.succeeded
    assert "already on main branch" in cli.logged
    assert git(work, "branch", "--show-current") == "main"


def test_groom_refuses_pending_changes(cli):
    work = make_checkout("checkout")
    make_stale_tracked_branch(work)
    (work / "scratch.txt").write_text("pending\n")

    cli.run("groom checkout/work")
    assert cli.failed
    assert cli.exit_code == 1
    assert "pending changes" in cli.logged
    assert git(work, "branch", "--show-current") == "stale"
    assert git(work, "branch", "--list", "stale")

    # Can't pull checkout/work (but 'seed' is OK)
    cli.run("pull checkout")
    assert cli.succeeded
    assert cli.logged.stdout.contents() == dedent("""\
        checkout:
        seed: [main] up to date
        work: [stale +1] 1 untracked  can't pull; remote branch gone
    """)
