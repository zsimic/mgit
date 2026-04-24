# mgit 2.0

> *User draft*, don't edit

Ideas for mgit v2.0

`mgit` v2.0 will have subcommands (instead of just CLI flags).
Instead of `mgit -f`, we want to run just `mgit f`
Most used commands can be invoked with just their first letter, ie: `mgit f` is the same as `mgit fetch`

mgit can operate on a single repo, or multiple repos at once.
If `mgit fetch` is run in a folder that has multipl git repos, then `fetch` is run on every single repo.
Not all commands apply to multiple repos, some are single repo only

`mgit main` means checkout default branch (it can be called `master` or whatever - we still refer to it as "main")

- Figure out the default branch, allow referring to it as `main` (even when it really is called `master`)
- Use `argparse` instead of `click` library
- We do want simple coloring (in terminal), but we also would like to keep the dependencies to a minimum
  - Consider using `rich` library, any other great libraries for coloring?
  - How much effort does it take to have coloring using std-lib only?

The `mgit clone` command will operate from a config located in ~/.config/mgit/config.toml

```toml
[locations]
"~/dev" = "git.mycompany.com/*"
"~/github" = "github.com/zsimic/*"
"~/ext" = "github.com/*"
```

Or perhaps:
```toml
locations = [
    { match = "github.com/zsimic/*", dir = "~/github" },
    { match = "github.com/*",        dir = "~/ext" },
    { match = "git.mycompany.com/*", dir = "~/dev" }
]
```

The above would make it so that a `mgit clone https://github.com/zsimic/dotfiles/...` goes to `~/github/dotfiles`
The location would be determined via a "best match" approach (the most specific url matched gets picked)

```shell
mgit    # status
mgit g  # groom, clean up local branches + go back to main (if in one repo)
mgit s  # status
mgit m  # git checkout <main>
mgit b  # show local branches (meh, could just run 'git branch', interesting in multi-repo case)
mgit p  # pull (only pulls when no pending changes)
mgit f  # fetch
mgit c  # clone

mgit groom-remote # Clean merged remote branches
mgit groom-all    # Clean local and merged remote branches

mgit zap-zap  # Do a git --reset --hard + clean -fdx (nuke all changes, get back to pristine state)
```

Example output:
```shell
~/github$ mgit
~/github: 4 github/codrsquad
        pickley: [main] up to date*  last fetch 3w 6d ago
portable-python: [main] up to date*  last fetch 4d 10h ago
          runez: [main] up to date
      setupmeta: [main] up to date*  last fetch 3w 6d ago
```


# Most common usage (using v1 as illustration)

```shell
mgit  # shows current status, which branch we're on, how old is the last fetch, and if there are pending changes

# Let's say that the last fetch was 2 days ago, so I do a quick fetch to check if anything's new on remote
mgit -f  # shows '1 behind' for example
mgit -p  # ok, pull it then (but I do it in 2 steps, I like to know... and not pull in always blindly..)

# Iterate, commit, PR, ...

mgit  # check status again (status is most common mgit run for me)

# Iterate, commit, PR, ... and let's say PR is merged

mgit -f  # shows that the current branch can be cleaned now
git checkout main  # or was it master? damn, let's check `git branch` real quick
mgit -p   # pull main branch (so we can indeed clean our prev working branch)
mgit -cl  # clean our now orphan/merged local branch
```


We want to change the above to this with v2:

```shell
mgit
mgit f
mgit p
mgit
mgit f
mgit g  # does all of the: checkout main, pull, clean local business all in one go
```
