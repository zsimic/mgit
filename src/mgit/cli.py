"""
\b
Advanced usage:
  --clean show                  Show which local/remote branches can be cleaned
  --clean local                 Clean local branches that were deleted from their corresponding remote
  --clean remote                Clean merged remote branches
  --clean all                   Clean local and merged remote branches
  --clean reset                 Do a git --reset --hard + clean -fdx (nuke all changes, get back to pristine state)
\b
"""

import logging
import sys

import click
import runez

from mgit import get_target, GitCheckout
from mgit.git import GitRunReport


LOG = logging.getLogger(__name__)
VALID_CLEAN_ACTIONS = "show local remote all reset".split()


@runez.click.command()
@runez.click.version()
@runez.click.debug()
@runez.click.color()
@runez.click.log()
@click.option("--clean", default=None, type=click.Choice(VALID_CLEAN_ACTIONS), help="Auto-clean branches")
@click.option("-f", "--fetch", is_flag=True, default=False, help="Fetch from all remotes")
@click.option("-p", "--pull", is_flag=True, default=False, help="Pull from tracking remote")
@click.option("-s/-v", "--short/--verbose", is_flag=True, default=None, help="Short/verbose output")
@click.option("-cs", is_flag=True, default=False, help="Handy shortcut for '--clean show'")
@click.option("-cl", is_flag=True, default=False, help="Handy shortcut for '--clean local'")
@click.option("-cr", is_flag=True, default=False, help="Handy shortcut for '--clean remote'")
@click.option("-ca", is_flag=True, default=False, help="Handy shortcut for '--clean all'")
@click.argument("target", required=False, default=None)
def main(debug, log, clean, target, **kwargs):
    """
    Fetch collections of git projects
    """
    runez.system.AbortException = SystemExit
    runez.date.DEFAULT_DURATION_SPAN = -2
    runez.log.setup(debug=debug, console_format="%(levelname)s %(message)s", file_location=log, locations=None)

    hc = handy_clean(kwargs)
    if not clean:
        clean = hc

    target = get_target(target, **kwargs)

    if clean is not None:
        handle_clean(target, clean)
        sys.exit(0)

    target.print_status()


def handy_clean(kwargs):
    """
    :param kwargs: Pop all handy shortcuts from kwargs
    :return str|None: Equivalent full --clean option
    """
    cs = kwargs.pop("cs")
    cl = kwargs.pop("cl")
    cr = kwargs.pop("cr")
    ca = kwargs.pop("ca")
    if cs:
        return "show"

    if cl:
        return "local"

    if cr:
        return "remote"

    if ca:
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
            print("  %s branch %s can be cleaned" % (runez.bold("local"), runez.bold(branch)))

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
                print("%s/%s remote branches cleaned" % (cleaned, total))

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
                print(runez.orange("%s/%s local branches cleaned" % (cleaned, total)))

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
