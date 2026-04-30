import shutil
import subprocess
from pathlib import Path
from textwrap import dedent

import pytest

from mgit.cli import parse_cli_args
from mgit.commands import command_for, COMMANDS
from mgit.git import GitDir

GIT = shutil.which("git") or "git"


def git(cwd, *args, check=True):
    proc = subprocess.run(  # noqa: S603
        [GIT, "-C", str(cwd), *args],
        check=check,
        capture_output=True,
        text=True,
    )
    return proc.stdout.strip()


def git_init(*args):
    subprocess.run([GIT, *args], check=True, capture_output=True, text=True)  # noqa: S603


def make_checkout(base):
    base.mkdir(parents=True, exist_ok=True)
    remote = base / "remote.git"
    seed = base / "seed"
    work = base / "work"

    git_init("init", "--bare", "--initial-branch=main", str(remote))
    git_init("init", "--initial-branch=main", str(seed))
    git(seed, "config", "user.email", "tester@example.com")
    git(seed, "config", "user.name", "Test User")
    (seed / "README.md").write_text("hello\n")
    git(seed, "add", "README.md")
    git(seed, "commit", "-m", "initial")
    remote_url = str(remote.resolve())
    git(seed, "remote", "add", "origin", remote_url)
    git(seed, "push", "-u", "origin", "main")
    git_init("clone", remote_url, str(work))
    git(work, "config", "user.email", "tester@example.com")
    git(work, "config", "user.name", "Test User")
    return work


def make_repo(path):
    git_init("init", "--initial-branch=main", str(path))
    git(path, "config", "user.email", "tester@example.com")
    git(path, "config", "user.name", "Test User")
    (path / "README.md").write_text(f"{path.name}\n")
    git(path, "add", "README.md")
    git(path, "commit", "-m", "initial")


def make_stale_tracked_branch(work):
    git(work, "checkout", "-b", "stale")
    git(work, "push", "-u", "origin", "stale")
    git(work, "checkout", "main")
    git(work, "push", "origin", "--delete", "stale")
    git(work, "checkout", "stale")


def commit_file(work, name, text, message):
    (work / name).write_text(text)
    git(work, "add", name)
    git(work, "commit", "-m", message)


def make_unmerged_stale_tracked_branch(work):
    git(work, "checkout", "-b", "unmerged")
    commit_file(work, "unmerged.txt", "still in progress\n", "unmerged work")
    git(work, "push", "-u", "origin", "unmerged")
    git(work, "checkout", "main")
    git(work, "push", "origin", "--delete", "unmerged")
    git(work, "checkout", "unmerged")


def make_squashed_stale_tracked_branch(work):
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


def test_command_registry_core_slice():
    assert {command.name: command.aliases for command in COMMANDS} == {
        "status": ("s",),
        "fetch": ("f",),
        "pull": ("p",),
        "main": ("m",),
        "branches": ("b",),
        "groom": ("g",),
    }
    assert command_for("g").name == "groom"
    assert command_for("status").scope == "both"
    assert command_for("groom").scope == "single"


@pytest.mark.parametrize(
    ("argv", "command", "target"),
    [
        ([], "status", "."),
        (["status"], "status", "."),
        (["s"], "status", "."),
        (["fetch"], "fetch", "."),
        (["f"], "fetch", "."),
        (["pull"], "pull", "."),
        (["p"], "pull", "."),
        (["branches"], "branches", "."),
        (["b"], "branches", "."),
        (["groom"], "groom", "."),
        (["g"], "groom", "."),
        (["main"], "main", "."),
        (["m"], "main", "."),
        (["status", "repo"], "status", "repo"),
        (["repo"], "status", "repo"),
    ],
)
def test_parse_core_commands(argv, command, target):
    invocation = parse_cli_args(argv)
    assert invocation.command.name == command
    assert invocation.target == Path(target)


def test_parse_rejects_extra_targets(cli):
    cli.run("fetch one two")

    assert cli.failed
    assert cli.exit_code == 2
    assert "fetch accepts at most one target" in cli.logged


