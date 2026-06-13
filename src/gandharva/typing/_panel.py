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

__all__ = [
    "BasicTemplateParameters",
    "ButtonParameters",
    "DataFrameParameters",
    "HTMLParameters",
    "JSONSchemaParameters",
    "MarkdownParameters",
]

from collections.abc import Callable, Hashable
from typing import TYPE_CHECKING, Generic, Literal

import panel as pn
from typing_extensions import Any, Never, TypedDict, TypeVar

if TYPE_CHECKING:
    from bokeh.models.ui.tooltips import Tooltip
    from markdown.extensions import Extension
    from markdown_it import MarkdownIt
    from panel.config import (
        _base_config,  # pyright: ignore[reportPrivateUsage]
    )
    from panel.io.notifications import NotificationAreaBase
    from panel.layout import ListLike
    from panel.theme import Design, Theme

_DataFrameAlign = Literal["start", "end", "center"] | None
_Formatter = Callable[[object], str]
_LayoutableAlign = Literal["auto", "start", "center", "end"]
_Policy = Literal["auto", "fixed", "fit", "min", "max"]
_T = TypeVar("_T", default=Never)
_Widget = str | pn.widgets.WidgetBase | Callable[..., pn.widgets.WidgetBase]


class _Layoutable(TypedDict, extra_items=Any, total=False):
    align: _LayoutableAlign | tuple[_LayoutableAlign, _LayoutableAlign]
    aspect_ratio: float | Literal["auto"] | None
    css_classes: Never
    design: Never
    height: int | None
    height_policy: _Policy
    margin: int | tuple[int, int] | tuple[int, int, int, int]
    max_height: int | None
    max_width: int | None
    min_height: int | None
    min_width: int | None
    name: Never
    sizing_mode: Literal[
        "fixed",
        "stretch_width",
        "stretch_height",
        "stretch_both",
        "scale_width",
        "scale_height",
        "scale_both",
    ] | None
    styles: dict[str, str | None]
    stylesheets: list[str]
    tags: list[str]
    visible: Never
    width: int | None
    width_policy: _Policy


class _PaneBase(_Layoutable, Generic[_T], total=False):
    default_layout: type[_T]
    object: Never


class _Viewable(_Layoutable, total=False):
    loading: Never


class _HTMLBasePane(_PaneBase, _Viewable, total=False):
    enable_streaming: Never


class _WidgetSpec(TypedDict, extra_items=Any, total=False):
    type: _Widget


class BasicTemplateParameters(TypedDict, extra_items=Any, total=False):
    base_target: Literal["_blank", "_self", "_parent", "_top"]
    base_url: str
    busy_indicator: pn.widgets.indicators.BooleanIndicator | None
    collapsed_sidebar: Never
    config: "_base_config"
    design: type["Design"]
    favicon: str | None
    header: "ListLike | None"
    header_background: str
    header_color: str
    location: bool
    logo: str
    main: "ListLike | None"
    main_max_width: str
    manifest: str | None
    meta_author: str
    meta_description: str
    meta_keywords: str
    meta_refresh: str
    meta_viewport: str
    modal: "ListLike | None"
    name: str | None
    notifications: "NotificationAreaBase | None"
    sidebar: Never
    sidebar_width: int
    site: str
    site_url: str
    theme: type["Theme"]
    title: str
    _actions: Never


class ButtonParameters(_Viewable, total=False):
    attached: Never
    button_style: Never
    button_type: Never
    clicks: Never
    color: Literal["default", "primary", "success", "info", "light", "danger"]
    dark_theme: Never
    description: "str | Tooltip | pn.widgets.TooltipIcon | None"
    description_delay: int
    disabled: Never
    disable_elevation: bool
    end_icon: str | None
    href: Never
    icon: str | None
    icon_size: str
    size: Literal["small", "medium", "large"]
    sx: dict[str, str]
    target: Never
    theme_config: Never
    use_shadow_dom: Never
    value: Never
    variant: Literal["contained", "outlined", "text"]


class DataFrameParameters(_HTMLBasePane, total=False):
    bold_rows: bool
    border: int
    classes: list[str]
    col_space: str | int | dict[Hashable, str | int] | None
    decimal: str
    disable_math: bool
    escape: bool
    float_format: Callable[[float], str] | None
    formatters: dict[str | int, _Formatter] | list[_Formatter] | None
    header: Never
    index: bool
    index_names: Never
    justify: _DataFrameAlign | Literal[
        "left",
        "right",
        "justify",
        "justify-all",
        "inherit",
        "match-parent",
        "initial",
        "unset",
    ]
    max_cols: int | None
    max_rows: int | None
    na_rep: str
    render_links: bool
    sanitize_hook: Callable[[str], str]
    sanitize_html: bool
    show_dimensions: bool
    sparsify: bool
    text_align: _DataFrameAlign
    _object: Never


class HTMLParameters(_HTMLBasePane, total=False):
    disable_math: bool
    sanitize_hook: Never
    sanitize_html: Never


class JSONSchemaParameters(_PaneBase[pn.layout.ListPanel], total=False):
    multi: Never
    properties: Never
    schema: Never
    widgets: dict[str, _Widget | _WidgetSpec] | None


class MarkdownParameters(_HTMLBasePane, total=False):
    dedent: Never
    disable_anchors: bool
    disable_math: bool
    extensions: list["Extension | str"]
    hard_line_break: bool
    plugins: list["Callable[[MarkdownIt], None]"]
    renderer: Literal["markdown-it", "myst", "markdown"]
    renderer_options: dict[str, Any]
