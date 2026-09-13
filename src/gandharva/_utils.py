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

__all__ = ["isclass", "undisplayable_info"]

import sys
import types

import holoviews as hv  # pyright: ignore[reportMissingTypeStubs]
import param
from holoviews.plotting import util  # pyright: ignore[reportMissingTypeStubs]

if sys.version_info >= (3, 11):
    from inspect import isclass
else:
    from typing_extensions import TypeIs

    def isclass(x: object, /) -> TypeIs[type[object]]:
        return not isinstance(x, types.GenericAlias) and isinstance(x, type)


def undisplayable_info(obj: hv.core.Dimensioned, *, html: bool = False) -> str:
    if obj.traverse(specs=hv.DynamicMap):  # pyright: ignore[reportUnknownMemberType]
        message = (
            "'holoviews.DynamicMap' objects are unsupported; see "
            "https://github.com/holoviz/holoviews/issues/5021 for details. If "
            "you're using 'hvplot', specify 'dynamic=False' to bypass this "
            "issue."
        )
        raise TypeError(message)
    if util.displayable(obj):  # pyright: ignore[reportUnknownMemberType]
        return ""
    if isinstance(obj, hv.Overlay):
        original = param.parameterized.warnings_as_exceptions
        param.parameterized.warnings_as_exceptions = True
        try:
            util.collate(obj)  # pyright: ignore[reportUnknownMemberType]
        finally:
            param.parameterized.warnings_as_exceptions = original
    if isinstance(obj, hv.NdLayout):
        obj = hv.Layout()
    return util.undisplayable_info(obj, html)  # pyright: ignore[reportUnknownMemberType]
