# Bootstrap your OSX for tox

OSX's system python doesn't come with `pip` and `virtualenv` installed (you need to do this only once...)

Install them like so:

```
ls /Library/Python/2.7/site-packages/pip* || (sudo easy_install pip && sudo pip install virtualenv)
```

Install tox:

```
sudo pip install tox
```

Refrain from installing anything else in the system python.
You only need `tox` in one place, even if you have several python installations
(tox will create venvs properly for those other python installations)


# Build

To build for local development, run:

```
tox -e venv
```

This creates a virtual environment in `./.venv`, you can now open the project in PyCharm.

Go to menu **PyCharm** -> **Preferences** ->  **Project : ...** -> **Project Interpreter**  -> **Add local**
-> "**Existing environment**" should be already selected, with the path to local `.venv` already pre-populated
-> hit **OK**


# Build pex

```
tox -e pex
```

The pex is now in `./tox/mgit`


# Run tests

```
tox
```

This will run the tests + linters against python 2.7 and 3.6
