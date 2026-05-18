from textwrap import dedent


def test_groom_workflow(cli, git):
    work = git.seeded("work")
    work.checkout("-b", "stale")
    work.push("-u", "origin", "stale")
    work.checkout("main")
    work.push("origin", "--delete", "stale")
    work.checkout("stale")

    cli.run("g work")

    assert cli.succeeded
    assert cli.logged.stdout.contents() == dedent("""\
        Checked out main branch
        Deleted branch stale
        on main ✅
    """)
