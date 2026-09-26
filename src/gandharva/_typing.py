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

__all__ = ["Gandharva", "HoloVizTypes"]

from typing import TYPE_CHECKING

import holoviews as hv  # pyright: ignore[reportMissingTypeStubs]
import panel as pn
from typing_extensions import TypeAliasType

if TYPE_CHECKING:
    import gandharva as gd

# Prevent `functools.singledispatch` from evaluating the annotation
# string too early
Gandharva = TypeAliasType("Gandharva", "gd.Gandharva")

HoloVizTypes = pn.viewable.Viewable | hv.core.Dimensioned
