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

__all__ = ["to_response", "to_response_model"]

import contextlib
import functools
import io
import pathlib
import sys
import tempfile

import fastapi
import holoviews as hv  # pyright: ignore[reportMissingTypeStubs]
import matplotlib as mpl
import matplotlib.figure as mfigure
import matplotlib.pyplot as plt
import panel as pn
import pydantic
from matplotlib import animation
from typing_extensions import Any, TypeForm

from gandharva import _utils
from gandharva._typing import Gandharva, HoloVizTypes

from . import _common


@functools.singledispatch
def to_response(value: object, app: Gandharva) -> object:
    del app
    return {"code": 0, "message": "OK", "data": value}


def to_response_model(
    model_name: str,
    data: TypeForm[Any],
    kwargs: dict[str, Any],
) -> None:
    try:
        kwargs["response_model"] = pydantic.create_model(
            model_name,
            code=int,
            message=str,
            data=data,
        )
    except pydantic.PydanticSchemaGenerationError:
        pass
    else:
        return
    kwargs["response_model"] = pydantic.create_model(
        model_name,
        code=int,
        message=str,
        data=Any,
    )
    ann = _utils.unwrap_annotation(data)
    _to_responses(ann, kwargs["responses"])


def _to_responses(
    tp: TypeForm[Any],
    responses: dict[int | str, dict[str, Any]],
) -> None:
    if _utils.isclass(tp):
        if issubclass(tp, animation.TimedAnimation):
            responses[200] = {"content": {"video/mp4": {}}}
        elif issubclass(tp, mfigure.Figure):
            match mpl.rcParams["savefig.format"]:
                case "png":
                    responses[200] = {"content": {"image/png": {}}}
                case "svg":
                    responses[200] = {"content": {"image/svg+xml": {}}}
                case _:
                    raise NotImplementedError
        elif issubclass(tp, HoloVizTypes):
            if sys.version_info >= (3, 12):
                responses[200] = {"content": {"text/html": {}}}
            else:
                match mpl.rcParams["savefig.format"]:
                    case "png":
                        responses[200] = {
                            "content": {"image/png": {}, "video/mp4": {}},
                        }
                    case "svg":
                        responses[200] = {
                            "content": {"image/svg+xml": {}, "video/mp4": {}},
                        }
                    case _:
                        raise NotImplementedError


@to_response.register
def _(value: fastapi.Response, app: Gandharva) -> fastapi.Response:
    del app
    return value


if sys.version_info >= (3, 12):
    @to_response.register
    def _(value: pn.viewable.Viewable, app: Gandharva) -> object:
        raise NotImplementedError

    @to_response.register
    def _(value: hv.core.Dimensioned, app: Gandharva) -> object:
        raise NotImplementedError
else:
    @to_response.register
    def _(value: pn.viewable.Viewable, app: Gandharva) -> object:
        return to_response(_common.get_plot(value), app)

    @to_response.register
    def _(value: hv.core.Dimensioned, app: Gandharva) -> object:
        return to_response(app.to_matplotlib(value), app)


@to_response.register
def _(value: animation.TimedAnimation, app: Gandharva) -> fastapi.Response:
    del app
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        p = pathlib.Path(tmp, "plot.mp4")
        value.save(p, writer="ffmpeg", codec="libopenh264")
        return fastapi.Response(p.read_bytes(), media_type="video/mp4")


@to_response.register
def _(value: mfigure.Figure, app: Gandharva) -> fastapi.Response:
    del app
    with contextlib.ExitStack() as stack:
        stack.callback(plt.close, value)
        match fmt := mpl.rcParams["savefig.format"]:
            case "png":
                media_type = "image/png"
            case "svg":
                media_type = "image/svg+xml"
            case _:
                raise NotImplementedError
        f = stack.enter_context(io.BytesIO())
        value.savefig(f, format=fmt)  # pyright: ignore[reportUnknownMemberType]
        return fastapi.Response(f.getvalue(), media_type=media_type)
