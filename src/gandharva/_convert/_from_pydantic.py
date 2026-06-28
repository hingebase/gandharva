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

__all__ = ["enable_zarr_v3", "from_pydantic_field"]

import contextlib
import functools
import importlib.metadata
import os
import types
import warnings
from typing import cast, get_args, get_origin

import pandera.xarray as pa
import pydantic.fields
import xarray as xr
from packaging.version import Version
from typing_extensions import Any, override
from upath import UPath


@functools.lru_cache(maxsize=1)
def enable_zarr_v3() -> contextlib.AbstractContextManager[None, None]:
    try:
        zarr = importlib.metadata.version("zarr")
    except ModuleNotFoundError:
        pass
    else:
        if Version(zarr) >= Version("3"):
            return contextlib.nullcontext()
    os.environ["ZARR_V3_EXPERIMENTAL_API"] = "1"
    return _SuppressFutureWarning()


def from_pydantic_field(
    source: object,
    target: pydantic.fields.FieldInfo,
) -> object:
    ann = cast("object", target.annotation)
    if isinstance(ann, types.GenericAlias):
        origin = get_origin(ann)
        if issubclass(origin, xr.Dataset):
            match get_args(ann):
                case [type() as model] if issubclass(model, pa.DatasetModel):
                    return _upath_to_xarray(source, model)
                case _:
                    return _upath_to_xarray(source)
    elif isinstance(ann, type):
        if issubclass(ann, xr.Dataset):
            return _upath_to_xarray(source)
    return source


class _SuppressFutureWarning(contextlib.AbstractContextManager[None, None]):
    @override
    def __enter__(self) -> None:
        # Although zarr only emits the warning once, we always try
        # catching it in case there is an error before the warning
        self._ctx = ctx = warnings.catch_warnings()
        ctx.__enter__()
        warnings.filterwarnings(
            "ignore",
            category=FutureWarning,
            module="zarr._storage.store",
        )

    @override
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: types.TracebackType | None,
        /,
    ) -> None:
        self._ctx.__exit__(exc_type, exc_value, traceback)


def _upath_to_xarray(
    source: object,
    target: type[pa.DatasetModel] | None = None,
) -> xr.Dataset:
    if not isinstance(source, UPath):
        raise TypeError
    if (source / "zarr.json").is_file():
        with enable_zarr_v3():
            data = xr.open_zarr(  # pyright: ignore[reportUnknownMemberType]
                str(source),
                chunks=cast("Any", None),
                storage_options=source.storage_options,
                zarr_format=3,
            )
    else:
        if source.storage_options:
            raise NotImplementedError
        data = xr.open_dataset(  # pyright: ignore[reportUnknownMemberType]
            str(source),
            engine="netcdf4",
            auto_complex=True,
        )
    if target:
        data = target.validate(data)
    return data
