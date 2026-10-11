# Type checking: v2.0.0 → v2.1

What v2.1 changed in response to type checker findings on v2.0.0.

| Checker | Version | v2.0.0 | v2.1 | Actionable | Design | Minor |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| ty | 0.0.86 | 8 | 0 | 8 | 2 | 0 |
| pyrefly | 1.3.2 | 7 | 0 | 7 | 1 | 0 |
| pyright | 1.1.414 | 1 | 0 | 1 | 1 | 0 |
| mypy | 2.4.0 | 4 | 0 | 4 | 0 | 2 |
| basedpyright | 1.40.2 | 825 | 952 | 87 | 1 | 2 |
| zuban | 0.10.0 | 0 | 0 | 0 | 0 | 0 |

- **v2.0.0**, **v2.1**: findings on that release's `src/` and `tests/`, both checked with v2.1's
  settings (`tox.ini`, `pyproject.toml`).
- **Actionable**: v2.0.0 findings resolved by a change in v2.1.
- **Design**, **Minor**: how many of the changes listed under [Design](#design) and
  [Minor](#minor) the checker spotted. None pointed at misbehaving code: pyright already checked
  `src/` before v2.1.
- basedpyright counts include its warnings: 3 errors + 822 warnings on v2.0.0, 0 + 952 on v2.1
  (which has more code).
- v2.1's zeros need runez 5.10.2, which fixed an annotation mgit tripped on (see
  [Fixed in runez](#fixed-in-runez)).

## Design

- CLI hooks take their argument positionally (`add_arguments(cls, _parser, /)`, ...): the base
  classes name it `_parser`, `_namespace` and `_project_dir` (unused there), the overrides
  `parser`, `namespace` and `project_dir`, which breaks any call passing it by keyword [ty, pyrefly]
- `@cli_command` returns the class it decorates: it was typed as returning a plain
  `type[CliCommand]`, so checkers lost each command's own attributes [ty, pyright, basedpyright]

## Fixed in runez

mgit tripped on this runez annotation, fixed in runez 5.10.2 rather than worked around.

- `runez.date.DEFAULT_DURATION_SPAN` accepts any `int` (it was inferred as `Literal[2]`) [ty,
  pyrefly]

## Minor

The checker was right, the fix changes little in practice.

- `GitRunReport`'s message lists are annotated `list[str]` [mypy]
- `FolderTargetCommand` says it's abstract (`ABC`) [basedpyright]
- `argparse._SubParsersAction` annotation gets its type argument [basedpyright]
- Tests: `run_git_command()` keeps its arguments a tuple [mypy]

## Not from a type checker

Found while setting up the type checkers.

- The wheel shipped without its `LICENSE` file (`license-files` named `LICENSE.txt`)
- mgit claimed Python 3.9 support, but runez requires 3.10 since 5.4: on 3.9, mgit got runez 5.3
  or older. mgit now requires 3.10
- `tox -e style` failed on a rule nobody added: ruff's `extend-select` adds to ruff's default
  rules, which grow across releases. mgit now uses `select`, exactly the rules listed
