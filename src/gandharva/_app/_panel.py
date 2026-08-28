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

__all__ = ["App"]

import asyncio
import contextlib
import inspect
import math
from collections.abc import Callable, Iterable, Mapping
from typing import TYPE_CHECKING, cast

import lumen.schema  # pyright: ignore[reportMissingTypeStubs]
import panel as pn
import panel_material_ui as pmui
import pydantic
from bokeh.server.contexts import BokehSessionContext
from hypothesis_jsonschema import _resolve  # ruff: ignore[import-private-name]
from typing_extensions import Any, TypeVar, final, override

import gandharva as gd
from gandharva import _convert

from . import _base, _pydantic

if TYPE_CHECKING:
    from _typeshed import StrPath
    from panel.io.application import TViewable
    from panel.viewable import Viewable
    from tornado.httputil import HTTPServerRequest

_NINF = -math.inf
_Panels = dict[
    str,
    "Viewable | pn.viewable.Viewer | Callable[[], TViewable] | StrPath",
    # i.e. TViewableFuncOrPath but not BaseTemplate
    # See https://github.com/holoviz/panel/issues/2476
]
_T = TypeVar("_T", default=type[pn.widgets.WidgetBase])
_Widgets = Iterable[tuple[str, pn.widgets.WidgetBase]]
_WidgetType = tuple[_T, dict[str, object]]


class App(_pydantic.App):
    panel_event_loop: asyncio.AbstractEventLoop
    panel_request: "HTTPServerRequest"

    @classmethod
    def panel_button_params(cls) -> gd.typing.ButtonParameters:
        return {"color": "primary", "label": "Submit"}

    @classmethod
    def panel_dataframe_params(cls) -> gd.typing.DataFrameParameters:
        return {"index": False}

    @classmethod
    def panel_html_params(cls) -> gd.typing.HTMLParameters:
        return {}

    @classmethod
    def panel_jsonschema_params(cls) -> gd.typing.JSONSchemaParameters:
        return {}

    @classmethod
    def panel_markdown_params(cls) -> gd.typing.MarkdownParameters:
        return {}

    @classmethod
    def panel_page_params(cls) -> gd.typing.PageParameters:
        title = _base.normalize(cls.__name__).replace("-", " ")
        return {"sidebar_width": 500, "title": title[:1].upper() + title[1:]}

    @classmethod
    def __panel__(cls) -> pmui.Page:
        async def main(clicked: bool) -> "Viewable":  # ruff: ignore[boolean-type-hint-positional-argument]
            loop = asyncio.get_running_loop()
            result, stack = await asyncio.to_thread(
                cls._panel_update, submit, page, loop, args, clicked=clicked)
            if task := asyncio.current_task(loop):
                task.add_done_callback(
                    lambda task: task.get_loop().call_later(1, stack.close))
            else:  # Unlikely
                stack.close()
            return result

        model = cls.to_pydantic()
        sidebar, widgets = _Sidebar.build(
            cls.panel_jsonschema_params(),
            # https://github.com/pydantic/pydantic/issues/12023
            _resolve.resolve_all_refs(model.model_json_schema())["properties"],  # pyright: ignore[reportArgumentType, reportUnknownMemberType]
        )
        args = (model, widgets)
        submit = pmui.Button(**dict(cls.panel_button_params(), on_click=None))
        sidebar.append(
            pmui.Row(
                pn.Spacer(sizing_mode="stretch_width"),
                submit,
                pn.Spacer(sizing_mode="stretch_width"),
            ),
        )
        kwargs = dict(
            cls.panel_page_params(),
            main=[pn.bind(main, submit)],
            sidebar=sidebar,
        )
        page = pmui.Page(**kwargs)
        return page

    @classmethod
    @final
    def to_panels(cls, prefix: str = "") -> _Panels:
        # https://github.com/fastapi/fastapi/blob/0.136.1/fastapi/routing.py#L1288-L1292
        if prefix:
            if not prefix.startswith("/"):
                message = "A path prefix must start with '/'"
                raise ValueError(message)
            if prefix.endswith("/"):
                message = (
                    "A path prefix must not end with '/', as the routes will "
                    "start with '/'"
                )
                raise ValueError(message)

        panels: _Panels = {prefix or "/": cls.__panel__}
        prefix += "/"
        for child in cls.children:
            panels |= child.to_panels(prefix + child.app_normalized_name())
        return panels

    @classmethod
    def _panel_main(
        cls,
        loop: asyncio.AbstractEventLoop,
        model: type[pydantic.BaseModel],
        widgets: _Widgets,
        *,
        clicked: bool = False,
    ) -> "Viewable":
        if not clicked:
            kwargs = dict(
                cls.panel_markdown_params(),
                object=cls.app_description(),
            )
            return pn.pane.Markdown(**kwargs)
        obj = {k: v.value for k, v in widgets}
        try:
            data = model.model_validate(obj)
        except pydantic.ValidationError as e:
            result = [
                {
                    "type": detail["type"],
                    "loc": ".".join(map(str, detail["loc"])),
                    "msg": detail["msg"],
                }
                for detail in e.errors(
                    include_url=False,
                    include_context=False,
                    include_input=False,
                )
            ]
        else:
            self = cls(run_mode="gui")
            self.panel_event_loop = loop
            if curdoc := pn.state.curdoc:
                ctx = curdoc.session_context
                if (
                    isinstance(ctx, BokehSessionContext)
                    and (request := ctx.request)
                ):
                    self.panel_request = cast("HTTPServerRequest", request)
            with self.from_pydantic(data):
                result = self.main()
        return _convert.to_panel(result, cls)

    @classmethod
    def _panel_update(
        cls,
        submit: pmui.Button,
        page: pmui.Page,
        loop: asyncio.AbstractEventLoop,
        args: tuple[type[pydantic.BaseModel], _Widgets],
        *,
        clicked: bool = False,
    ) -> tuple["Viewable", contextlib.ExitStack]:
        with contextlib.ExitStack() as stack:
            stack.enter_context(submit.param.update(disabled=True))
            stack.enter_context(page.param.update(busy=True))
            try:
                result = cls._panel_main(loop, *args, clicked=clicked)
            except Exception as e:  # ruff: ignore[blind-except]
                result = _convert.gui_error_handler(e)
            return result, stack.pop_all()


