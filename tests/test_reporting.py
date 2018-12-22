import pytest

from mgit.colored import activate_colors
from mgit.git import GitRunReport


def check_sorting(input, expected, max_chars=160):
    activate_colors(False)
    if not isinstance(input, GitRunReport):
        input = GitRunReport(problem=input.split())
    assert isinstance(input, GitRunReport)
    s = input.representation(max_chars=max_chars)
    assert s == expected


def test_reporting():
    assert GitRunReport.not_git().has_problems

    # Sorting
    check_sorting("a b c", "a; b; c")                           # Messages stay in order they were provided
    check_sorting("a b c b a", "a; b; c")                       # No dupes
    check_sorting("a <b c", "b; a; c")                          # < pushes message to front
    check_sorting("a <b <c d", "c; b; a; d")                    # < ordered pushing
    check_sorting("a <b >c d", "b; a; d; c")                    # > pushed message to back
    check_sorting("a <b >c <d >e f", "d; b; a; f; c; e")        # > ordered pushing

    # Typical issues
    check_sorting(GitRunReport.not_git(), "not a git checkout")
    check_sorting(GitRunReport.not_git().cant_pull(), "can't pull; not a git checkout")
    check_sorting(GitRunReport().cant_pull(), "can't pull")
    check_sorting(GitRunReport().cant_pull("foo"), "can't pull; foo")

    # Adding nothing does nothing
    check_sorting(GitRunReport().cant_pull().add(), "can't pull")
    check_sorting(GitRunReport().cant_pull().add(None), "can't pull")
    check_sorting(GitRunReport().cant_pull().add([]), "can't pull")
    check_sorting(GitRunReport().cant_pull().add(""), "can't pull")

    # Adding bogus things is detected
    with pytest.raises(Exception):
        GitRunReport().cant_pull().add(a=1)

    # Cumulating
    r1 = GitRunReport(problem="p1", note="n1")
    r2 = GitRunReport(problem="p2", note="n2")
    check_sorting(GitRunReport(r1).add(r2), "p1; p2; n1; n2")

    # Filtering
    check_sorting(GitRunReport(r1).add(problem=r2), "p1; p2; n1")

    # Problems come ahead of notes
    check_sorting(GitRunReport().add(problem="p1").add(problem='p2').add(problem="p3"), "p1; p2; p3")
    check_sorting(GitRunReport().add(problem="p1", note='n1').add(problem="p2"), "p1; p2; n1")

    # Progress comes ahead of notes, but after problems
    check_sorting(
        GitRunReport().add(
            note="n1 <n2".split(),
            progress='p1 p2 <p3'.split(),
            problem="prob1"
        ),
        "prob1; p3; p1; p2; n2; n1"
    )


def test_truncating():
    # Lots of reports
    problems = ["some problem", "some other problem", "and yet another"]
    progress = ["some progress", "and some more"]
    notes = ["one note", "two notes", "and some really looooong note that just has to be truncated", "yup"]

    expected = 'some problem; some other problem; and yet another; some progress; and some more; one note; two notes; and some really looooong note that just has to be trunc...'   # noqa

    r = GitRunReport(problem=problems, progress=progress, note=notes)
    check_sorting(r, expected)

    # Really long problem shadowing progress/notes
    problems = ["some problem", "plus some other problem", "and yet another"]
    problems.append("even more problems")
    problems.append("and some really really really loooong problem report that just has to be truncated")
    progress = ["progress won't show", "since problem too long"]

    expected = 'some problem; plus some other problem; and yet another; even more problems; and some really really really loooong problem report that just has to be truncate...'   # noqa
    r = GitRunReport(problem=problems, progress=progress, note="note won't show either")
    check_sorting(r, expected)

    check_sorting(r, "some problem;...", max_chars=16)
