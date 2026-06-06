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
import functools
import math
from collections.abc import Callable, Iterable, Mapping
from typing import TYPE_CHECKING, cast

import lumen.schema  # pyright: ignore[reportMissingTypeStubs]
import panel as pn
import param
import pydantic
from hypothesis_jsonschema import _resolve  # noqa: PLC2701
from typing_extensions import Any, final, override

import gandharva as gd
from gandharva import _convert

from . import _base, _pydantic

if TYPE_CHECKING:
    from panel.io.application import TViewable
    from panel.layout import ListLike
    from panel.viewable import Viewable
    from panel.widgets import WidgetBase

_NINF = -math.inf


class App(_pydantic.App):
    panel_event_loop: asyncio.AbstractEventLoop

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
    def panel_template_class(cls) -> type[pn.template.base.BasicTemplate]:
        return _MaterialTemplate

    @classmethod
    def panel_template_params(cls) -> gd.typing.BasicTemplateParameters:
        title = _base.normalize(cls.__name__).replace("-", " ")
        return {"title": title[:1].upper() + title[1:]}

    @classmethod
    def __panel__(cls) -> "TViewable":  # noqa: PLW3201
        async def main(clicked: bool) -> "Viewable":  # noqa: FBT001
            loop = asyncio.get_running_loop()
            func = functools.partial(
                cls._panel_main, loop, model, widgets, clicked=clicked)
            result, stack = await asyncio.to_thread(
                cls._panel_update, func, submit, indicator)
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
        kwargs = dict(cls.panel_button_params(), on_click=None)
        submit = pn.widgets.Button(**kwargs)
        sidebar.append(
            pn.Row(
                pn.Spacer(sizing_mode="stretch_width"),
                submit,
                pn.Spacer(sizing_mode="stretch_width"),
            ),
        )
        template = cls._panel_template(sidebar)
        indicator = template.busy_indicator
        cast("ListLike", template.main).append(pn.bind(main, submit))
        return template

    @classmethod
    @final
    def to_panels(cls, prefix: str = "") -> dict[
        str,
        Callable[[], "TViewable"],  # See https://github.com/holoviz/panel/issues/2476
    ]:
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

        panels = {prefix or "/": cls.__panel__}
        prefix += "/"
        for child in cls.children:
            panels |= child.to_panels(prefix + child.app_normalized_name())
        return panels

    @classmethod
    def _panel_main(
        cls,
        loop: asyncio.AbstractEventLoop,
        model: type[pydantic.BaseModel],
        widgets: Iterable["tuple[str, WidgetBase]"],
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
            self = cls.from_pydantic(data, run_mode="gui")
            self.panel_event_loop = loop
            result = self.main()
        return _convert.to_panel(result, cls)

    @classmethod
    def _panel_update(
        cls,
        callback: Callable[[], "Viewable"],
        submit: pn.widgets.Button,
        indicator: pn.widgets.indicators.BooleanIndicator | None = None,
    ) -> tuple["Viewable", contextlib.ExitStack]:
        with contextlib.ExitStack() as stack:
            stack.enter_context(submit.param.update(disabled=True))
            if indicator:
                stack.enter_context(
                    indicator.param.update(value=True, visible=True),
                )
            try:
                result = callback()
            except Exception as e:  # noqa: BLE001
                result = _convert.gui_error_handler(e)
            return result, stack.pop_all()

    @classmethod
    def _panel_template(
        cls,
        sidebar: "ListLike",
    ) -> pn.template.base.BasicTemplate:
        template = cls.panel_template_class()
        if issubclass(
            template,
            (
                pn.template.EditableTemplate,
                pn.template.FastGridTemplate,
                pn.template.FastListTemplate,
                pn.template.GoldenTemplate,
                pn.template.ReactTemplate,
                pn.template.SlidesTemplate,
            ),
        ):
            message = f"Unsupported template: {template}"
            raise gd.ApplicationBuilderError(message)
        return template(**dict(cls.panel_template_params(), sidebar=sidebar))


class _MaterialTemplate(pn.template.MaterialTemplate):
    busy_indicator = param.ClassSelector(
        default=pn.widgets.LoadingSpinner(visible=False, width=20, height=20),
        class_=pn.widgets.indicators.BooleanIndicator,
        constant=True,
        allow_None=True,
        doc="Visual indicator of application busy state.",
    )


class _Sidebar(lumen.schema.JSONSchema):
    @classmethod
    def build(
        cls,
        kwargs: gd.typing.JSONSchemaParameters,
        schema: dict[str, pydantic.JsonValue],
    ) -> tuple["ListLike", "Iterable[tuple[str, WidgetBase]]"]:
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
        sidebar = cast("ListLike", self.layout)
        widgets = cast("dict[str, WidgetBase]", self._widgets).items()
        return sidebar, widgets

    @override
    def _array_type(
        self,
        schema: Mapping[str, Any],
    ) -> tuple["type[WidgetBase]", dict[str, object]]:
        match schema:
            case {"items": {"enum": [*options]}}:
                return pn.widgets.MultiSelect, {"options": options}
            case _:
                return pn.widgets.JSONEditor, {"menu": False, "schema": schema}

    @override
    def _integer_type(
        self,
        schema: Mapping[str, int],
    ) -> tuple[type, dict[str, int]]:
        kwargs = {"step": 1}
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
                if start < end:
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
        return pn.widgets.IntInput, kwargs

    @override
    def _number_type(
        self,
        schema: Mapping[str, float],
    ) -> tuple[type, dict[str, float]]:
        kwargs = {"step": .1}
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
                if start < end:
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
        return pn.widgets.FloatInput, kwargs

    def _object_type(
        self,
        schema: Mapping[str, object],
    ) -> tuple[type[pn.widgets.JSONEditor], dict[str, object]]:
        del self
        return pn.widgets.JSONEditor, {"menu": False, "schema": schema}

    @override
    def _string_type(
        self,
        schema: Mapping[str, object],
    ) -> tuple[type, dict[str, object]]:
        match schema:
            case {"format": "date-time"}:
                return pn.widgets.DatetimePicker, {"allow_input": True}
            case {"format": "date"}:
                return pn.widgets.DatePicker, {}
            case {"format": "time"}:
                return pn.widgets.TimePicker, {"clock": "24h"}
            case {"maxLength": max_length}:
                return pn.widgets.TextInput, {"max_length": max_length}
            case _:
                return pn.widgets.TextInput, {}

    @override
    def _widget_type(
        self,
        prop: str,
        schema: Mapping[str, object],
    ) -> tuple[type, dict[str, object]]:
        wtype, kwargs = super()._widget_type(prop, schema)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        return wtype, dict(kwargs, sizing_mode="stretch_width")  # pyright: ignore[reportUnknownArgumentType]
