import os
import sys


# tty color codes by use-case
PROBLEM = [31]
WARN = [33, 2]
HIGHLIGHT = [37, 1]
POP = [36]
PROGRESS = None
NOTE = [35]

FORMAT_STRING = "\033[%dm%s"
RESET = "\033[0m"


def is_tty():
    """
    :return bool: True if current stdout is a tty
    """
    return sys.stdout.isatty() or "PYCHARM_HOSTED" in os.environ


def plain(text, color=None):
    """Ignore coloring and return plan 'text'"""
    return str(text)


def tty_colored(text, color=None):
    if not color or not text:
        return str(text)
    for code in color:
        text = FORMAT_STRING % (code, text)
    return text + RESET


# By default, do not use colors
colored = plain


def is_color_active():
    """
    :return bool: True if coloring is currently activated
    """
    return colored is not plain


def problem(text):
    return colored(text, PROBLEM)


def warn(text):
    return colored(text, WARN)


def highlight(text):
    return colored(text, HIGHLIGHT)


def pop(text):
    return colored(text, POP)


def progress(text):
    return colored(text, PROGRESS)


def note(text):
    return colored(text, NOTE)


def activate_colors(on):
    """
    :param bool|None on: Set colored output on or off
    """
    global colored
    if on is None:
        on = is_tty()
    colored = tty_colored if on else plain


def simple_plural(word):
    if word.endswith("ch"):
        return "%ses" % word
    return "%ss" % word


def plural(count, what, color=None, on_first=False):
    """
    :param int|list|object count: Count to show
    :param str text: What the count represents
    :param callable|str color: Color to use
    :param bool on_first: If True, the plural applies to first word in 'what' (otherwise, applies to the end)
    :return: Plural form
    """
    if count is not None:
        try:
            count = int(count)
        except (TypeError, ValueError):
            count = len(count) if hasattr(count, "__len__") else 0

    if count and count == 1:
        text = "%s %s" % (count, what)

    elif on_first:
        words = what.split()
        text = "%s %s" % (count, simple_plural(words[0]))
        if len(words) > 1:
            text += " %s" % (" ".join(words[1:]))

    else:
        text = "%s %s" % (count, simple_plural(what))

    if color:
        if callable(color):
            return color(text)
        return colored(text, color)

    return text
