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
import traceback
from typing import TYPE_CHECKING

import pandas as pd
import panel as pn
import pydantic_core
from panel.pane import HTML, DataFrame
from typing_extensions import override

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
