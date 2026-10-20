# Git lint and fixer pre-commit hook

This directory contains a standalone, local Git hook that runs the linters and
fixers configured in `~/.config/vim/plugin/ale.vim`. It does not use Vim, ALE,
or cloud CI. The hook processes staged files only and stages its formatting
changes automatically.

## Install

From the target Git repository, run:

```bash
python3 /path/to/cheatsheets/git-lint-fixer-precommit/bin/git-lint-fixer install
```

The installer creates or updates `.git/hooks/pre-commit`. It refuses to replace
an unrelated existing hook. To remove this hook, run the same command with
`uninstall`.

Install the required tools separately and make them available on `PATH`:

On Debian, system tools can be installed with:

```bash
sudo apt install clang-format shellcheck shfmt
```

Install the Python tools into the existing virtual environment:

```bash
source ~/.pyvenv/v/bin/activate
python -m pip install --upgrade ruff black isort sqlfluff vim-vint yamllint yamlfix
```

For GitHub Actions workflow linting, install `actionlint` separately (for
example, with `go install github.com/rhysd/actionlint/cmd/actionlint@latest`)
and ensure its install directory is on `PATH`. It is only invoked for files
under `.github/workflows/`.

| Filetype | Linter | Fixer |
| --- | --- | --- |
| Python (`.py`) | `ruff check --fix` | `black`, `isort` |
| C++ (`.cc`, `.cpp`, `.cxx`, `.hh`, `.hpp`, `.hxx`) | — | `clang-format` |
| Bash (`.bash`) and shell (`.sh`) | `shellcheck` | `shfmt` |
| SQL (`.sql`) | `sqlfluff lint` | `sqlfluff fix` |
| Vim (`.vim`) | `vint` | — |
| YAML (`.yaml`, `.yml`) | `yamllint` | `yamlfix` |
| GitHub Actions workflows | `actionlint` | — |

The Python language-server configuration is invoked through the equivalent
`ruff` CLI rather than running `pylsp` as a server. For Bash, ShellCheck remains
the linter and `shfmt` is used as the standalone formatter; ALE's ShellCheck
fixer relies on ALE to apply ShellCheck's diff output.

For YAML workflow files under `.github/workflows/`, `actionlint` runs in
addition to `yamllint`. The bundled YAML, SQLFluff, and clang-format
configurations are passed explicitly, so the hook works regardless of the
target repository's current directory.

The hook checks for unstaged edits to any staged file it will process and
stops before running tools if it finds one. This prevents fixers from
accidentally staging unrelated working-tree changes. After a successful tool
run, modified files are added back to the index. A linter error still blocks
the commit; fix the reported issue and commit again.

## Test

Run the standard-library test suite from this directory:

```bash
python3 -m unittest discover -s tests -v
```

The tests use temporary Git repositories and mock executables to verify the
commands and staging behavior without requiring the external lint tools. The
fixtures cover Python, C++, Bash, shell, SQL, Vim, YAML, and YML.

## OTHER SEMI HOOK PRACTICES

**Only `pre-commit` and `pre-push` are native Git hooks.** “Pre-testing” is a workflow step we define, not a Git hook.

| Stage | Native Git hook? | When it runs |
| --- | --- | --- |
| `pre-commit` | Yes | Before creating a commit; failure blocks it |
| Pre-testing / full check | No | Manually through a command that runs mypy, optional Pylint, and tests |
| `pre-push` | Yes | Before pushing; failure blocks the push |

For your local setup, use **`pre-commit` for fast formatting/linting**, plus **one explicit full-check command**. An optional `pre-push` hook can invoke that same command automatically. Both native hooks can be bypassed with `--no-verify`, so they’re convenience safeguards, not enforcement.
