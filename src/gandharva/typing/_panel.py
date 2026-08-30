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
    "ButtonParameters",
    "DataFrameParameters",
    "HTMLParameters",
    "JSONSchemaParameters",
    "MarkdownParameters",
    "PageParameters",
]

import pathlib
from collections.abc import Callable, Hashable
from typing import TYPE_CHECKING, Generic, Literal

import jinja2
import panel as pn
from typing_extensions import Any, Never, TypedDict, TypeVar

if TYPE_CHECKING:
    from bokeh.models.ui.tooltips import Tooltip
    from markdown.extensions import Extension
    from markdown_it import MarkdownIt
    from panel.config import (
        _base_config,  # pyright: ignore[reportPrivateUsage]
    )
    from panel_material_ui.template.base import Meta

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


class _PaneBase(_Layoutable, total=False):
    default_layout: Never
    object: Never


class _Viewable(_Layoutable, total=False):
    loading: Never


class _HTMLBasePane(_PaneBase, _Viewable, total=False):
    enable_streaming: Never


class _MaterialComponent(_Viewable, Generic[_T], total=False):
    dark_theme: _T
    sx: dict[str, str]
    theme_config: dict[str, Any]
    use_shadow_dom: bool


class _Logo(TypedDict, closed=True):
    dark: str | pathlib.Path
    light: str | pathlib.Path


class _WidgetSpec(TypedDict, extra_items=Any, total=False):
    type: _Widget


class PageParameters(_MaterialComponent[bool], total=False):
    app_bar_width: int | str | dict[str, int | str] | None
    busy: Never
    busy_indicator: Literal["circular", "linear"] | None
    config: "_base_config"
    contextbar: Never
    contextbar_open: bool
    contextbar_resizable: bool
    contextbar_variant: Literal["persistent", "temporary", "permanent", "auto"]
    contextbar_width: int
    favicon: str | pathlib.Path
    header: list[pn.viewable.Viewable]
    logo: str | pathlib.Path | _Logo
    main: Never
    main_width: int | str | dict[str, int | str] | None
    meta: "Meta | None"
    meta_apple_touch_icon: str | None
    meta_author: str | None
    meta_description: str | None
    meta_icon: str | None
    meta_keywords: str | None
    meta_name: str
    meta_refresh: str | None
    meta_title: str | None
    meta_viewport: str
    sidebar: Never
    sidebar_open: bool
    sidebar_resizable: bool
    sidebar_variant: Literal["persistent", "temporary", "permanent", "auto"]
    sidebar_width: int
    site_url: str
    template: str | pathlib.Path | jinja2.Template
    theme: Literal["dark"]
    theme_toggle: bool
    title: str
    _custom_theme: Never


class ButtonParameters(_MaterialComponent, total=False):
    attached: Never
    button_style: Never
    button_type: Never
    clicks: Never
    color: Literal["default", "primary", "success", "info", "light", "danger"]
    description: "str | Tooltip | pn.widgets.TooltipIcon | None"
    description_delay: int
    disabled: Never
    disable_elevation: bool
    end_icon: str | None
    href: Never
    icon: str | None
    icon_size: str
    label: str
    size: Literal["small", "medium", "large"]
    target: Never
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


class JSONSchemaParameters(_PaneBase, total=False):
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


class MatplotlibParameters(_HTMLBasePane, total=False):
    alt_text: str | None
    caption: str | None
    dpi: int
    embed: Never
    encode: bool
    fixed_aspect: bool
    format: Literal["png", "svg"]
    high_dpi: bool
    interactive: Never
    link_url: str | None
    target: str
    tight: bool
