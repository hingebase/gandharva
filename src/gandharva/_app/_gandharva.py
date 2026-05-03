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
import inspect
from collections.abc import Callable, Coroutine

import anyio.from_thread
from typing_extensions import Any, ParamSpec, TypeVar, disjoint_base

import gandharva as gd

from . import _fastapi, _panel

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

    @classmethod
    def _registered(cls, parent: type["Gandharva"]) -> bool:
        children = parent.children
        return cls in children or any(map(cls._registered, children))
