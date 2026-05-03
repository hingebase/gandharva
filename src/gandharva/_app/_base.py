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

__all__ = ["App", "normalize"]

import abc
import inspect
import os
from typing import TYPE_CHECKING, ClassVar, Literal

import packaging.utils
import platformdirs
import pydantic.alias_generators
from typing_extensions import final

if TYPE_CHECKING:
    import gandharva as gd


class App(abc.ABC):
    children: ClassVar["list[type[gd.Gandharva]]"]
    run_mode: Literal["api", "cli", "gui"]

    @abc.abstractmethod
    def main(self) -> object:
        raise NotImplementedError

    @classmethod
    def app_description(cls) -> str:
        if doc := cls.__doc__:
            return inspect.cleandoc(doc)
        # Unlike `inspect.getdoc`, we are not interested in the base
        # classes
        return ""

    @classmethod
    def app_normalized_name(cls) -> str:
        return normalize(cls.__name__)

    @classmethod
    def app_summary(cls) -> str:
        if lines := cls.app_description().splitlines():
            return lines[0].rstrip(".")
        return ""

    @final
    def __init__(self, run_mode: Literal["api", "cli", "gui"]) -> None:
        self.run_mode = run_mode


def normalize(name: str) -> str:
    return packaging.utils.canonicalize_name(
        pydantic.alias_generators.to_snake(name).removeprefix("_"),
        validate=True,
    )


os.environ.setdefault(
    "HYPOTHESIS_STORAGE_DIRECTORY",
    platformdirs.user_cache_dir("gandharva", appauthor=False),
)
