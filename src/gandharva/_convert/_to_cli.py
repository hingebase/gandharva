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

__all__ = ["to_cli"]

import functools
import itertools

import pydantic_core
import rich
from rich.table import Table
from typing_extensions import override

from . import _common


def to_cli(value: object, *, json: bool = False) -> None:
    if json:
        data = pydantic_core.to_jsonable_python(value, inf_nan_mode="null")
        rich.print_json(data=data, allow_nan=False)
    else:
        _to_cli(value)


@functools.singledispatch
def _to_cli(value: object) -> None:
    data = pydantic_core.to_jsonable_python(value)
    elem = _RichDisplay().element(data)
    rich.print(elem)


@_to_cli.register
def _(value: None) -> None:
    pass


class _RichDisplay(_common.RichDisplay[str, Table]):
    @override
    def text(self, data: str) -> str:
        return data

    @override
    def long_table(self, data: _common.LongTable) -> Table:
        table = Table(show_header=False)
        for row in data:
            table.add_row(*map(str, row))
        return table

    @override
    def wide_table(self, data: _common.WideTable) -> Table:
        columns = sorted(set(itertools.chain.from_iterable(data)))
        table = Table(*columns, show_header=True)
        for row in data:
            table.add_row(*[str(row.get(col, "")) for col in columns])
        return table
