"""
\b
Advanced usage:
  --clean show                  Show which local/remote branches can be cleaned
  --clean local                 Clean local branches that were deleted from their corresponding remote
  --clean remote                Clean merged remote branches
  --clean all                   Clean local and merged remote branches
  --clean reset                 Do a git --reset --hard + clean -fdx (nuke all changes, get back to pristine state)
\b
  --ignore show                 Show ignores currently in effect
  --ignore add 'hackday.*'      Add an ignore regex, for example here 'hackday.*'
  --ignore remove 'hackday.*'   Remove an ignore regex, for example here 'hackday.*'
  --ignore clean                Remove all ignores
\b
"""

from __future__ import absolute_import

import logging
import sys

import click

from mgit import abort, colored, get_target, GitCheckout, ProjectDir
from mgit.git import GitRunReport


LOG = logging.getLogger(__name__)
VALID_IGNORE_ACTIONS = "show add remove clear".split()
VALID_CLEAN_ACTIONS = "show local remote all reset".split()


@click.command(context_settings=dict(help_option_names=["-h", "--help"], max_content_width=160), epilog=__doc__)
@click.version_option()
@click.option("--debug", is_flag=True, help="Show debugging information")
@click.option("--color/--no-color", is_flag=True, default=None, help="Use (or not) colors (on by default on tty)")
@click.option("--ignore", metavar="action[:what]", default=None, help="Show/add/remove/clear ignores")
@click.option("--clean", default=None, type=click.Choice(VALID_CLEAN_ACTIONS), help="Auto-clean branches")
@click.option("-a", "--all", is_flag=True, default=False, help="Examine all repos, even missing git checkouts")
@click.option("-f", "--fetch", is_flag=True, default=False, help="Fetch from all remotes")
@click.option("-p", "--pull", is_flag=True, default=False, help="Pull from tracking remote, clone missing with --all")
@click.option("-s/-v", "--short/--verbose", is_flag=True, default=None, help="Short/verbose output")
@click.option("-cs", is_flag=True, default=False, help="Handy shortcut for '--clean show'")
@click.option("-cl", is_flag=True, default=False, help="Handy shortcut for '--clean local'")
@click.option("-cr", is_flag=True, default=False, help="Handy shortcut for '--clean remote'")
@click.option("-ca", is_flag=True, default=False, help="Handy shortcut for '--clean all'")
@click.argument("target", required=False, default=None)
def main(debug, color, ignore, clean, target, **kwargs):
    """
    Manage git projects en masse
    """
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(format="[%(levelname)s] %(asctime)s %(message)s", level=level)
    colored.activate_colors(color)

    hc = handy_clean(kwargs)
    if not clean:
        clean = hc

    target = get_target(target, **kwargs)

    if ignore is not None:
        action, _, what = ignore.partition(":")
        handle_ignore(action, what, target)
        sys.exit(0)

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
            abort(error.representation())
        print(error.representation())
        return 0
    return 1


def clean_reset(target):
    """
    :param GitCheckout target: Target to reset
    """
    fallback = target.git.fallback_branch()
    if not fallback:
        abort("Can't determine a branch that can be used for reset")
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
            print("  %s branch %s can be cleaned" % (colored.highlight("local"), colored.highlight(branch)))
    if not target.git.remote_cleanable_branches:
        print("  No remote branches can be cleaned")
    else:
        for branch in target.git.remote_cleanable_branches:
            print("  %s can be cleaned" % (colored.highlight(branch)))


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
        abort()

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
                print("%s cleaned" % colored.plural(cleaned, "remote branch"))
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
                print(colored.highlight("%s cleaned" % colored.plural(cleaned, "local branch")))
            else:
                print(colored.warn("%s/%s local branches cleaned" % (cleaned, total)))

            target.git.reset_cached_properties()

    if total_cleaned:
        print(target.header())


def handle_clean(target, what):
    if isinstance(target, GitCheckout):
        handle_single_clean(target, what)
        return

    if what in "remote reset":
        abort("Only '--clean show' and '--clean local' supported for multiple git checkouts for now")

    target.prefs.name_size = None
    target.prefs.set_short(True)
    for subtarget in target.checkouts:
        handle_single_clean(subtarget, what)
        print("----")


def handle_ignore(action, what, target):
    """
    Show/add/remove/clear ignores on current project
    :param str action: One of VALID_IGNORE_ACTIONS
    :param str what: What to add or remove
    :param ProjectDir target: Target dir
    """
    if not isinstance(target, ProjectDir):
        abort("--ignore applies to collections of checkouts, not particular checkouts")
    if not target.predominant:
        abort("--ignore applies to internal bitbucket stash repos, this folder doesn't seem related to one")
    if target.predominant.type != 'stash':
        abort("--ignore applies to bitbucket stash only, not '%s'" % target.predominant.type)

    if not action:
        action = 'show'

    action = action.lower()
    if action not in VALID_IGNORE_ACTIONS:
        abort("--ignore unknown action '%s', try for example: '--ignore show', or '--ignore add:hackday.*'")
    if action in ('show', 'clear') and what:
        abort("--ignore %s does not take arguments" % action)

    if action == 'clear':
        target.ignores.clear()

    elif action == 'add':
        added, invalid = target.ignores.add(what)
        if added:
            print("Added %s" % colored.plural(added, "pattern"))
        if invalid:
            print("%s: [%s], %s" % (
                colored.note("Skipped"),
                '], ['.join(colored.problem(s) for s in invalid),
                colored.note("invalid regexes"),
            ))

    elif action == 'remove':
        removed, invalid = target.ignores.remove(what)
        if removed:
            print("Removed %s" % colored.plural(removed, "pattern"))
        if invalid:
            print("%s: [%s], %s" % (
                colored.note("Skipped"),
                '], ['.join(colored.problem(s) for s in invalid),
                colored.note("not in ignore list"),
            ))

    values = target.ignores.values
    if not values:
        print(colored.note("No ignores defined"))
    else:
        print("%s:\n  %s" % (colored.plural(values, "ignore", colored.NOTE), "\n  ".join(values)))
