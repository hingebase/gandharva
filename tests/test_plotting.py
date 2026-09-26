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

"""Test postprocessing of HoloViz and Matplotlib objects."""

import contextlib
import functools
import io
import math
import mimetypes
import os
import subprocess  # ruff: ignore[suspicious-subprocess-import]
import sys
import types
import warnings
from collections.abc import Callable, Generator, Iterator
from typing import IO, TYPE_CHECKING, Annotated, Generic, cast

import annotated_types as at
import holoviews as hv  # pyright: ignore[reportMissingTypeStubs]
import httpx2
import hvplot  # pyright: ignore[reportMissingTypeStubs]
import hvsampledata
import lxml.etree
import matplotlib.animation
import matplotlib.axes as maxes
import matplotlib.dates as mdates
import matplotlib.figure as mfigure
import matplotlib.legend as mlegend
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import panel as pn
import PIL.Image
import pydantic_settings
import pytest
from bokeh.models import ColorBar
from bokeh.plotting import figure
from fastapi.testclient import TestClient
from holoviews.plotting import bokeh, mpl  # pyright: ignore[reportMissingTypeStubs]
from matplotlib.backend_bases import FigureCanvasBase
from matplotlib.colorbar import Colorbar
from typing_extensions import Any, ParamSpec, override

import gandharva as gd
from gandharva import testing

if TYPE_CHECKING:
    import numpy.typing as npt

_P = ParamSpec("_P")


@pytest.fixture(scope="module", autouse=True)
def _rc_context() -> Iterator[None]:
    with matplotlib.rc_context(matplotlib.rcParamsDefault):  # pyright: ignore[reportUnknownMemberType]
        matplotlib.rcParams["figure.max_open_warning"] = 1
        yield


@pytest.fixture(params=["png", "svg"])
def savefig_format(request: pytest.FixtureRequest) -> Iterator[str]:
    """Matplotlib `savefig.format` should be honored in API mode.

    Yields:
        The corresponding `Content-Type`.

    """
    content_type = mimetypes.guess_type(f"foo.{request.param}")[0]
    assert content_type
    with matplotlib.rc_context({"savefig.format": request.param}):  # pyright: ignore[reportUnknownMemberType]
        yield content_type


# This is not a fixture since we want to track errors inside test cases
class _CheckFresh(
    contextlib.ContextDecorator,
    contextlib.AbstractContextManager[None, None],
):
    @override
    def __enter__(self) -> None:
        assert hv.Store.current_backend == "bokeh"
        assert not plt.get_fignums()

    @override
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: types.TracebackType | None,
        /,
    ) -> None:
        self.__enter__()


_check_fresh = _CheckFresh()


