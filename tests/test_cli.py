import shutil
import subprocess
from pathlib import Path
from textwrap import dedent

from mgit.cli import normalized_cli_args

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
    assert normalized_cli_args(["--color", "always", "g", "checkout"]) == ["--color", "always", "groom", "checkout"]


def test_workspace_status_alignment(cli):
    make_repo(Path("my-workspace/short"))
    make_repo(Path("my-workspace/longer-name"))

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
    assert "DEBUG Running:" in cli.logged


def test_branches_single_repo(cli):
    make_repo(Path("repo"))
    git(Path("repo"), "checkout", "-b", "feature")

    cli.run("b repo")

    assert cli.succeeded
    assert cli.logged.stdout.contents() == dedent("""\
        * feature  [orphaned]
          main     [default]
    """)

    cli.run("--color always b repo")
    assert cli.succeeded
    assert "\x1b[32m* feature" in cli.logged.stdout.contents()


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
