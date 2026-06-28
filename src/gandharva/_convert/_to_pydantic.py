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

__all__ = ["to_pydantic_field"]

import types
from typing import cast, get_origin

import upath
import xarray as xr
from pydantic.fields import FieldInfo

import gandharva as gd


def to_pydantic_field(source: FieldInfo) -> FieldInfo:
    ann = cast("object", source.annotation)
    if isinstance(ann, types.GenericAlias):
        origin = get_origin(ann)
        if issubclass(origin, xr.Dataset):
            return _xarray_to_upath(source)
    elif isinstance(ann, type):
        if issubclass(ann, xr.Dataset):
            return _xarray_to_upath(source)
    return source


def _xarray_to_upath(source: FieldInfo) -> FieldInfo:
    if not source.is_required():
        message = (
            "Default values or factory functions for input datasets are "
            "unsupported"
        )
        raise gd.ApplicationBuilderError(message)
    return FieldInfo.from_annotated_attribute(
        upath.UPath,
        gd.Field(**source.asdict()["attributes"]),
    )
