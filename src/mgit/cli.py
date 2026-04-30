import argparse
import contextlib
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version

import runez

from mgit import get_target, GitCheckout, print_modified
from mgit.commands import command_for, command_help, CommandSpec
from mgit.git import GitRunReport

VALID_CLEAN_ACTIONS = ("show", "local", "remote", "all", "reset")


@dataclass(frozen=True)
class CliInvocation:
    command: CommandSpec
    target: str | None
    verbose: bool = False
    color: str = "auto"
    legacy_clean: str | None = None
    legacy_short: bool = False


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

    # Compatibility paths for the v1 flag-oriented CLI. New commands are the v2 design center.
    parser.add_argument("--clean", choices=VALID_CLEAN_ACTIONS, help=argparse.SUPPRESS)
    parser.add_argument("-f", "--fetch", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("-p", "--pull", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("-s", "--short", dest="legacy_short", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("-cs", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("-cl", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("-cr", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("-ca", action="store_true", help=argparse.SUPPRESS)

    parser.add_argument("args", nargs="*", metavar="COMMAND_OR_TARGET")
    return parser


def parse_cli_args(argv=None, parser=None):
    parser = parser or build_parser()
    namespace = parser.parse_args(argv)
    command = command_for("status")
    target_args = namespace.args
    explicit_command = False

    if namespace.args:
        command_match = command_for(namespace.args[0])
        if command_match:
            command = command_match
            target_args = namespace.args[1:]
            explicit_command = True

    if len(target_args) > 1:
        parser.error(f"{command.name} accepts at most one target")

    legacy_clean = handy_clean(namespace)
    if namespace.clean and legacy_clean and namespace.clean != legacy_clean:
        parser.error("choose only one clean action")

    legacy_clean = namespace.clean or legacy_clean
    legacy_actions = sum(bool(value) for value in (legacy_clean, namespace.fetch, namespace.pull))
    if legacy_actions > 1:
        parser.error("choose only one legacy action flag")

    if legacy_actions and explicit_command:
        parser.error("legacy action flags cannot be combined with v2 commands")

    if namespace.fetch:
        command = command_for("fetch")

    elif namespace.pull:
        command = command_for("pull")

    return CliInvocation(
        command=command,
        target=target_args[0] if target_args else None,
        verbose=namespace.verbose,
        color=namespace.color,
        legacy_clean=legacy_clean,
        legacy_short=namespace.legacy_short,
    )


def configure_runtime():
    runez.system.AbortException = SystemExit
    runez.date.DEFAULT_DURATION_SPAN = -2
    runez.log.setup(debug=False, console_format="%(levelname)s %(message)s", locations=None)


def color_context(policy):
    if policy == "never":
        return runez.ActivateColors(False)

    if policy == "always":
        return runez.ActivateColors(True)

    return contextlib.nullcontext()


def target_preferences(invocation):
    short = invocation.legacy_short or not invocation.verbose
    return {
        "fetch": invocation.command.name == "fetch",
        "fetch_age": None if invocation.command.name == "fetch" else 30,
        "pull": invocation.command.name == "pull",
        "short": short,
    }


def invocation_target(invocation):
    return get_target(invocation.target, **target_preferences(invocation))


def handy_clean(namespace):
    """
    :param argparse.Namespace namespace: Parsed command line
    :return str|None: Equivalent full --clean option
    """
    if namespace.cs:
        return "show"

    if namespace.cl:
        return "local"

    if namespace.cr:
        return "remote"

    if namespace.ca:
        return "all"

    return None


def run_git(target, fatal, *args):
    """Run git command on target, abort if command exits with error code"""
    error = target.git.run_raw_git_command(*args)
    if error.has_problems:
        if fatal:
            runez.abort(error.representation())

        print(error.representation())
        return 0

    return 1


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

        print_modified(target.git.status.modified, runez.teal, runez.red)
        print_modified(target.git.status.untracked, runez.orange)


def ensure_single_checkout(target, command):
    if not isinstance(target, GitCheckout):
        runez.abort(f"{command} only supports one git checkout", code=2)

    return target


def handle_status(target, _invocation):
    target.print_status()
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
    "main": handle_main,
    "groom": handle_groom,
}


def run_invocation(invocation):
    configure_runtime()
    target = invocation_target(invocation)

    if invocation.legacy_clean:
        handle_clean(target, invocation.legacy_clean)
        return 0

    handler = COMMAND_HANDLERS[invocation.command.handler]
    return handler(target, invocation)


def main(argv=None):
    invocation = parse_cli_args(argv)
    with color_context(invocation.color):
        return run_invocation(invocation)


def clean_reset(target):
    """
    :param GitCheckout target: Target to reset
    """
    fallback = target.git.fallback_branch()
    if not fallback:
        runez.abort("Can't determine a branch that can be used for reset")

    run_git(target, True, "reset", "--hard", "HEAD")
    run_git(target, True, "clean", "-fdx")
    if fallback != target.git.branches.current:
        run_git(target, True, "checkout", fallback)

    run_git(target, True, "pull")
    target.git.reset_cached_properties()
    print(target.header())


def clean_show(target):
    """
    :param GitCheckout target: Target to show
    """
    print(target.header())
    if not target.git.local_cleanable_branches:
        print("  No local branches can be cleaned")

    else:
        for branch in target.git.local_cleanable_branches:
            print("  {} branch {} can be cleaned".format(runez.bold("local"), runez.bold(branch)))

    if not target.git.remote_cleanable_branches:
        print("  No remote branches can be cleaned")

    else:
        for branch in target.git.remote_cleanable_branches:
            print("  %s can be cleaned" % (runez.bold(branch)))


def handle_single_clean(target, what):
    """
    :param GitCheckout target: Single checkout to clean
    :param str what: Operation
    """
    report = target.git.fetch()
    if report.has_problems:
        if what != "reset":
            what = "clean"

        print(target.header(GitRunReport(report).add(problem="<can't %s" % what)))
        runez.abort("")

    if what == "reset":
        return clean_reset(target)

    if what == "show":
        return clean_show(target)

    total_cleaned = 0
    print(target.header())

    if what in "remote all":
        if not target.git.remote_cleanable_branches:
            print("  No remote branches can be cleaned")

        else:
            total = len(target.git.remote_cleanable_branches)
            cleaned = 0
            for branch in target.git.remote_cleanable_branches:
                remote, _, name = branch.partition("/")
                if not remote and name:
                    raise Exception("Unknown branch spec '%s'" % branch)

                if run_git(target, False, "branch", "--delete", "--remotes", branch):
                    cleaned += run_git(target, False, "push", "--delete", remote, name)

            total_cleaned += cleaned
            if cleaned == total:
                print("%s cleaned" % runez.plural(cleaned, "remote branch"))

            else:
                print(f"{cleaned}/{total} remote branches cleaned")

            target.git.reset_cached_properties()
            if what == "all":
                # Fetch to update remote branches (and correctly detect new dangling local)
                target.git.fetch()

    if what in "local all":
        if not target.git.local_cleanable_branches:
            print("  No local branches can be cleaned")

        else:
            total = len(target.git.local_cleanable_branches)
            cleaned = 0
            for branch in target.git.local_cleanable_branches:
                if branch == target.git.branches.current:
                    fallback = target.git.fallback_branch()
                    if not fallback:
                        print("Skipping branch '%s', can't determine fallback branch" % target.git.branches.current)
                        continue

                    run_git(target, True, "checkout", fallback)
                    run_git(target, True, "pull")

                cleaned += run_git(target, False, "branch", "--delete", branch)

            total_cleaned += cleaned
            if cleaned == total:
                print(runez.bold("%s cleaned" % runez.plural(cleaned, "local branch")))

            else:
                print(runez.orange(f"{cleaned}/{total} local branches cleaned"))

            target.git.reset_cached_properties()

    if total_cleaned:
        print(target.header())


def handle_clean(target, what):
    if isinstance(target, GitCheckout):
        handle_single_clean(target, what)
        return

    if what in "remote reset":
        runez.abort("Only '--clean show' and '--clean local' supported for multiple git checkouts for now")

    target.prefs.name_size = None
    target.prefs.set_short(True)
    for sub_target in target.checkouts:
        handle_single_clean(sub_target, what)
        print("----")
