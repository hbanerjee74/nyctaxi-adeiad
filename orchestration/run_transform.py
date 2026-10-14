"""Run the dbt project: `dbt build` against the domain target."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(command, cwd, env):
    return subprocess.run(command, cwd=cwd, env=env, check=False)


def run_transform(runner: Callable = _run, target: str = "domain") -> int:
    env = os.environ.copy()
    env["DBT_PROFILES_DIR"] = str(ROOT / "transformation")
    command = [sys.executable, "-m", "dbt.cli.main", "build", "--target", target]
    return runner(command, cwd=ROOT / "transformation", env=env).returncode


def main() -> int:
    return run_transform()


if __name__ == "__main__":
    raise SystemExit(main())