def test_workspace_status_alignment(cli):
    make_repo(Path("my-workspace/short"))
    make_repo(Path("my-workspace/longer-name"))

    expected = dedent("""\
        my-workspace: 2 unknown/unknown
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
    make_repo(Path("repo"))
    (Path("repo/README.md")).write_text("changed\n")
    (Path("repo/new.txt")).write_text("new\n")

    cli.run("repo")

    assert cli.succeeded
    assert "README.md" in cli.logged
    assert "new.txt" in cli.logged


def test_verbose_enables_debug_logging(cli):
    make_repo(Path("repo"))

    cli.run("repo")
    assert cli.succeeded
    assert "DEBUG Running:" not in cli.logged

    cli.run("-v repo")
    assert cli.succeeded
    assert "DEBUG Running: git -C repo config --list" in cli.logged
    assert "DEBUG Running: git -C repo branch --list --all" in cli.logged
    assert "DEBUG Running: git -C repo status --porcelain --branch" in cli.logged


def test_branches_single_repo(cli):
    make_repo(Path("repo"))
    git(Path("repo"), "checkout", "-b", "feature")

    cli.run("b repo")

    assert cli.succeeded
    assert cli.logged.stdout.contents() == dedent("""\
        * feature  [orphaned]
          main     [default]
    """)


def test_branches_workspace(cli):
    make_repo(Path("workspace/one"))
    make_repo(Path("workspace/two"))
    git(Path("workspace/two"), "checkout", "-b", "topic")

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
    work = make_checkout(Path("checkout"))
    git(work, "checkout", "-b", "feature")

    cli.run("m checkout/work")

    assert cli.succeeded
    assert git(work, "branch", "--show-current") == "main"


def test_groom_deletes_stale_tracked_branch(cli):
    work = make_checkout(Path("checkout"))
    make_stale_tracked_branch(work)

    cli.run("g checkout/work")

    assert cli.succeeded
    assert "deleted stale" in cli.logged
    assert git(work, "branch", "--show-current") == "main"
    assert not git(work, "branch", "--list", "stale")


def test_groom_preserves_unmerged_stale_tracked_branch(cli):
    work = make_checkout(Path("checkout"))
    make_unmerged_stale_tracked_branch(work)

    cli.run("g checkout/work")

    assert cli.failed
    assert cli.exit_code == 1
    assert "current branch can't be cleaned" in cli.logged
    assert git(work, "branch", "--show-current") == "unmerged"
    assert git(work, "branch", "--list", "unmerged")


def test_groom_deletes_squashed_stale_tracked_branch(cli):
    work = make_checkout(Path("checkout"))
    make_squashed_stale_tracked_branch(work)

    cli.run("g checkout/work")

    assert cli.succeeded
    assert "deleted squashed" in cli.logged
    assert git(work, "branch", "--show-current") == "main"
    assert not git(work, "branch", "--list", "squashed")


def test_groom_reports_already_on_default_branch(cli):
    work = make_checkout(Path("checkout"))

    cli.run("g checkout/work")

    assert cli.succeeded
    assert "already on main branch" in cli.logged
    assert git(work, "branch", "--show-current") == "main"


def test_groom_refuses_pending_changes(cli):
    work = make_checkout(Path("checkout"))
    make_stale_tracked_branch(work)
    (work / "scratch.txt").write_text("pending\n")

    cli.run("groom checkout/work")

    assert cli.failed
    assert cli.exit_code == 1
    assert "pending changes" in cli.logged
    assert git(work, "branch", "--show-current") == "stale"
    assert git(work, "branch", "--list", "stale")


def test_cleanable_branches_require_default_branch_ancestry(tmp_path):
    work = make_checkout(tmp_path / "checkout")
    git(work, "checkout", "-b", "done")
    commit_file(work, "done.txt", "done\n", "done work")
    git(work, "push", "-u", "origin", "done")
    git(work, "checkout", "main")
    git(work, "merge", "--no-ff", "done", "-m", "merge done")
    git(work, "push", "origin", "main")
    git(work, "checkout", "-b", "v2gpt")
    commit_file(work, "v2gpt.txt", "still in progress\n", "v2gpt work")
    git(work, "push", "-u", "origin", "v2gpt")

    git_dir = GitDir(work)

    assert git_dir.cleanable_base_ref == "origin/main"
    assert git_dir.local_cleanable_branches == {"done"}
    assert "origin/done" in git_dir.remote_cleanable_branches
    assert "origin/v2gpt" not in git_dir.remote_cleanable_branches
    assert "origin/main" not in git_dir.remote_cleanable_branches


def test_cleanable_branches_detect_squashed_content(tmp_path):
    work = make_checkout(tmp_path / "checkout")
    git(work, "checkout", "-b", "squashed")
    commit_file(work, "one.txt", "one\n", "one")
    commit_file(work, "two.txt", "two\n", "two")
    git(work, "push", "-u", "origin", "squashed")
    git(work, "checkout", "main")
    git(work, "merge", "--squash", "squashed")
    git(work, "commit", "-m", "squash squashed")
    git(work, "push", "origin", "main")

    git_dir = GitDir(work)

    assert not git_dir.is_ancestor("squashed", "origin/main")
    assert git_dir.merge_is_noop("squashed", "origin/main")
    assert git_dir.local_cleanable_branches == {"squashed"}
    assert "origin/squashed" in git_dir.remote_cleanable_branches
