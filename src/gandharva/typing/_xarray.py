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

__all__ = ["Dataset"]

import contextlib
from typing import TYPE_CHECKING

import hvplot.xarray  # pyright: ignore[reportMissingTypeStubs]  # ruff: ignore[typing-only-third-party-import]
import pandera.typing.xarray as xr
from typing_extensions import TypeVar

_T = TypeVar("_T")

if TYPE_CHECKING:
    import metpy  # pyright: ignore[reportMissingTypeStubs]

    class Dataset(xr.Dataset[_T]):
        @property
        def interactive(self) -> hvplot.xarray.XArrayInteractive: ...
        @property
        def hvplot(self) -> hvplot.hvPlot: ...
        @property
        def metpy(self) -> metpy.MetPyDatasetAccessor: ...
else:
    with contextlib.suppress(ImportError):
        import metpy  # ruff: ignore[typing-only-third-party-import]

    Dataset = xr.Dataset
