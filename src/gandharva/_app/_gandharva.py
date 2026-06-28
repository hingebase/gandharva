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

__all__ = ["Gandharva"]

import asyncio
import functools
import importlib.metadata
import inspect
from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING, cast

import anyio.from_thread
import pandera.xarray as pa
import xarray as xr
from typing_extensions import Any, ParamSpec, TypeVar, disjoint_base
from upath import UPath

import gandharva as gd
from gandharva import _convert

from . import _base, _fastapi, _panel

if TYPE_CHECKING:
    from _typeshed import StrPath
    from metpy import (  # pyright: ignore[reportMissingTypeStubs]
        MetPyDatasetAccessor,
    )

_GandharvaT = TypeVar("_GandharvaT", bound=type["Gandharva"])
_P = ParamSpec("_P")
_T = TypeVar("_T")


@disjoint_base
class Gandharva(_fastapi.App, _panel.App):
    @classmethod
    def register(cls, child: _GandharvaT) -> _GandharvaT:
        if inspect.isabstract(cls) or inspect.isabstract(child):
            message = (
                "Can't register sub-application if either the parent or the "
                "child is an abstract class. Please implement the main() "
                "method."
            )
            raise gd.ApplicationRegisterError(message) from None
        if cls is child or cls._registered(child):
            message = (
                "Can't register sub-application if a cycle would be formed "
                "in the application structure graph"
            )
            raise gd.ApplicationRegisterError(message)
        cls.children.append(child)
        return child

    def syncify(
        self,
        func: Callable[_P, Coroutine[Any, Any, _T]],
    ) -> Callable[_P, _T]:
        match self.run_mode:
            case "api":
                @functools.wraps(func)
                def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _T:
                    wrapped = functools.partial(func, *args, **kwargs)
                    return anyio.from_thread.run(wrapped)
            case "cli":
                @functools.wraps(func)
                def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _T:
                    coro = func(*args, **kwargs)
                    return asyncio.run(coro)
            case "gui":
                @functools.wraps(func)
                def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _T:
                    coro = func(*args, **kwargs)
                    fut = asyncio.run_coroutine_threadsafe(coro, loop)
                    return fut.result()

                loop = self.panel_event_loop
        return wrapper

    def to_netcdf(
        self,
        source: xr.Dataset,
        destination: "StrPath | UPath",
        *,
        model: type[pa.DatasetModel] | None = None,
    ) -> str:
        if isinstance(destination, UPath) and destination.storage_options:
            raise NotImplementedError
        source = self._dataset_postprocessing(source, model)
        destination = str(destination)
        source.to_netcdf(  # pyright: ignore[reportUnknownMemberType]
            destination,
            format="NETCDF4",
            engine="netcdf4",
            auto_complex=True,
        )
        return destination

    def to_zarr(
        self,
        source: xr.Dataset,
        destination: "StrPath | UPath",
        *,
        model: type[pa.DatasetModel] | None = None,
    ) -> str:
        source = self._dataset_postprocessing(source, model)
        if isinstance(destination, UPath):
            storage_options = dict(destination.storage_options)
        else:
            storage_options = None
        destination = str(destination)
        with _convert.enable_zarr_v3():
            source.to_zarr(  # pyright: ignore[reportUnknownMemberType]
                destination,
                storage_options=storage_options,
                zarr_format=3,
            )
        return destination

    def dataset_metadata(self) -> dict[str, object]:
        meta: dict[str, object] = {}
        if comment := self.dataset_comment():
            meta["comment"] = comment
        if conventions := self.dataset_conventions():
            meta["Conventions"] = conventions
        if history := self.dataset_history():
            meta["history"] = history
        if institution := self.dataset_institution():
            meta["institution"] = institution
        if references := self.dataset_references():
            meta["references"] = references
        if source := self.dataset_source():
            meta["source"] = source
        if title := self.dataset_title():
            meta["title"] = title
        return meta

    def dataset_comment(self) -> str | None:
        """Return the comment for output datasets.

        See https://wiki.esipfed.org/Attribute_Convention_for_Data_Discovery_1-3#comment
        """

    def dataset_conventions(self) -> str | None:
        """Return the conventions for output datasets.

        See https://cfconventions.org/cf-conventions/cf-conventions.html#identification-of-conventions
        """

    def dataset_history(self) -> str | None:
        lines: list[str] = []
        for name in self._pydantic_fields_for_main():
            match getattr(self, name, None):
                case xr.Dataset(attrs={"history": str(history)}):
                    lines += history.splitlines()
                case _:
                    pass
        if line := self.dataset_history_line():
            lines.append(line)
        return "\n".join(lines) if lines else None

    def dataset_history_line(self) -> str | None:
        raise NotImplementedError

    def dataset_institution(self) -> str | None:
        for name in self._pydantic_fields_for_main():
            match getattr(self, name, None):
                case xr.Dataset(attrs={"institution": str(institution)}):
                    return institution
                case _:
                    pass
        return None

    def dataset_references(self) -> str | None:
        """Return the references for output datasets.

        See https://wiki.esipfed.org/Attribute_Convention_for_Data_Discovery_1-3#references
        """

    def dataset_source(self) -> str | None:
        for module in type(self).__module__.split(".", 1)[0], "gandharva":
            try:
                version = importlib.metadata.version(module)
            except ModuleNotFoundError:  # noqa: PERF203
                pass
            else:
                return f"{_base.normalize(module)}/{version}"
        return None

    def dataset_title(self) -> str | None:
        """Return the title for output datasets.

        See https://docs.unidata.ucar.edu/nug/2.0-draft/nug_conventions.html#title
        """

    def _dataset_postprocessing(
        self,
        source: xr.Dataset,
        model: type[pa.DatasetModel] | None,
    ) -> xr.Dataset:
        try:
            metpy = cast("MetPyDatasetAccessor", source.metpy)
        except AttributeError:
            pass
        else:
            source = cast("xr.Dataset", metpy.dequantify())
        source = source.assign_attrs(self.dataset_metadata())
        if model:
            source = model.validate(source)
        return source

    @classmethod
    def _registered(cls, parent: type["Gandharva"]) -> bool:
        children = parent.children
        return cls in children or any(map(cls._registered, children))
