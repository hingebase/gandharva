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

__all__ = ["gui_error_handler", "reset_contextbar", "to_panel"]

import dataclasses
import functools
import html
import itertools
import pathlib
import tempfile
import traceback

import holoviews as hv  # pyright: ignore[reportMissingTypeStubs]
import matplotlib.figure as mfigure
import matplotlib.pyplot as plt
import pandas as pd
import panel as pn
import pydantic_core
from matplotlib import animation
from panel.pane import HTML, DataFrame
from typing_extensions import override

from gandharva import _utils
from gandharva._typing import Gandharva

from . import _common

_TEMPLATE = '<b>{0.__name__}</b>\n<pre style="overflow-y: auto">{1}</pre>'


@functools.singledispatch
def gui_error_handler(exc: Exception) -> pn.pane.Alert:
    # Taken from pn.io.handlers.run_app
    return pn.pane.Alert(
        _TEMPLATE.format(type(exc), "".join(traceback.format_exception(exc))),
        alert_type="danger",
        margin=5,
        sizing_mode="stretch_width",
    )


@gui_error_handler.register(_utils.ReturnThePanelWrappedInThisError)
def _(
    exc: _utils.ReturnThePanelWrappedInThisError[pn.pane.Alert],
) -> pn.pane.Alert:
    return exc.obj


def reset_contextbar(contextbar: pn.rx, contextbar_open: pn.rx) -> None:
    contextbar.rx.value = []
    contextbar_open.rx.value = False


@functools.singledispatch
def to_panel(
    value: object,
    app: type[Gandharva],
    contextbar: pn.rx,
    contextbar_open: pn.rx,
) -> pn.viewable.Viewable:
    reset_contextbar(contextbar, contextbar_open)
    data = pydantic_core.to_jsonable_python(value)
    return _RichDisplay(app).element(data)


@to_panel.register
def _(
    value: pn.viewable.Viewable,
    app: type[Gandharva],
    contextbar: pn.rx,
    contextbar_open: pn.rx,
) -> pn.viewable.Viewable:
    del app
    reset_contextbar(contextbar, contextbar_open)
    return value


@to_panel.register
def _(
    value: hv.core.Dimensioned,
    app: type[Gandharva],
    contextbar: pn.rx,
    contextbar_open: pn.rx,
) -> pn.viewable.Viewable:
    if object_ := _utils.undisplayable_info(value, html=True):
        kwargs = dict(app.panel_html_params(), object=object_)
        return HTML(**kwargs)
    # https://github.com/panel-extensions/panel-material-ui/blob/v0.14.2/src/panel_material_ui/pane/base.py#L11-L18
    pane = pn.pane.HoloViews(
        value,
        widget_layout=pn.Column,
        widget_location="top",
    )
    if column := pane.widget_box:
        contextbar.rx.value = [column]
        contextbar_open.rx.value = True
    else:
        reset_contextbar(contextbar, contextbar_open)
    return pane


@to_panel.register
def _(
    value: animation.TimedAnimation,
    app: type[Gandharva],
    contextbar: pn.rx,
    contextbar_open: pn.rx,
) -> pn.pane.Video:
    del app
    reset_contextbar(contextbar, contextbar_open)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        p = pathlib.Path(tmp, "plot.mp4")
        value.save(p, writer="ffmpeg", codec="libopenh264")
        return pn.pane.Video(object=p.read_bytes())


@to_panel.register
def _(
    value: mfigure.Figure,
    app: type[Gandharva],
    contextbar: pn.rx,
    contextbar_open: pn.rx,
) -> pn.pane.Matplotlib:
    try:
        reset_contextbar(contextbar, contextbar_open)
        kwargs = dict(app.panel_matplotlib_params(value), object=value)
    finally:
        plt.close(value)  # https://panel.holoviz.org/reference/panes/Matplotlib.html#using-the-matplotlib-pyplot-interface
    return pn.pane.Matplotlib(**kwargs)


@dataclasses.dataclass
class _RichDisplay(_common.RichDisplay[HTML, DataFrame]):
    app: type[Gandharva]

    @override
    def text(self, data: str) -> HTML:
        kwargs = dict(self.app.panel_html_params(), object=html.escape(data))
        return HTML(**kwargs)

    @override
    def long_table(self, data: _common.LongTable) -> DataFrame:
        df = pd.DataFrame(list(data), dtype=object)
        return self._dataframe(df, header=False)

    @override
    def wide_table(self, data: _common.WideTable) -> DataFrame:
        columns = sorted(set(itertools.chain.from_iterable(data)))
        df = pd.DataFrame.from_records(data, columns=columns)
        return self._dataframe(df, header=True)

    def _dataframe(
        self,
        df: pd.DataFrame,
        *,
        header: bool = False,
    ) -> DataFrame:
        kwargs = dict(
            self.app.panel_dataframe_params(),
            header=header,
            object=df,
        )
        return DataFrame(**kwargs)
