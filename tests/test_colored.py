from mock import patch

from mgit import colored


def test_plural():
    assert colored.plural(None, 'commit') == 'None commits'
    assert colored.plural([], 'commit') == '0 commits'
    assert colored.plural('', 'commit') == '0 commits'
    assert colored.plural(1, 'commit') == '1 commit'
    assert colored.plural('2', 'commit') == '2 commits'

    assert colored.plural(15, 'great dane') == '15 great danes'

    assert colored.plural(7, 'branch') == '7 branches'

    assert colored.plural(1, 'commit behind', on_first=True) == '1 commit behind'
    assert colored.plural('a b c'.split(), 'commit behind', on_first=True) == '3 commits behind'

    colored.activate_colors(True)
    assert colored.plural(1, 'commit', colored.PROBLEM) == '[31m1 commit[0m'
    assert colored.plural(1, 'commit', colored.problem) == '[31m1 commit[0m'
    colored.activate_colors(False)


@patch('sys.stdout.isatty', return_value=False)
def test_colors(*args):
    # Colors are inactive by default when stdout is not a tty
    assert colored.is_tty() is False
    assert colored.is_color_active() is False
    assert colored.problem("foo") == "foo"
    assert colored.tty_colored(None) == "None"

    # activate_colors(None) means "use default setting"
    colored.activate_colors(None)
    assert colored.is_color_active() is False
    assert colored.highlight("foo") == "foo"

    # Turn off coloring explicitly
    colored.activate_colors(False)
    assert colored.is_color_active() is False
    assert colored.pop("foo") == "foo"
    assert colored.warn("foo") == "foo"
    assert colored.progress("foo") == "foo"
    assert colored.note("foo") == "foo"

    # Turn on coloring explicitly
    colored.activate_colors(True)
    assert colored.is_color_active() is True
    assert colored.problem("foo") == '[31mfoo[0m'

    # Go back to default
    colored.activate_colors(None)
    assert colored.is_color_active() is False
    assert colored.highlight("foo") == "foo"
