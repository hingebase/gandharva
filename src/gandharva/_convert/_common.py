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

__all__ = ["LongTable", "RichDisplay", "WideTable"]

import abc
import itertools
import json
from collections.abc import Iterator
from typing import Generic, TypeGuard

from pydantic import JsonValue
from typing_extensions import TypeVar

_Atom = str | bool | int | float | None
LongTable = Iterator[tuple[_Atom, ...]]
WideTable = list[dict[str, _Atom]]

_TableT = TypeVar("_TableT")
_TextT = TypeVar("_TextT")


class RichDisplay(abc.ABC, Generic[_TextT, _TableT]):
    @abc.abstractmethod
    def text(self, data: str) -> _TextT:
        raise NotImplementedError

    @abc.abstractmethod
    def long_table(self, data: LongTable) -> _TableT:
        raise NotImplementedError

    @abc.abstractmethod
    def wide_table(self, data: WideTable) -> _TableT:
        raise NotImplementedError

    def element(self, data: JsonValue) -> _TextT | _TableT:
        try:
            if isinstance(data, dict):
                return self._long_table(_flatten_dict(data))
            if isinstance(data, list):
                if _is_wide_table(data):
                    return self.wide_table(data)
                return self._long_table(_flatten_list(data))
        except _EmptyError:
            data = json.dumps(
                data,
                check_circular=False,
                ensure_ascii=False,
                separators=(",", ":"),
            )
        else:
            data = str(data)
        return self.text(data)

    def _long_table(self, data: LongTable) -> _TableT:
        try:
            values, *keys = itertools.zip_longest(*data, fillvalue="")
        except ValueError:
            raise _EmptyError from None
        return self.long_table(zip(*keys, values, strict=True))


class _EmptyError(Exception):
    pass


def _flatten_dict(data: dict[str, JsonValue], *prefix: str | int) -> LongTable:
    for k, v in data.items():
        match v:
            case dict():
                yield from _flatten_dict(v, *prefix, k)
            case list():
                yield from _flatten_list(v, *prefix, k)
            case _:
                yield v, *prefix, k


def _flatten_list(data: list[JsonValue], *prefix: str | int) -> LongTable:
    for i, v in enumerate(data):
        match v:
            case dict():
                yield from _flatten_dict(v, *prefix, i)
            case list():
                yield from _flatten_list(v, *prefix, i)
            case _:
                yield v, *prefix, i


def _is_wide_table(data: list[JsonValue]) -> TypeGuard[WideTable]:
    for item in data:
        if not isinstance(item, dict):
            return False
        for value in item.values():
            if not isinstance(value, _Atom):
                return False
    return True
