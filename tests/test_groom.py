def make_stale_tracked_branch(work, branch="stale", merged=True):
    work.checkout("-b", branch)
    if not merged:
        work.commit_file(f"{branch}.txt", "still in progress", f"{branch} work")

    work.push("-u", "origin", branch)
    work.checkout("main")
    work.push("origin", "--delete", branch)
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
    assert "Already on main branch" in cli.logged


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
    assert "can't groom: current branch can't be cleaned: unmerged" in cli.logged
    assert work.current_branch == "unmerged"
    assert work.has_branch("unmerged")
