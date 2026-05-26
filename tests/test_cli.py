from __future__ import annotations

import os
import time
from pathlib import Path

import runez

from mgit.cli import normalized_cli_args
from mgit.git import GitDir, GitRefs


def test_command_help(cli):
    cli.run("--help")
    assert cli.succeeded
    assert "Commands:" in cli.logged
    assert "status (s)" in cli.logged
    assert "legend (l)" in cli.logged

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
    assert normalized_cli_args(["l"]) == ["legend"]


def test_abort_reporting(cli, git):
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
    cli.run("folder")
    assert cli.failed
    assert "no git folders" in cli.logged

    git.init("folder/repo")
    cli.run("main folder")
    assert cli.failed
    assert "main only supports one git checkout" in cli.logged


def test_single_status_shows_pending_paths_and_discovers_parent_checkout(cli, git):
    repo = git.init("repo")
    repo.write_file("README.md", "changed")
    repo.write_file("new.txt", "new")

    cli.run("repo")
    assert cli.succeeded
    assert "main ✅ ✏️1 🆕1" in cli.logged
    assert "README.md" in cli.logged
    assert "new.txt" in cli.logged

    cli.run("fetch repo")
    assert cli.succeeded

    (repo.cwd / "foo").mkdir()
    os.chdir(repo.cwd / "foo")
    cli.run()
    assert cli.succeeded
    assert "README.md" in cli.logged
    assert "new.txt" in cli.logged

    cli.run(".")
    assert cli.failed
    assert "repo/foo: no git folders" in cli.logged


def test_status_line_summarizes_stale_and_cleanable_branches(cli, git):
    repo = git.seeded("repo")
    repo.checkout("-b", "stale")
    repo.push("-u", "origin", "stale")
    repo.checkout("main")
    repo.push("origin", "--delete", "stale")
    old_time = time.time() - (13 * 60 * 60 + 60)
    for name in ("FETCH_HEAD", "HEAD"):
        path = repo.cwd / ".git" / name
        if path.exists():
            os.utime(path, (old_time, old_time))

    cli.run("repo")

    assert cli.succeeded
    assert "main ☑️ [+1🪦] ⌛13h" in cli.logged


def test_status_line_partitions_other_branches(cli, git):
    repo = git.seeded("repo")
    for branch in ("foo", "bar"):
        repo.checkout("-b", branch, "main")
        repo.push("-u", "origin", branch)
        repo.checkout("main")
        repo.push("origin", "--delete", branch)

    repo.checkout("-b", "baz", "main")
    repo.commit_file("baz.txt", "pending", "baz work")
    repo.checkout("main")

    cli.run("repo")
    assert cli.succeeded
    assert "main ✅ [+2🪦+1]" in cli.logged

    repo.checkout("foo")
    cli.run("repo")
    assert cli.succeeded
    assert "foo 🪦 [+1🪦+1]" in cli.logged


def test_dirty_cleanable_status_keeps_tombstone(cli, git):
    repo = git.seeded("repo")
    repo.checkout("-b", "cleanable")
    repo.push("-u", "origin", "cleanable")
    repo.checkout("main")
    repo.push("origin", "--delete", "cleanable")
    repo.checkout("cleanable")
    repo.write_file("scratch.txt", "pending")

    cli.run("repo")

    assert cli.succeeded
    assert "cleanable 🪦 🆕1" in cli.logged


def test_verbose_enables_debug_logging(cli, git):
    git.init("repo")

    cli.run("repo")
    assert cli.succeeded
    assert "DEBUG Running:" not in cli.logged

    cli.run("-v repo")
    assert cli.succeeded
    assert "DEBUG Running:" in cli.logged


