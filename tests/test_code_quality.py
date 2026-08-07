# Copyright 2026 hingebase

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied. See the License for the specific language governing
# permissions and limitations under the License.

"""Type checking and linting."""

import contextlib
import importlib.metadata
import os
import runpy
import subprocess  # ruff: ignore[suspicious-subprocess-import]
import sys
from collections.abc import Generator
from typing import NoReturn

import pytest

if sys.platform == "win32":
    from contextlib import (
        nullcontext as _astral_context,  # pyright: ignore[reportAssignmentType]
    )
else:
    @contextlib.contextmanager
    def _astral_context(monkeypatch: pytest.MonkeyPatch) -> Generator[object]:
        def execvp(executable: str, args: list[str]) -> NoReturn:
            nonlocal patched
            patched = True
            sys.exit(subprocess.call(args, executable=executable))  # ruff: ignore[subprocess-without-shell-equals-true]
        patched = False
        monkeypatch.setattr(os, "execvp", execvp)
        try:
            yield
        finally:
            assert patched


def test_basedpyright(monkeypatch: pytest.MonkeyPatch) -> None:
    """Type checking with basedpyright."""
    argv = [
        "basedpyright",
        "--pythonpath", sys.executable,
        # "--threads",  # Enable if better performance observed
    ]
    monkeypatch.setattr(sys, "argv", argv)
    _run_module("basedpyright")


@pytest.mark.skipif(
    os.getenv("PIXI_PROJECT_NAME") == "gandharva"
        and os.getenv("PIXI_ENVIRONMENT_NAME", "default") != "default",
    reason="It's unnecessary to run Ruff for each Python environment",
)
def test_ruff(monkeypatch: pytest.MonkeyPatch) -> None:
    """Linting with Ruff."""
    args = ["ruff", "check", "--ignore", "FIX002"]
    try:
        importlib.metadata.distribution("ruff")
    except ModuleNotFoundError:
        subprocess.run(args, check=True)  # ruff: ignore[subprocess-without-shell-equals-true]
    else:
        monkeypatch.setattr(sys, "argv", args)
        with _astral_context(monkeypatch):
            _run_module("ruff")


def _run_module(module_name: str) -> None:
    try:
        runpy.run_module(module_name, run_name="__main__")
    except SystemExit as e:
        code = e.code
    else:
        return
    assert code == 0