@pytest.mark.skipif(
    sys.version_info < (3, 12),
    reason="This feature requires Python 3.12 or later",
)
@_check_fresh
def test_embeddable_html_api(subtests: pytest.Subtests) -> None:
    """HoloViz objects should be converted to HTML in API mode."""
    app = _Main()
    paths = app.openapi()["paths"]
    for endpoint, method in [
        ("/dynamic-map/", "get"),
        ("/holo-map/", "get"),
        ("/holo-views/", "post"),
        ("/matplotlib/", "get"),
        ("/nd-overlay/", "get"),
    ]:
        responses = paths[endpoint][method]["responses"]
        assert responses["200"]["content"] == {"text/html": {}}

    with TestClient(app) as client:
        with subtests.test("Non-plotting"):
            response = client.get("/")
            response.raise_for_status()
            assert response.json() == {
                "code": 0,
                "message": "OK",
                "data": "Hello world!",
            }

        with subtests.test("DynamicMap + Forwarded"):
            # ruff: disable[line-too-long]
            response = client.get(
                "/dynamic-map/",
                headers=[
                    ("Host", "127.0.0.1"),
                    # Examples taken from RFC 7239
                    ("Forwarded", "for=192.0.2.43,for=198.51.100.17;by=203.0.113.60;proto=https;host=example.com"),
                    ("Forwarded", "for=192.0.2.60;proto=http;by=203.0.113.43;host=unused.com"),
                ],
            )
            # ruff: enable[line-too-long]
            _check_html_integrity(response)
            body = response.content
            # We inserted <base> in the front of <head>
            assert b'<head><base href="https://example.com/"/>' in body
            _ensure_no_cdn(body)

        with subtests.test("HoloMap + X-Forwarded-*"):
            response = client.get(
                "/holo-map/",
                headers={
                    "Host": "127.0.0.1",
                    "X-Forwarded-Host": "example.com",
                    "X-Forwarded-Proto": "http",
                },
            )
            _check_html_integrity(response)
            body = response.content
            assert b'<head><base href="http://example.com/"/>' in body
            _ensure_no_cdn(body)

        with subtests.test("HoloViews + Host"):
            response = client.post(
                "/holo-views/",
                json={"year": 2019, "quarter": 4},
                headers={"Host": "127.0.0.1"},
            )
            _check_html_integrity(response)
            body = response.content
            assert b'<head><base href="http://127.0.0.1/"/>' in body
            _ensure_no_cdn(body)

        with subtests.test("Matplotlib + default Host"):
            response = client.get("/matplotlib/")
            _check_html_integrity(response)
            body = response.content
            assert b'<head><base href="http://testserver/"/>' in body
            _ensure_no_cdn(body)

        with subtests.test("NdOverlay + bad headers"):
            response = client.get(
                "/nd-overlay/",
                headers={"Forwarded": "host=example.com"},
            )
            _check_html_integrity(response)
            body = response.content
            assert b"<head><base" not in body
            assert b"cdn.bokeh.org" in body
            assert b"cdn.holoviz.org" in body


@pytest.mark.skipif(
    sys.version_info >= (3, 12),
    reason="This only applies to Python 3.10 and 3.11",
)
@_check_fresh
def test_dynamic_map_fallback_api() -> None:
    """DynamicMaps are forbidden in API mode."""
    with TestClient(_DynamicMap()) as client, pytest.raises(TypeError):
        client.get("/")


@_check_fresh
def test_dynamic_map_cli() -> None:
    """DynamicMaps are forbidden in CLI mode."""
    with pytest.raises(TypeError):
        pydantic_settings.CliApp.run(_DynamicMap.to_cli(), cli_args=[])


@pytest.mark.xfail(raises=NotImplementedError)
@_check_fresh
def test_dynamic_map_gui() -> None:
    """DynamicMaps are allowed in GUI mode."""
    raise NotImplementedError


@_check_fresh
def test_image_api(savefig_format: str) -> None:
    """Figures should be converted to images in API mode."""
    app = _Figure()
    responses = app.openapi()["paths"]["/"]["get"]["responses"]
    assert responses["200"]["content"] == {savefig_format: {}}
    with TestClient(app) as client:
        response = client.get("/")
    _check_image_integrity_api(response, savefig_format)


@pytest.mark.skipif(
    sys.version_info >= (3, 12),
    reason="This only applies to Python 3.10 and 3.11",
)
@_check_fresh
def test_image_fallback_api(savefig_format: str) -> None:
    """Non-HoloMap objects should be converted to images in API mode."""
    app = _Main()
    content_types: dict[str, object] = {savefig_format: {}, "video/mp4": {}}
    paths = app.openapi()["paths"]
    responses = paths["/matplotlib/"]["get"]["responses"]
    assert responses["200"]["content"] == content_types
    responses = paths["/nd-overlay/"]["get"]["responses"]
    assert responses["200"]["content"] == content_types
    responses = paths["/holo-views/"]["post"]["responses"]
    assert responses["200"]["content"] == content_types
    with TestClient(app) as client:
        response = client.get("/matplotlib/")
        _check_image_integrity_api(response, savefig_format)
        response = client.get("/nd-overlay/")
        _check_image_integrity_api(response, savefig_format)
        response = client.post("/holo-views/", json={"quarter": 4})
        _check_image_integrity_api(response, savefig_format)