def test_legend_describes_display_symbols(cli):
    cli.run("legend")

    assert cli.succeeded
    assert "✅ repo freshly fetched (within 30 seconds)" in cli.logged
    assert "☑️ repo not freshly fetched (more than 30 seconds ago)" in cli.logged
    assert "⌛ repo fetch notably stale (more than 12 hours ago)" in cli.logged
    assert "💾 branch present locally" in cli.logged
    assert "☁️ configured upstream present in fetched remote refs" in cli.logged
    assert "🪦 cleanable branch" in cli.logged
    assert "👻 detached HEAD" in cli.logged
    assert "[+N🪦+N] cleanable and remaining local branches" in cli.logged


def test_branches_workspace_lists_local_branches(cli, git):
    git.init("workspace/one")
    two = git.init("workspace/two")
    two.checkout("-b", "topic")
    two.commit_file("topic.txt", "in progress", "topic work")

    cli.run("branches workspace")

    assert cli.succeeded
    assert "workspace:" not in cli.logged
    assert "one:" in cli.logged
    assert "two:" in cli.logged
    assert "* topic" in cli.logged
    assert "topic💾" in cli.logged
    assert "[current]" in cli.logged
    assert "[default]" in cli.logged
    assert "[cleanable]" not in cli.logged


def test_branches_can_append_legend(cli, git):
    git.init("repo")

    cli.run("branches --legend repo")
    assert cli.succeeded
    assert "* main [default] [current]\n\n✅ repo freshly fetched" in str(cli.logged.stdout)

    cli.run("b -l repo")
    assert cli.succeeded
    assert "💾 branch present locally" in cli.logged


def test_branches_fall_back_to_symbolic_head_for_unborn_repo(cli, git):
    git.init("repo", include_readme=False)

    cli.run("-v branches repo")

    assert cli.succeeded
    assert "* main [default] [current]" in cli.logged
    assert "symbolic-ref --quiet --short HEAD" in cli.logged


def test_branches_distinguish_cleanable_and_in_progress_refs(cli, git):
    repo = git.seeded("repo")
    repo.checkout("-b", "done")
    repo.commit_file("done.txt", "complete", "done work")
    repo.push("-u", "origin", "done")
    repo.checkout("main")
    repo.run_git("merge", "--no-ff", "done", "-m", "merge done")
    repo.push("origin", "main")
    repo.checkout("-b", "remote-work", "main")
    repo.commit_file("remote.txt", "in progress", "remote work")
    repo.push("-u", "origin", "remote-work")
    repo.checkout("-b", "local-work", "main")
    repo.commit_file("local.txt", "not pushed", "local work")

    cli.run("branches repo")

    assert cli.succeeded
    lines = {
        name: next(line for line in str(cli.logged.stdout).splitlines() if name in line) for name in ("done", "local-work", "remote-work")
    }
    assert "done💾☁️🪦" in lines["done"]
    assert "[cleanable]" in lines["done"]
    assert "* local-work💾" in lines["local-work"]
    assert "[current]" in lines["local-work"]
    assert "☁️" not in lines["local-work"]
    assert "🪦" not in lines["local-work"]
    assert "remote-work💾☁️" in lines["remote-work"]
    assert "🪦" not in lines["remote-work"]

    git_dir = GitDir(repo.cwd)
    refs = git_dir.lazy_refs
    main = refs.all_branches["main"]
    assert "protected" not in main.__dict__
    assert main.protected
    assert main.__dict__["protected"]
    done = refs.all_branches["done"]
    assert done.local_merged is None
    assert done.cleanable
    assert refs.local_branch_names == ["done", "local-work", "main", "remote-work"]
    assert done.parent is refs
    assert done.parent.parent is git_dir
    assert done.local_ref == "refs/heads/done"
    assert done.remote_ref == "refs/remotes/origin/done"
    assert done.local_oid
    assert done.remote_oid == done.local_oid
    assert done.local_tree
    assert done.remote_tree == done.local_tree
    assert done.local_merged
    assert done.remote_merged
    assert main.parent is refs
    assert main.remote_ref == "refs/remotes/origin/main"
    assert refs.cleanable_base() is main
    assert main.protected


