import contextlib

import runez


def color_context(policy):
    if policy == "never":
        return runez.ActivateColors(False)

    if policy == "always":
        return runez.ActivateColors(True)

    return contextlib.nullcontext()


def branch(text):
    return runez.bold(text)


def command(text):
    return runez.bold(text)


def ok(text):
    return runez.teal(text)


def problem(text):
    return runez.red(text)


def warning(text):
    return runez.orange(text)


def note(text):
    return runez.purple(text)


def progress(text):
    return runez.plain(text)


def workspace_path(text):
    return runez.purple(text)


def workspace_primary(text):
    return runez.bold(text)


def workspace_detail(text):
    return runez.purple(text)


def index_change(text):
    return runez.teal(text)


def worktree_change(text):
    return runez.red(text)


def untracked_change(text):
    return runez.orange(text)
