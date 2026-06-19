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

__all__ = ["from_pydantic_field"]

import types
from typing import cast, get_args, get_origin

import pandera.xarray as pa
import pydantic.fields
import xarray as xr


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


def _upath_to_xarray(
    source: object,
    target: type[pa.DatasetModel] | None = None,
) -> xr.Dataset:
    raise NotImplementedError
