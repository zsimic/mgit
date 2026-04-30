import argparse
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version

import runez

from mgit import get_target, GitCheckout, print_modified
from mgit.commands import command_for, command_help, CommandSpec
from mgit.git import GitRunReport
from mgit.output import branch_default, branch_orphaned, color_context, index_change, untracked_change, worktree_change


@dataclass(frozen=True)
class CliInvocation:
    command: CommandSpec
    target: str | None
    verbose: bool = False
    color: str = "auto"


def package_version():
    try:
        return version("mgit")

    except PackageNotFoundError:
        return "0+unknown"


def build_parser():
    parser = argparse.ArgumentParser(
        prog="mgit",
        description="Inspect and update git checkouts.",
        epilog=command_help(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Show extra detail.")
    parser.add_argument("--color", choices=("auto", "always", "never"), default="auto", help="Control ANSI color output.")
    parser.add_argument("--version", action="version", version=f"mgit {package_version()}")
    parser.add_argument("args", nargs="*", metavar="COMMAND_OR_TARGET")
    return parser


def parse_cli_args(argv=None, parser=None):
    parser = parser or build_parser()
    namespace = parser.parse_args(argv)
    command = command_for("status")
    target_args = namespace.args

    if namespace.args:
        command_match = command_for(namespace.args[0])
        if command_match:
            command = command_match
            target_args = namespace.args[1:]

    if len(target_args) > 1:
        parser.error(f"{command.name} accepts at most one target")

    return CliInvocation(
        command=command,
        target=target_args[0] if target_args else None,
        verbose=namespace.verbose,
        color=namespace.color,
    )


def configure_runtime():
    runez.system.AbortException = SystemExit
    runez.date.DEFAULT_DURATION_SPAN = -2
    runez.log.setup(debug=False, console_format="%(levelname)s %(message)s", locations=None)


def target_preferences(invocation):
    return {
        "fetch": invocation.command.name == "fetch",
        "fetch_age": None if invocation.command.name == "fetch" else 30,
        "pull": invocation.command.name == "pull",
        "short": not invocation.verbose,
    }


def invocation_target(invocation):
    return get_target(invocation.target, **target_preferences(invocation))


def default_branch(git):
    """
    :param mgit.git.GitDir git: Checkout model
    :return str|None: Default branch name
    """
    branch = git.branches.default_branches.get("origin")
    if branch:
        return branch

    origin_branches = git.branches.by_remote.get("origin", set())
    for candidate in ("main", "master"):
        if candidate in git.branches.local or candidate in origin_branches:
            return candidate

    return None


def checkout_default_branch(target):
    """
    :param GitCheckout target: Checkout to move to its default branch
    :return GitRunReport: Checkout report
    """
    branch = default_branch(target.git)
    if not branch:
        return GitRunReport(problem="can't determine default branch")

    if target.git.branches.current == branch:
        return GitRunReport()

    _, error = target.git.run_git_command("checkout", branch)
    target.git.reset_cached_properties()
    if error.has_problems:
        return GitRunReport(error).add(problem="<can't checkout default branch")

    return GitRunReport(progress=f"checked out {branch}")


def stale_tracked_local_branches(git):
    """
    :param mgit.git.GitDir git: Checkout model
    :return list[str]: Local branches whose tracked remote branch is gone
    """
    result = []
    for branch in sorted(git.branches.local):
        if branch in git.special_branches:
            continue

        remote = git.config.tracking_remote.get(branch)
        if remote and branch not in git.branches.by_remote.get(remote, set()):
            result.append(branch)

    return result


def delete_stale_local_branches(target):
    """
    :param GitCheckout target: Checkout to clean
    :return GitRunReport: Cleanup report
    """
    report = GitRunReport()
    branches = stale_tracked_local_branches(target.git)
    if not branches:
        return report.add(note="no stale local branches")

    for branch in branches:
        if branch == target.git.branches.current:
            report.add(problem=f"can't delete current branch '{branch}'")
            continue

        _, error = target.git.run_git_command("branch", "--delete", branch)
        if error.has_problems:
            report.add(problem=f"couldn't delete '{branch}': {error.representation()}")

        else:
            report.add(progress=f"deleted {branch}")

    target.git.reset_cached_properties()
    return report


def pending_changes_report(target):
    report = GitRunReport(problem="<can't groom").add(problem="pending changes")
    if target.git.status.modified:
        report.add(note=runez.plural(target.git.status.modified, "diff"))

    if target.git.status.untracked:
        report.add(note=f"{len(target.git.status.untracked)} untracked")

    return report


def has_pending_changes(target):
    return bool(target.git.status.modified or target.git.status.untracked)


def print_checkout_status(target, report=None):
    print(target.header(report))
    if target.prefs.verbose:
        if len(target.git.orphan_branches) > 1:
            print("  Orphan branches: %s" % (", ".join(target.git.orphan_branches)))

        print_modified(target.git.status.modified, index_change, worktree_change)
        print_modified(target.git.status.untracked, untracked_change)


def branch_annotations(target, name):
    annotations = []
    if name == default_branch(target.git):
        annotations.append(branch_default("[default]"))

    if name in target.git.orphan_branches and name not in target.git.special_branches:
        annotations.append(branch_orphaned("[orphaned]"))

    return annotations


def branch_lines(target):
    branches = sorted(target.git.branches.local)
    if not branches:
        return ["  no local branches"]

    width = max(len(name) for name in branches)
    lines = []
    for name in branches:
        marker = "*" if name == target.git.branches.current else " "
        line = f"{marker} {name:<{width}}"
        annotations = branch_annotations(target, name)
        if annotations:
            line += "  %s" % " ".join(annotations)

        lines.append(line)

    return lines


def print_branch_report(target, indent=""):
    for line in branch_lines(target):
        print(f"{indent}{line}")


def ensure_single_checkout(target, command):
    if not isinstance(target, GitCheckout):
        runez.abort(f"{command} only supports one git checkout", code=2)

    return target


def handle_status(target, _invocation):
    target.print_status()
    return 0


def handle_branches(target, _invocation):
    if isinstance(target, GitCheckout):
        print_branch_report(target)
        return 0

    for checkout in target.checkouts:
        if target.prefs.all or checkout.git.is_git_checkout:
            print(f"{checkout.name}:")
            print_branch_report(checkout, indent="  ")

    return 0


def handle_main(target, invocation):
    target = ensure_single_checkout(target, invocation.command.name)
    report = checkout_default_branch(target)
    print_checkout_status(target, report)
    return 1 if report.has_problems else 0


def handle_groom(target, invocation):
    target = ensure_single_checkout(target, invocation.command.name)
    report = GitRunReport()

    fetch_report = target.git.fetch(age=None)
    if fetch_report.has_problems:
        report.add(fetch_report).add(problem="<can't groom")
        print_checkout_status(target, report)
        return 1

    if has_pending_changes(target):
        print_checkout_status(target, pending_changes_report(target))
        return 1

    checkout_report = checkout_default_branch(target)
    if checkout_report.has_problems:
        report.add(checkout_report).add(problem="<can't groom")
        print_checkout_status(target, report)
        return 1

    report.add(checkout_report)
    if has_pending_changes(target):
        print_checkout_status(target, pending_changes_report(target))
        return 1

    pull_report = target.git.pull()
    if pull_report.has_problems:
        report.add(pull_report).add(problem="<can't groom")
        print_checkout_status(target, report)
        return 1

    report.add(pull_report)
    report.add(delete_stale_local_branches(target))
    print_checkout_status(target, report)
    return 1 if report.has_problems else 0


COMMAND_HANDLERS = {
    "status": handle_status,
    "fetch": handle_status,
    "pull": handle_status,
    "branches": handle_branches,
    "main": handle_main,
    "groom": handle_groom,
}


def run_invocation(invocation):
    configure_runtime()
    target = invocation_target(invocation)

    handler = COMMAND_HANDLERS[invocation.command.handler]
    return handler(target, invocation)


def main(argv=None):
    invocation = parse_cli_args(argv)
    with color_context(invocation.color):
        return run_invocation(invocation)
