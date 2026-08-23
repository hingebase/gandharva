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

__all__ = ["gui_error_handler", "to_panel"]

import dataclasses
import functools
import html
import itertools
import pathlib
import tempfile
import traceback
from typing import TYPE_CHECKING

import holoviews as hv  # pyright: ignore[reportMissingTypeStubs]
import matplotlib.figure as mfigure
import pandas as pd
import panel as pn
import pydantic_core
from matplotlib import animation
from panel.pane import HTML, DataFrame
from typing_extensions import override

from gandharva import _utils

from . import _common

if TYPE_CHECKING:
    import gandharva as gd

_TEMPLATE = '<b>{0.__name__}</b>\n<pre style="overflow-y: auto">{1}</pre>'


def gui_error_handler(exc: Exception) -> pn.pane.Alert:
    # Taken from pn.io.handlers.run_app
    return pn.pane.Alert(
        _TEMPLATE.format(type(exc), "".join(traceback.format_exception(exc))),
        alert_type="danger",
        margin=5,
        sizing_mode="stretch_width",
    )


@functools.singledispatch
def to_panel(value: object, app: type["gd.Gandharva"]) -> pn.viewable.Viewable:
    data = pydantic_core.to_jsonable_python(value)
    return _RichDisplay(app).element(data)


@to_panel.register
def _(
    value: pn.viewable.Viewable,
    app: type["gd.Gandharva"],
) -> pn.viewable.Viewable:
    del app
    return value


@to_panel.register
def _(
    value: hv.core.Dimensioned,
    app: type["gd.Gandharva"],
) -> pn.viewable.Viewable:
    if object_ := _utils.undisplayable_info(value, html=True):
        kwargs = dict(app.panel_html_params(), object=object_)
        return HTML(**kwargs)
    # https://github.com/panel-extensions/panel-material-ui/blob/v0.14.2/src/panel_material_ui/pane/base.py#L11-L18
    return pn.panel(value, widget_layout=pn.Column)  # pyright: ignore[reportReturnType, reportUnknownMemberType]


@to_panel.register
def _(
    value: animation.TimedAnimation,
    app: type["gd.Gandharva"],
) -> pn.pane.Video:
    del app
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        p = pathlib.Path(tmp, "plot.mp4")
        value.save(p, writer="ffmpeg", codec="h264_mf")
        return pn.pane.Video(object=p.read_bytes())


@to_panel.register
def _(
    value: mfigure.Figure,
    app: type["gd.Gandharva"],
) -> pn.pane.Matplotlib:
    kwargs = dict(app.panel_matplotlib_params(value), object=value)
    return pn.pane.Matplotlib(**kwargs)


@dataclasses.dataclass
class _RichDisplay(_common.RichDisplay[HTML, DataFrame]):
    app: type["gd.Gandharva"]

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