def test_refs_include_remote_only_branches(cli, git):
    repo = git.seeded("repo")
    repo.checkout("-b", "remote-only")
    repo.commit_file("remote.txt", "published", "remote work")
    repo.push("-u", "origin", "remote-only")
    repo.checkout("main")
    repo.branch("-D", "remote-only")

    refs = GitDir(repo.cwd).lazy_refs
    remote_only = refs.all_branches["origin/remote-only"]

    assert not remote_only.has_local
    assert remote_only.has_remote
    assert remote_only.remote == "origin"
    assert remote_only.remote_ref == "refs/remotes/origin/remote-only"

    cli.run("branches repo")
    assert cli.succeeded
    assert "remote-only" not in cli.logged


def test_branches_batch_normal_merge_proofs(cli, git):
    repo = git.seeded("repo")
    for branch in ("done-a", "done-b"):
        repo.checkout("-b", branch, "main")

    repo.checkout("main")

    cli.run("-v branches repo")

    assert cli.succeeded
    output = str(cli.logged)
    merged_commands = {line for line in output.splitlines() if "for-each-ref --merged=" in line}
    assert len(merged_commands) == 1
    assert " git -C repo remote" not in output
    assert "symbolic-ref" not in output
    assert "merge-base --is-ancestor" not in output
    assert "merge-tree" not in output
    assert "rev-parse" not in output


def test_unmerged_branch_with_gone_upstream_is_not_cleanable(cli, git):
    repo = git.seeded("repo")
    repo.checkout("-b", "not-done")
    repo.commit_file("work.txt", "in progress", "unmerged work")
    repo.push("-u", "origin", "not-done")
    repo.checkout("main")
    repo.push("origin", "--delete", "not-done")
    repo.checkout("not-done")

    cli.run("repo")

    assert cli.succeeded
    assert "not-done ✅" in cli.logged
    assert "🪦" not in cli.logged


def test_branch_names_are_styled_consistently(cli, git):
    repo = git.seeded("repo")
    repo.checkout("-b", "topic")
    repo.commit_file("topic.txt", "in progress", "topic work")
    repo.push("-u", "origin", "topic")
    repo.checkout("main")
    repo.checkout("-b", "cleanable")
    repo.push("-u", "origin", "cleanable")
    repo.checkout("topic")
    repo.push("origin", "--delete", "cleanable")
    with runez.ActivateColors(True):
        default_name = runez.bold(runez.green("main"))
        topic_name = runez.bold("topic")
        cleanable_name = runez.bold(runez.orange("cleanable"))

    cli.run("--color always branches repo")
    assert cli.succeeded
    assert default_name in cli.logged
    assert topic_name in cli.logged
    assert cleanable_name in cli.logged

    cli.run("--color always repo")
    assert cli.succeeded
    assert f"{topic_name} ✅" in cli.logged
    assert "[+1🪦]" in cli.logged

    cli.run("--color always pull repo")
    assert cli.succeeded
    assert f"{topic_name} ✅" in cli.logged

    cli.run("--color always main repo")
    assert cli.succeeded
    assert f"checked out {default_name}" in cli.logged

    repo.checkout("cleanable")
    cli.run("--color always repo")
    assert cli.succeeded
    assert f"{cleanable_name} 🪦" in cli.logged

    cli.run("--color always fetch repo")
    assert cli.succeeded
    assert f"{cleanable_name} 🪦" in cli.logged


