# Code Size

Measured with:

```shell
tokei src/
tokei tests/
```

Branches compared:

- `main` at `b4f528c`
- `v2gpt` at `d14ebd5`

## Summary

| Area | Branch | Files | Lines | Code | Comments | Blanks |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `src/` | `main` | 3 | 1,439 | 924 | 184 | 331 |
| `src/` | `v2gpt` | 4 | 1,440 | 961 | 127 | 352 |
| `tests/` | `main` | 5 | 188 | 123 | 16 | 49 |
| `tests/` | `v2gpt` | 4 | 351 | 230 | 25 | 96 |
| `src/ + tests/` | `main` | 8 | 1,627 | 1,047 | 200 | 380 |
| `src/ + tests/` | `v2gpt` | 8 | 1,791 | 1,191 | 152 | 448 |

## Delta

| Area | Files | Lines | Code | Comments | Blanks |
| --- | ---: | ---: | ---: | ---: | ---: |
| `src/` | +1 | +1 | +37 | -57 | +21 |
| `tests/` | -1 | +163 | +107 | +9 | +47 |
| `src/ + tests/` | 0 | +164 | +144 | -48 | +68 |
