import pytest

from mgit.cli import GroomCommand


def make_stale_tracked_branch(work, branch="stale", merged=True):
    work.checkout("-b", branch)
    if not merged:
        work.commit_file(f"{branch}.txt", "still in progress", f"{branch} work")

    work.push("-u", "origin", branch)
    work.checkout("main")
    work.push("origin", "--delete", branch)
    work.checkout(branch)


def make_cleanable_remote_branch(work, branch="published", squash=False):
    work.checkout("-b", branch)
    work.commit_file(f"{branch}.txt", "completed", f"{branch} work")
    work.push("-u", "origin", branch)
    work.checkout("main")
    if squash:
        work.run_git("merge", "--squash", branch)
        work.commit(f"squash {branch}")
    else:
        work.run_git("merge", "--no-ff", branch, "-m", f"merge {branch}")

    work.push("origin", "main")
    work.checkout(branch)


def test_groom_deletes_stale_tracked_branch(cli, git):
    work = git.seeded("work")
    make_stale_tracked_branch(work)

    cli.run("g work")
    assert cli.succeeded
    assert "Checked out main branch" in cli.logged
    assert "Deleted branch stale" in cli.logged
    assert "main ✅ was up-to-date" in cli.logged
    assert work.current_branch == "main"
    assert not work.has_branch("stale")

    # 2nd groom: no-op
    cli.run("g work")
    assert cli.succeeded
    assert "main ✅ already on default branch" in cli.logged


def test_groom_only_deletes_the_branch_being_groomed(cli, git):
    work = git.seeded("work")
    make_stale_tracked_branch(work, branch="leave-me")
    work.checkout("main")
    make_stale_tracked_branch(work, branch="clean-me")

    cli.run("g work")

    assert cli.succeeded
    assert "Deleted branch clean-me" in cli.logged
    assert "Deleted branch leave-me" not in cli.logged
    assert "leave-me" not in cli.logged
    assert not work.has_branch("clean-me")
    assert work.has_branch("leave-me")

    cli.run("g work")
    assert cli.succeeded
    assert "main ✅ [+1🪦] already on default branch" in cli.logged
    assert "leave-me" not in cli.logged
    assert work.has_branch("leave-me")


def test_groom_deletes_cleanable_local_only_current_branch(cli, git):
    work = git.seeded("work")
    work.checkout("-b", "local-only")

    cli.run("g work")

    assert cli.succeeded
    assert "Deleted branch local-only" in cli.logged
    assert not work.has_branch("local-only")


def test_groom_on_default_branch_only_fetches_and_reports(cli, git):
    work = git.seeded("work")
    work.write_file("scratch.txt", "pending")

    cli.run("g work")

    assert cli.succeeded
    assert "already on default branch" in cli.logged
    assert work.current_branch == "main"


@pytest.mark.parametrize("squash", [False, True])
def test_groom_deletes_cleanable_current_remote_branch(cli, git, squash):
    work = git.seeded(f"work-{squash}")
    make_cleanable_remote_branch(work, squash=squash)

    cli.run(f"g {work.cwd.name}")

    assert cli.succeeded
    assert "Deleted remote branch origin/published" in cli.logged
    assert "Deleted branch published" in cli.logged
    assert work.current_branch == "main"
    assert not work.has_branch("published")
    assert not work.run_git("ls-remote", "--heads", "origin", "refs/heads/published")


def test_groom_does_not_delete_remote_branch_that_advanced_after_fetch(cli, git, monkeypatch):
    repos = git.seeded_set("work")
    work = repos.work
    make_cleanable_remote_branch(work)
    racer = git.clone(repos.remote_url, "racer")
    racer.checkout("-b", "published", "origin/published")

    checkout_default_branch = GroomCommand._checkout_default_branch

    def advance_remote_after_checkout(command, git_dir, branch):
        checkout_default_branch(command, git_dir, branch)
        racer.commit_file("late.txt", "not merged", "advance published")
        racer.push("origin", "published")

    monkeypatch.setattr(GroomCommand, "_checkout_default_branch", advance_remote_after_checkout)
    cli.run("g work")

    assert cli.failed
    assert "git push --force-with-lease=refs/heads/published:" in cli.logged
    assert "--delete origin refs/heads/published failed:" in cli.logged
    assert work.has_branch("published")
    assert work.run_git("ls-remote", "--heads", "origin", "refs/heads/published")


def test_groom_refuses_published_branch_with_unmerged_remote_work(cli, git):
    repos = git.seeded_set("work")
    work = repos.work
    work.checkout("-b", "published")
    work.push("-u", "origin", "published")
    racer = git.clone(repos.remote_url, "racer")
    racer.checkout("-b", "published", "origin/published")
    racer.commit_file("remote-only.txt", "not merged", "advance published")
    racer.push("origin", "published")

    cli.run("g work")

    assert cli.failed
    assert "Remote branch origin/published can't be cleaned automatically" in cli.logged
    assert work.current_branch == "published"
    assert work.has_branch("published")
    assert work.run_git("ls-remote", "--heads", "origin", "refs/heads/published")


def test_groom_refuses_pending_changes(cli, git):
    work = git.seeded("work")
    make_stale_tracked_branch(work)
    work.write_file("scratch.txt", "pending")

    cli.run("groom work")

    assert cli.failed
    assert "can't groom: pending changes" in cli.logged
    assert work.current_branch == "stale"
    assert work.has_branch("stale")


def test_groom_refuses_uncleanable_current_branch(cli, git):
    work = git.seeded("work")
    make_stale_tracked_branch(work, branch="unmerged", merged=False)

    cli.run("g work")

    assert cli.failed
    assert "Branch unmerged can't be cleaned" in cli.logged
    assert work.current_branch == "unmerged"
    assert work.has_branch("unmerged")
