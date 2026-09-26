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

__all__ = ["to_cli"]

import functools
import itertools
import os
import pathlib
import shutil
import subprocess  # ruff: ignore[suspicious-subprocess-import]
import sys
import tempfile
from typing import TYPE_CHECKING

import holoviews as hv  # pyright: ignore[reportMissingTypeStubs]
import matplotlib.figure as mfigure
import matplotlib.pyplot as plt
import panel as pn
import pydantic_core
import rich
import textual_image.renderable
from matplotlib import animation
from rich.table import Table
from typing_extensions import override

from gandharva import testing
from gandharva._typing import Gandharva

from . import _common

if TYPE_CHECKING:
    from _typeshed import StrPath


def to_cli(value: object, app: Gandharva, *, json: bool = False) -> None:
    if json:
        data = pydantic_core.to_jsonable_python(value, inf_nan_mode="null")
        rich.print_json(data=data, allow_nan=False)
    else:
        _to_cli(value, app)


@functools.singledispatch
def _to_cli(value: object, app: Gandharva) -> None:
    del app
    data = pydantic_core.to_jsonable_python(value)
    elem = _RichDisplay().element(data)
    rich.print(elem)


@_to_cli.register(rich.console.ConsoleRenderable)
@_to_cli.register(rich.console.RichCast)
def _(
    value: rich.console.ConsoleRenderable | rich.console.RichCast,
    app: Gandharva,
) -> None:
    del app
    rich.print(value)


@_to_cli.register
def _(value: None, app: Gandharva) -> None:
    pass


@_to_cli.register
def _(value: pn.viewable.Viewable, app: Gandharva) -> None:
    _to_cli(_common.get_plot(value), app)


@_to_cli.register
def _(value: hv.core.Dimensioned, app: Gandharva) -> None:
    _to_cli(app.to_matplotlib(value), app)


@_to_cli.register
def _(value: animation.TimedAnimation, app: Gandharva) -> None:
    ffplay = shutil.which("ffplay", path=_ffplay_path())
    if not ffplay:
        rich.print(  # TODO(): #4
            "Please install FFmpeg and expose the executables 'ffmpeg', "
            "'ffplay' via PATH or "
            "matplotlib.rcParams['animation.ffmpeg_path']",
        )
        sys.exit(1)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        filename = str(pathlib.Path(tmp, "plot.mp4"))
        value.save(filename, writer="ffmpeg", codec="libopenh264")
        subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true]
            [
                ffplay,
                *(("-loop", "0"), ("-autoexit", "-fs"))[testing.TESTING],
                "-window_title", app.app_title() or "Gandharva",
                filename,
            ],
            check=True,
        )


@_to_cli.register
def _(value: mfigure.Figure, app: Gandharva) -> None:
    with testing.BytesIO() as f:
        try:
            value.savefig(f)  # pyright: ignore[reportUnknownMemberType]
        finally:
            plt.close(value)
        sixel = textual_image.renderable.Image(f)
    _to_cli(sixel, app)


class _RichDisplay(_common.RichDisplay[str, Table]):
    @override
    def text(self, data: str) -> str:
        return data

    @override
    def long_table(self, data: _common.LongTable) -> Table:
        table = Table(show_header=False)
        for row in data:
            table.add_row(*map(str, row))
        return table

    @override
    def wide_table(self, data: _common.WideTable) -> Table:
        columns = sorted(set(itertools.chain.from_iterable(data)))
        table = Table(*columns, show_header=True)
        for row in data:
            table.add_row(*[str(row.get(col, "")) for col in columns])
        return table


def _ffplay_path() -> "StrPath | None":
    ffmpeg = animation.FFMpegWriter.bin_path()
    pref = pathlib.Path(ffmpeg).parent
    if pref == pathlib.Path() and not ffmpeg.startswith(
        ("./", ".\\") if sys.platform == "win32" else "./",
    ):
        return None
    pref = pref.resolve(strict=True)

    # Copied from shutil.which
    path = os.getenv("PATH")
    if path is None:
        try:
            path = os.confstr("CS_PATH")
        except (AttributeError, ValueError):
            path = os.defpath

    return f"{pref}{os.pathsep}{path}" if path else pref