def test_pull_workspace_recaps_each_checkout(cli, git):
    foo_source = git.seeded_set("foo-source")
    bar_source = git.seeded_set("bar-source")
    foo = git.clone(foo_source.remote_url, "workspace/foo")
    git.clone(bar_source.remote_url, "workspace/bar-baz")
    detached = git.clone(foo_source.remote_url, "workspace/detached")
    detached.checkout("--detach", "HEAD")
    git.init("workspace/broken")
    foo_source.seed.commit_file("next.txt", "next", "next")
    foo_source.seed.push()
    foo.run_git("fetch")

    cli.run("workspace")
    assert cli.succeeded
    assert "workspace:" not in cli.logged
    assert "foo: main ✅ 1 behind" in cli.logged
    assert "detached: HEAD 👻" in cli.logged
    assert "HEAD detached" not in cli.logged

    cli.run("fetch workspace")
    assert cli.succeeded

    cli.run("pull workspace")
    assert cli.succeeded
    assert "foo: main ✅ was 1 behind" in cli.logged
    assert "bar-baz: main ✅ was up-to-date" in cli.logged
    assert "broken: main ✅ can't pull; no remotes" in cli.logged
    assert "detached: HEAD 👻 can't pull; HEAD detached" in cli.logged
    assert "HEAD detached; HEAD detached" not in cli.logged
    assert foo.run_git("rev-parse", "HEAD") == foo.run_git("rev-parse", "origin/main")
    assert detached.current_branch == ""

    # Single fails with exit code != 0
    cli.run("pull workspace/broken")
    assert cli.failed
    assert "can't pull; no remotes" in cli.logged

    cli.run("pull workspace/detached")
    assert cli.failed
    assert "can't pull; HEAD detached" in cli.logged
    assert detached.current_branch == ""


def test_pull_refuses_untracked_changes(cli, git):
    repo = git.seeded("repo")
    repo.write_file("scratch.txt", "pending")

    cli.run("pull repo")

    assert cli.failed
    assert "can't pull; pending changes" in cli.logged


def test_pull_refuses_branch_with_gone_upstream(cli, git):
    repo = git.seeded("repo")
    repo.checkout("-b", "gone")
    repo.push("-u", "origin", "gone")
    repo.checkout("main")
    repo.push("origin", "--delete", "gone")
    repo.checkout("gone")

    cli.run("pull repo")

    assert cli.failed
    assert "can't pull; remote branch gone" in cli.logged


def test_single_pull_failure_shows_full_git_error(cli, git):
    repo = git.seeded("repo")
    repo.remote("set-url", "origin", "missing.git")

    cli.run("pull repo")

    assert cli.failed
    assert "git pull --rebase failed:" in cli.logged
    assert "fatal: 'missing.git' does not appear to be a git repository" in cli.logged
    assert "Please make sure you have the correct access rights" in cli.logged


def test_workspace_pull_failure_is_compact(cli, git):
    source = git.seeded_set("source")
    repo = git.clone(source.remote_url, "workspace/repo")
    repo.remote("set-url", "origin", "missing.git")

    cli.run("pull workspace")

    assert cli.succeeded
    assert "repo: main ✅ can't pull; 'missing.git' does not appear to be a git repository; was up-to-date" in cli.logged
    assert "fatal:" not in cli.logged
    assert "Please make sure" not in cli.logged


def test_main_checks_out_default_branch(cli, git):
    repo = git.init("repo")
    repo.checkout("-b", "feature")

    cli.run("m repo")

    assert cli.succeeded
    assert repo.current_branch == "main"


def test_main_only_evaluates_cleanability_for_reported_snapshot(cli, git, monkeypatch):
    repo = git.seeded("repo")
    repo.checkout("-b", "feature")
    evaluated = []
    evaluate_cleanability = GitRefs.evaluate_cleanability

    def track_evaluation(refs):
        if not refs._cleanup_evaluated:
            evaluated.append(refs.current)

        return evaluate_cleanability(refs)

    monkeypatch.setattr(GitRefs, "evaluate_cleanability", track_evaluation)

    cli.run("-v main repo")

    assert cli.succeeded
    assert repo.current_branch == "main"
    assert evaluated == ["main"]


def test_main_prefers_main_over_master_without_remote_head(cli, git):
    repo = git.seeded("repo")
    repo.branch("master")
    repo.push("origin", "master")
    repo.run_git("remote", "set-head", "origin", "--delete")
    repo.checkout("-b", "feature")

    cli.run("m repo")

    assert cli.succeeded
    assert repo.current_branch == "main"