@_check_fresh
def test_image_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-HoloMap objects should be converted to images in CLI mode."""
    @contextlib.contextmanager
    def patch() -> Generator[io.BytesIO]:
        yield f  # ruff: ignore[fallible-context-manager]
        raise _ExpectedError

    monkeypatch.setattr(testing, "BytesIO", patch)
    cli = _Main.to_cli()

    with io.BytesIO() as f:
        with pytest.raises(_ExpectedError):
            pydantic_settings.CliApp.run(_Figure.to_cli(), cli_args=[])
        _check_image_integrity(f)

    for cli_args in ["matplotlib"], ["nd-overlay"]:
        with io.BytesIO() as f:
            with pytest.raises(_ExpectedError):
                pydantic_settings.CliApp.run(cli, cli_args)
            _check_image_integrity(f)

    with io.BytesIO() as f:
        cli_args = ["holo-views", "--year", "2019", "--quarter", "4"]
        with pytest.raises(_ExpectedError):
            pydantic_settings.CliApp.run(cli, cli_args)
        _check_image_integrity(f)


@pytest.mark.xfail(raises=NotImplementedError)
@_check_fresh
def test_image_gui() -> None:
    """Figures should be converted to images in GUI mode."""
    raise NotImplementedError


@_check_fresh
def test_switching_plotting_backend_cli() -> None:
    """Plotting backend should be switched to Matplotlib in CLI mode.

    This rule applies even if the application neither declares a
    plot-like return type nor plots anything at runtime.
    """
    pydantic_settings.CliApp.run(_Main.to_cli(), cli_args=[])


@pytest.mark.skipif(
    os.getenv("PIXI_PROJECT_NAME") != "gandharva",
    reason="This test is not portable",
)
@_check_fresh
def test_video_api() -> None:
    """Animations should be converted to videos in API mode."""
    app = _Animation()
    responses = app.openapi()["paths"]["/"]["get"]["responses"]
    assert responses["200"]["content"] == {"video/mp4": {}}
    with TestClient(app) as client:
        response = client.get("/")
    _check_video_integrity(response)


@pytest.mark.skipif(
    sys.version_info >= (3, 12),
    reason="This only applies to Python 3.10 and 3.11",
)
@pytest.mark.skipif(
    os.getenv("PIXI_PROJECT_NAME") != "gandharva",
    reason="This test is not portable",
)
@_check_fresh
def test_video_fallback_api(savefig_format: str) -> None:
    """HoloMaps should be converted to videos in API mode."""
    app = _HoloMap()
    content_types: dict[str, object] = {savefig_format: {}, "video/mp4": {}}
    responses = app.openapi()["paths"]["/"]["get"]["responses"]
    assert responses["200"]["content"] == content_types
    with TestClient(app) as client:
        response = client.get("/")
    _check_video_integrity(response)


@pytest.mark.skipif(
    "CI" in os.environ or os.getenv("PIXI_PROJECT_NAME") != "gandharva",
    reason="This test is not portable",
)
@_check_fresh
def test_video_cli() -> None:
    """Animations/HoloMaps should be converted to videos in CLI mode."""
    pydantic_settings.CliApp.run(_Animation.to_cli(), cli_args=[])
    pydantic_settings.CliApp.run(_Main.to_cli(), cli_args=["holo-map"])


@pytest.mark.xfail(raises=NotImplementedError)
@_check_fresh
def test_video_gui() -> None:
    """Animations should be converted to videos in GUI mode."""
    raise NotImplementedError


class _EnsureCalled(Generic[_P]):
    def __init__(self, wrapped: Callable[_P, None]) -> None:
        self._fail = True
        self.__wrapped__ = wrapped

    def __call__(self, *args: _P.args, **kwargs: _P.kwargs) -> None:
        self._fail = False
        self.__wrapped__(*args, **kwargs)

    def __del__(self) -> None:
        # Exceptions in __del__ are unraisable
        if self._fail:
            warnings.warn(
                f"Hook {self.__wrapped__} never got called",
                stacklevel=1,
            )


class _EnsureNotCalled(Generic[_P]):
    def __init__(self, wrapped: Callable[_P, None]) -> None:
        self._fail = False
        self.__wrapped__ = wrapped

    def __call__(self, *args: _P.args, **kwargs: _P.kwargs) -> None:
        self._fail = True
        self.__wrapped__(*args, **kwargs)

    def __del__(self) -> None:
        if self._fail:
            warnings.warn(f"Hook {self.__wrapped__} was called", stacklevel=1)


class _ExpectedError(Exception):
    pass


class _Main(gd.Gandharva):
    @override
    def main(self) -> str:
        if self.run_mode == "cli":
            assert hv.Store.current_backend == "matplotlib"
        else:
            assert hv.Store.current_backend == "bokeh"
        return "Hello world!"


class _Figure(gd.Gandharva):
    @override
    def main(self) -> mfigure.Figure:
        assert hv.Store.current_backend == "matplotlib"
        overlay = _plot_stocks()
        with matplotlib.rc_context({"figure.dpi": 200}):  # pyright: ignore[reportUnknownMemberType]
            fig = self.to_matplotlib(overlay)
        assert isinstance(fig, mfigure.Figure)
        assert not plt.get_fignums()
        return fig


class _Animation(gd.Gandharva):
    @override
    def main(self) -> matplotlib.animation.FuncAnimation:
        assert hv.Store.current_backend == "matplotlib"
        ds, clim = _air_temperature()
        holomap = ds.hvplot.image(clim=clim, cmap="cwr", dynamic=False)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        assert isinstance(holomap, hv.HoloMap)
        if self.run_mode == "gui":
            holomap.opts(hooks=[_EnsureNotCalled(_hook_image)])
        else:
            holomap.opts(hooks=[_EnsureCalled(_hook_image)])
        anim = self.to_matplotlib(holomap)
        assert isinstance(anim, matplotlib.animation.FuncAnimation)
        assert not plt.get_fignums()
        return anim


@_Main.register
class _DynamicMap(gd.Gandharva):
    @override
    def main(self) -> hv.DynamicMap:
        _check_current_backend(self)
        ds, clim = _air_temperature()
        dynamicmap = ds.hvplot.image(clim=clim, cmap="cwr")  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        assert isinstance(dynamicmap, hv.DynamicMap)
        if self.run_mode == "api" and sys.version_info >= (3, 12):
            dynamicmap.opts(hooks=[_EnsureCalled(_hook_image)])
        else:
            dynamicmap.opts(hooks=[_EnsureNotCalled(_hook_image)])
        return dynamicmap


@_Main.register
class _HoloMap(gd.Gandharva):
    @override
    def main(self) -> hv.HoloMap:
        _check_current_backend(self)
        ds, clim = _air_temperature()
        holomap = ds.hvplot.image(clim=clim, cmap="cwr", dynamic=False)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        assert isinstance(holomap, hv.HoloMap)
        holomap.opts(hooks=[_EnsureCalled(_hook_image)])
        return holomap


@_Main.register
class _HoloViews(gd.Gandharva):
    year: Annotated[int, at.Ge(2019), at.Le(2024)] = 2019
    quarter: Annotated[int, at.Ge(1), at.Le(4)] = 1

    @override
    def main(self) -> pn.pane.HoloViews:
        _check_current_backend(self)
        y = self.year
        q = self.quarter
        plot = hvplot.hvPlotTabular(
            hvsampledata.apple_stocks("pandas")  # pyright: ignore[reportUnknownMemberType]
                .set_index("date")
                .loc[f"{y}-{q * 3 - 2:02}" : f"{y}-{q * 3:02}"]
                .eval("yerr1 = close - low\nyerr2 = high - close"),
        )
        line = plot.line(xlabel="Date", y="close", ylabel="Price")  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        assert isinstance(line, hv.Curve)
        line.opts(hooks=[_EnsureCalled(_hook_curve)], show_grid=True)
        errorbars = plot.errorbars(y="close", yerr1="yerr1", yerr2="yerr2")  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        assert isinstance(errorbars, hv.ErrorBars)
        errorbars.opts(hooks=[_EnsureCalled(_hook_errorbars)])
        overlay = line * errorbars  # pyright: ignore[reportUnknownVariableType]
        assert isinstance(overlay, hv.Overlay)
        overlay.opts(hooks=[_EnsureCalled(_hook_overlay)])
        pane = pn.panel(overlay)  # pyright: ignore[reportUnknownMemberType]
        assert isinstance(pane, pn.pane.HoloViews)
        return pane


@_Main.register
class _Matplotlib(gd.Gandharva):
    @override
    def main(self) -> pn.pane.Matplotlib:
        assert hv.Store.current_backend == "matplotlib"
        overlay = _plot_stocks()
        with matplotlib.rc_context({"figure.dpi": 200}):  # pyright: ignore[reportUnknownMemberType]
            fig = self.to_matplotlib(overlay)
        assert isinstance(fig, mfigure.Figure)
        assert not plt.get_fignums()
        return pn.pane.Matplotlib(fig, format="svg", width=800)


@_Main.register
class _NdOverlay(gd.Gandharva):
    @override
    def main(self) -> hv.NdOverlay:
        _check_current_backend(self)
        return _plot_stocks()

    @classmethod
    @override
    def panel_matplotlib_params(
        cls,
        fig: mfigure.Figure,
    ) -> gd.typing.MatplotlibParameters:
        params = super().panel_matplotlib_params(fig)
        params["width"] = 800
        return params


# This is not a fixture since it's called inside the applications
@functools.lru_cache(maxsize=1)
def _air_temperature() -> tuple[gd.Dataset[Any], tuple[float, float]]:
    ds = hvsampledata.air_temperature("xarray")
    air = np.asarray(ds.data_vars["air"], np.float64)
    return cast("gd.Dataset[Any]", ds), (air.min(), air.max())


def _check_current_backend(app: gd.Gandharva) -> None:
    match app.run_mode:
        case "api" if sys.version_info < (3, 12):
            assert hv.Store.current_backend == "matplotlib"
        case "cli":
            assert hv.Store.current_backend == "matplotlib"
        case _:
            assert hv.Store.current_backend == "bokeh"


def _check_html_integrity(response: httpx2.Response) -> None:
    response.raise_for_status()
    # Skip optional `charset=`
    assert response.headers["Content-Type"].startswith("text/html")
    # response.read() doesn't take any arguments
    with io.BytesIO(response.content) as f:
        lxml.etree.parse(f, lxml.etree.HTMLParser(encoding=response.encoding))


def _check_image_integrity(f: IO[bytes]) -> None:
    with PIL.Image.open(f) as im:
        im.load()


def _check_image_integrity_api(
    response: httpx2.Response,
    content_type: str,
) -> None:
    response.raise_for_status()
    assert response.headers["Content-Type"] == content_type
    match content_type:
        case "image/png":
            _check_image_integrity(cast("IO[bytes]", response))
        case "image/svg+xml":
            with io.BytesIO(response.content) as f:
                # Matplotlib declared it as SVG 1.1, but it can't pass
                # the lxml `dtd_validation`
                lxml.etree.parse(f)
        case _:
            pytest.fail("Unreachable")


def _check_video_integrity(response: httpx2.Response) -> None:
    response.raise_for_status()
    assert response.headers["Content-Type"] == "video/mp4"
    subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true]
        [  # ruff: ignore[start-process-with-partial-path]
            "ffmpeg",
            "-xerror",
            "-i", "-",
            "-c", "copy",
            "-f", "null",
            os.devnull,
        ],
        check=True,
        input=response.content,
    )


def _ensure_no_cdn(body: bytes) -> None:
    assert b"cdn.bokeh.org" not in body
    assert b"cdn.holoviz.org" not in body


@functools.singledispatch
def _hook_curve(_plot: object, _element: hv.Curve) -> None:
    pytest.fail("Unreachable")


@_hook_curve.register
def _(_plot: bokeh.CurvePlot, _element: hv.Curve) -> None: ...
@_hook_curve.register
def _(_plot: mpl.CurvePlot, _element: hv.Curve) -> None: ...


@functools.singledispatch
def _hook_errorbars(_plot: object, _element: hv.ErrorBars) -> None:
    pytest.fail("Unreachable")


@_hook_errorbars.register
def _(_plot: bokeh.ErrorPlot, _element: hv.ErrorBars) -> None: ...
@_hook_errorbars.register
def _(_plot: mpl.ErrorPlot, _element: hv.ErrorBars) -> None: ...


@functools.singledispatch
def _hook_image(plot: object, _: hv.Image) -> None:
    del plot
    pytest.fail("Unreachable")


@_hook_image.register
def _(plot: bokeh.RasterPlot, _: hv.Image) -> None:
    fig = plot.handles["plot"]  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    assert isinstance(fig, figure)
    fig.toolbar.autohide = True
    cbar = plot.handles["colorbar"]  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    assert isinstance(cbar, ColorBar)
    cbar.height = 270
    cbar.location = (-15, -60)
    # https://discourse.holoviz.org/t/colorbar-label-position/2205
    cbar.padding = 35
    cbar.title_standoff = -160


@_hook_image.register
def _(plot: mpl.RasterPlot, _: hv.Image) -> None:
    fig = plot.handles["fig"]  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    assert isinstance(fig, mfigure.Figure)
    fig.dpi = 200
    if type(fig.canvas) is FigureCanvasBase:
        return
    k = fig.get_figheight()
    mpl.util.fix_aspect(fig, 1, 1)  # pyright: ignore[reportUnknownMemberType]
    k /= fig.get_figheight()
    cbar = plot.handles["cbar"]  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    assert isinstance(cbar, Colorbar)
    bbox = cbar.ax.get_position()  # Returns a copy
    y = cast("npt.NDArray[np.float64]", bbox.intervaly)
    y -= .5
    y *= k
    y += .5
    cbar.ax.set_position(bbox)


@functools.singledispatch
def _hook_overlay(plot: object, _: hv.Overlay) -> None:
    del plot
    pytest.fail("Unreachable")


@_hook_overlay.register
def _(plot: bokeh.OverlayPlot, _: hv.Overlay) -> None:
    fig = plot.handles["plot"]  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    assert isinstance(fig, figure)
    fig.toolbar.autohide = True


@_hook_overlay.register
def _(plot: mpl.OverlayPlot, _: hv.Overlay) -> None:
    fig = plot.handles["fig"]  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    assert isinstance(fig, mfigure.Figure)
    mpl.util.fix_aspect(fig, 1, 1)  # pyright: ignore[reportUnknownMemberType]
    ax = plot.handles["axis"]  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    assert isinstance(ax, maxes.Axes)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))


@functools.singledispatch
def _hook_ndoverlay(plot: object, _: hv.NdOverlay) -> None:
    del plot
    pytest.fail("Unreachable")


@_hook_ndoverlay.register
def _(plot: bokeh.OverlayPlot, _: hv.NdOverlay) -> None:
    fig = plot.handles["plot"]  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    assert isinstance(fig, figure)
    fig.legend[0].title = None
    fig.toolbar.autohide = True


@_hook_ndoverlay.register
def _(plot: mpl.OverlayPlot, _: hv.NdOverlay) -> None:
    fig = plot.handles["fig"]  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    assert isinstance(fig, mfigure.Figure)
    mpl.util.fix_aspect(fig, 1, 1)  # pyright: ignore[reportUnknownMemberType]
    legend = plot.handles["legend"]  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    assert isinstance(legend, mlegend.Legend)
    legend.set_title("")
    ax = plot.handles["axis"]  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    assert isinstance(ax, maxes.Axes)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
    ax.grid(visible=True)  # pyright: ignore[reportUnknownMemberType]


def _plot_stocks() -> hv.NdOverlay:
    df = hvsampledata.stocks("pandas")  # pyright: ignore[reportUnknownMemberType]
    x, *y = df.columns
    t = df.loc[:, x]
    pad = pd.Timedelta(days=1)
    data = df.loc[:, y]

    ymin = data.min(axis=None)
    assert isinstance(ymin, float)
    ymin = math.floor(ymin) - .01

    ymax = data.max(axis=None)
    assert isinstance(ymax, float)
    ymax = math.ceil(ymax) + .01

    overlay = hvplot.hvPlotTabular(df).line(  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        x=x,
        xlabel="Date",
        xlim=(t.min() - pad, t.max() + pad),
        y=y,
        ylabel="Normalized price",
        ylim=(ymin, ymax),
    )
    assert isinstance(overlay, hv.NdOverlay)
    overlay.opts(
        hooks=[_EnsureCalled(_hook_ndoverlay)],
        legend_position="top_left",
        show_grid=True,
    )
    return overlay
