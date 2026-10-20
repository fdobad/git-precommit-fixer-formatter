from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
EXECUTABLE = PROJECT_DIR / "bin" / "git-lint-fixer"
FIXTURES = PROJECT_DIR / "tests" / "fixtures"


def git(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


class GitLintFixerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.repo = self.root / "repo with spaces"
        self.repo.mkdir()
        self.bin_directory = self.root / "bin"
        self.bin_directory.mkdir()
        self.log_path = self.root / "commands.jsonl"
        self.assertEqual(git("init", "-q", cwd=self.repo).returncode, 0)
        shutil.copytree(FIXTURES, self.repo, dirs_exist_ok=True)
        self.make_fake_tools()
        self.stage_all_fixture_files()
        self.environment = os.environ.copy()
        self.environment["PATH"] = str(self.bin_directory) + os.pathsep + self.environment["PATH"]
        self.environment["GIT_LINT_FIXER_TEST_LOG"] = str(self.log_path)

    def make_fake_tools(self) -> None:
        tool_names = {
            "actionlint",
            "black",
            "clang-format",
            "isort",
            "ruff",
            "shellcheck",
            "shfmt",
            "sqlfluff",
            "vint",
            "yamllint",
            "yamlfix",
        }
        script = """#!/usr/bin/env python3
import json
import os
import pathlib
import sys

with open(os.environ["GIT_LINT_FIXER_TEST_LOG"], "a", encoding="utf-8") as log:
    log.write(json.dumps({"tool": pathlib.Path(sys.argv[0]).name, "args": sys.argv[1:]}) + "\\n")
if pathlib.Path(sys.argv[0]).name == "shfmt":
    target = pathlib.Path(sys.argv[-1])
    target.write_text(target.read_text(encoding="utf-8") + "# formatted\\n", encoding="utf-8")
if os.environ.get("GIT_LINT_FIXER_FAIL_TOOL") == pathlib.Path(sys.argv[0]).name:
    sys.exit(1)
"""
        for name in tool_names:
            executable = self.bin_directory / name
            executable.write_text(script, encoding="utf-8")
            executable.chmod(0o755)

    def stage_all_fixture_files(self) -> None:
        result = git("add", "--all", cwd=self.repo)
        self.assertEqual(result.returncode, 0, result.stderr)

    def run_hook(self, environment: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(EXECUTABLE), "run"],
            cwd=self.repo,
            env=environment or self.environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def command_log(self) -> list[dict[str, object]]:
        return [json.loads(line) for line in self.log_path.read_text(encoding="utf-8").splitlines()]

    def test_invokes_configured_tools_for_each_filetype(self) -> None:
        result = self.run_hook()
        self.assertEqual(result.returncode, 0, result.stderr)

        invocations = self.command_log()
        tools = [entry["tool"] for entry in invocations]
        self.assertEqual(tools.count("ruff"), 1)
        self.assertEqual(tools.count("black"), 1)
        self.assertEqual(tools.count("isort"), 1)
        self.assertIn("clang-format", tools)
        self.assertEqual(tools.count("shellcheck"), 2)
        self.assertEqual(tools.count("shfmt"), 2)
        self.assertEqual(tools.count("sqlfluff"), 2)
        self.assertIn("vint", tools)
        self.assertEqual(tools.count("yamlfix"), 2)
        self.assertEqual(tools.count("yamllint"), 2)
        self.assertIn("actionlint", tools)

        sqlfluff_commands = [entry["args"] for entry in invocations if entry["tool"] == "sqlfluff"]
        self.assertEqual(
            [arguments[0] for arguments in sqlfluff_commands],
            ["fix", "lint"],
        )

    def test_stages_formatter_output(self) -> None:
        result = self.run_hook()
        self.assertEqual(result.returncode, 0, result.stderr)
        staged = git("show", ":sh/sample.sh", cwd=self.repo)
        self.assertEqual(staged.returncode, 0, staged.stderr)
        self.assertIn("# formatted", staged.stdout)

    def test_linter_failure_blocks_commit_but_runs_fixers(self) -> None:
        environment = self.environment.copy()
        environment["GIT_LINT_FIXER_FAIL_TOOL"] = "shellcheck"
        result = self.run_hook(environment)
        self.assertNotEqual(result.returncode, 0)
        tools = [entry["tool"] for entry in self.command_log()]
        self.assertEqual(tools.count("shellcheck"), 2)
        self.assertEqual(tools.count("shfmt"), 2)

    def test_refuses_unstaged_changes_before_running_tools(self) -> None:
        path = self.repo / "python" / "sample.py"
        path.write_text(path.read_text(encoding="utf-8") + "# unstaged\n", encoding="utf-8")
        result = self.run_hook()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Unstaged edits", result.stderr)
        self.assertFalse(self.log_path.exists())

    def test_installs_and_uninstalls_only_its_own_hook(self) -> None:
        install = subprocess.run(
            [sys.executable, str(EXECUTABLE), "install"],
            cwd=self.repo,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(install.returncode, 0, install.stderr)
        hook = self.repo / ".git" / "hooks" / "pre-commit"
        self.assertTrue(hook.is_file())
        self.assertTrue(os.access(hook, os.X_OK))
        self.assertIn("managed by git-lint-fixer-precommit", hook.read_text())
        execution = subprocess.run(
            [str(hook)],
            cwd=self.repo,
            env=self.environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(execution.returncode, 0, execution.stderr)

        uninstall = subprocess.run(
            [sys.executable, str(EXECUTABLE), "uninstall"],
            cwd=self.repo,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(uninstall.returncode, 0, uninstall.stderr)
        self.assertFalse(hook.exists())

    def test_does_not_replace_an_unrelated_hook(self) -> None:
        hook = self.repo / ".git" / "hooks" / "pre-commit"
        hook.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(EXECUTABLE), "install"],
            cwd=self.repo,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Refusing to replace unrelated hook", result.stderr)
        self.assertEqual(hook.read_text(encoding="utf-8"), "#!/bin/sh\nexit 0\n")


if __name__ == "__main__":
    unittest.main()