class _Sidebar(lumen.schema.JSONSchema):
    @classmethod
    def build(
        cls,
        kwargs: gd.typing.JSONSchemaParameters,
        schema: dict[str, pydantic.JsonValue],
    ) -> tuple[list["Viewable"], _Widgets]:
        object_: dict[str, object] = {}
        for k, v in schema.items():
            match v:
                case {"default": default}:
                    object_[k] = default
                case {"type": "array"}:
                    object_[k] = []
                case _:
                    pass
        self = cls(**dict(kwargs, multi=False, object=object_, schema=schema))
        return self.layout.objects, self._widgets.items()  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]

    @override
    def _array_type(self, schema: Mapping[str, Any]) -> _WidgetType:
        match schema:
            case {"items": {"enum": [*options]}}:
                kwargs: dict[str, object] = {"options": options}
                if helper_text := _helper_text(schema):
                    # The implementation of `pmui.(Multi)Select` is
                    # different from other widgets, and `sx` doesn't
                    # apply to the helper text
                    # Truncating the description to the summary line
                    kwargs["helper_text"] = _base.summary(helper_text)
                return pmui.MultiSelect, kwargs
            case _:
                return pn.widgets.JSONEditor, {"menu": False, "schema": schema}

    @override
    def _boolean_type(self, schema: Mapping[str, object]) -> _WidgetType[type]:
        # https://github.com/panel-extensions/panel-material-ui/issues/392
        return pmui.Checkbox, {"size": "small"}

    @override
    def _enum(self, schema: Mapping[str, object]) -> _WidgetType[type]:
        kwargs = {"options": schema["enum"], "size": "small"}
        if helper_text := _helper_text(schema):
            kwargs["helper_text"] = _base.summary(helper_text)
        return pmui.Select, kwargs

    @override
    def _integer_type(
        self,
        schema: Mapping[str, int],
    ) -> tuple[type, dict[str, Any]]:
        kwargs = _kwargs(schema)
        start = max(
            schema.get("exclusiveMinimum", _NINF) + 1,
            schema.get("minimum", _NINF),
        )
        end = min(
            schema.get("exclusiveMaximum", math.inf) - 1,
            schema.get("maximum", math.inf),
        )
        match start > _NINF, end < math.inf:
            case True, True:
                if start < end and "helper_text" not in kwargs:
                    kwargs["fixed_start"] = int(start)
                    kwargs["fixed_end"] = int(end)
                    return pn.widgets.EditableIntSlider, kwargs
                if start > end:
                    message = f"Invalid schema: {schema}"
                    raise ValueError(message)
                kwargs["start"] = kwargs["end"] = int(end)
            case True, False:
                kwargs["start"] = int(start)
            case False, True:
                kwargs["end"] = int(end)
            case False, False:
                pass
        kwargs["size"] = "small"
        return pmui.IntInput, kwargs

    @override
    def _number_type(
        self,
        schema: Mapping[str, float],
    ) -> tuple[type, dict[str, Any]]:
        kwargs = _kwargs(schema)
        start = schema.get("exclusiveMinimum", _NINF)
        if start > _NINF:
            start = math.nextafter(start, math.inf)
        start = max(start, schema.get("minimum", _NINF))
        end = schema.get("exclusiveMaximum", math.inf)
        if end < math.inf:
            end = math.nextafter(end, _NINF)
        end = min(end, schema.get("maximum", math.inf))
        match start > _NINF, end < math.inf:
            case True, True:
                if start < end and "helper_text" not in kwargs:
                    kwargs["fixed_start"] = start
                    kwargs["fixed_end"] = end
                    return pn.widgets.EditableFloatSlider, kwargs
                if start > end:
                    message = f"Invalid schema: {schema}"
                    raise ValueError(message)
                kwargs["start"] = kwargs["end"] = end
            case True, False:
                kwargs["start"] = start
            case False, True:
                kwargs["end"] = end
            case False, False:
                pass
        kwargs["size"] = "small"
        return pmui.FloatInput, kwargs

    def _object_type(
        self,
        schema: Mapping[str, object],
    ) -> _WidgetType[type[pn.widgets.JSONEditor]]:
        del self
        return pn.widgets.JSONEditor, {"menu": False, "schema": schema}

    @override
    def _string_type(self, schema: Mapping[str, object]) -> _WidgetType[type]:
        kwargs = _kwargs(schema)
        match schema:
            case {"format": "date-time"}:
                return pmui.DatetimePicker, kwargs
            case {"format": "date"}:
                return pmui.DatePicker, kwargs
            case {"format": "time"}:
                kwargs["clock"] = "24h"
                return pmui.TimePicker, kwargs
            case _:
                kwargs["size"] = "small"
                if max_length := schema.get("maxLength"):
                    kwargs["max_length"] = max_length
                return pmui.TextInput, kwargs

    @override
    def _widget_type(
        self,
        prop: str,
        schema: Mapping[str, Any],
    ) -> _WidgetType:
        match schema:
            case {"type": _} | {"enum": _}:
                wtype, kwargs = cast(
                    "_WidgetType",
                    super()._widget_type(prop, schema),  # pyright: ignore[reportUnknownMemberType]
                )
            case {"anyOf": [first, *rest]}:
                wtype, kwargs = self._widget_type(prop, first)
                for subschema in rest:
                    t, kw = self._widget_type(prop, subschema)
                    if t != wtype or kw != kwargs:
                        wtype, kwargs = self._object_type(schema)
                        break
                else:
                    if "helper_text" in wtype.param:
                        kwargs |= _kwargs(schema)
            case _:
                wtype, kwargs = self._object_type(schema)
        kwargs["sizing_mode"] = "stretch_width"
        return wtype, kwargs


def _helper_text(schema: Mapping[str, Any]) -> str | None:
    return (desc := schema.get("description")) and inspect.cleandoc(desc)


def _kwargs(schema: Mapping[str, object]) -> dict[str, object]:
    return {
        "helper_text": helper_text,
        "sx": {"white-space": "pre-wrap"},
    } if (helper_text := _helper_text(schema)) else {}
