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

__all__ = ["App", "normalize", "summary"]

import abc
import contextlib
import importlib.metadata
import inspect
import logging
import os
from collections.abc import Mapping
from email.message import Message
from typing import TYPE_CHECKING, ClassVar, Literal

import packaging.utils
import platformdirs
import pydantic.alias_generators
import upath
from typing_extensions import Any, TypeForm, final

if TYPE_CHECKING:
    from logging import _ExcInfoType  # pyright: ignore[reportPrivateUsage]

    import gandharva as gd


class App(abc.ABC):
    children: ClassVar["list[type[gd.Gandharva]]"]
    run_mode: Literal["api", "cli", "gui"]

    @abc.abstractmethod
    def main(self) -> object:
        raise NotImplementedError

    @abc.abstractmethod
    def auto_plotting_backend(self) -> contextlib.AbstractContextManager[None]:
        raise NotImplementedError

    @abc.abstractmethod
    def dataset_auth(self, source: upath.UPath, /) -> upath.UPath:
        raise NotImplementedError

    @classmethod
    def app_description(cls) -> str:
        if doc := cls.__doc__:
            return inspect.cleandoc(doc)
        # Unlike `inspect.getdoc`, we are not interested in the base
        # classes
        return ""

    @classmethod
    @final
    def app_distribution_metadata(cls) -> Message:
        for distribution_name in cls.__module__.split(".", 1)[0], "gandharva":
            try:
                meta = importlib.metadata.metadata(distribution_name)
            except ModuleNotFoundError:  # ruff: ignore[try-except-in-loop]
                pass
            else:
                if isinstance(meta, Message):
                    return meta
        return Message()

    @classmethod
    def app_normalized_name(cls) -> str:
        return normalize(cls.__name__)

    @classmethod
    def app_summary(cls) -> str:
        return summary(cls.app_description())

    @classmethod
    def app_title(cls, meta: Message | None = None) -> str | None:
        if meta is None:
            meta = cls.app_distribution_metadata()
        if name := meta.get("Name"):
            title = name.replace("-", " ")
            return title[:1].upper() + title[1:]
        return None

    @classmethod
    def main_return_annotation(cls) -> TypeForm[Any]:
        main = cls.main
        main.__signature__ = sig = inspect.signature(main, eval_str=True)
        return sig.return_annotation

    @final
    def __init__(self, run_mode: Literal["api", "cli", "gui"]) -> None:
        self.run_mode = run_mode

    def debug(
        self,
        msg: object,
        *args: object,
        extra: Mapping[str, object] | None = None,
    ) -> None:
        del self
        _logger.debug(msg, *args, stacklevel=2, extra=extra)

    def info(
        self,
        msg: object,
        *args: object,
        gui_duration: int = 3000,
        extra: Mapping[str, object] | None = None,
    ) -> None:
        if self.run_mode == "gui":
            extra = _extra(gui_duration, extra)
        _logger.info(msg, *args, stacklevel=2, extra=extra)

    def success(
        self,
        msg: object,
        *args: object,
        gui_duration: int = 3000,
        extra: Mapping[str, object] | None = None,
    ) -> None:
        if self.run_mode == "gui":
            extra = _extra(gui_duration, extra)
        _logger.log(25, msg, *args, stacklevel=2, extra=extra)

    def warning(
        self,
        msg: object,
        *args: object,
        api_exc_info: "_ExcInfoType | None" = None,
        gui_duration: int = 0,
        extra: Mapping[str, object] | None = None,
    ) -> None:
        self._log(
            logging.WARNING,
            msg,
            *args,
            api_exc_info=api_exc_info,
            gui_duration=gui_duration,
            extra=extra,
        )

    def error(
        self,
        msg: object,
        *args: object,
        api_exc_info: "_ExcInfoType | None" = None,
        gui_duration: int = 0,
        extra: Mapping[str, object] | None = None,
    ) -> None:
        self._log(
            logging.ERROR,
            msg,
            *args,
            api_exc_info=api_exc_info,
            gui_duration=gui_duration,
            extra=extra,
        )

    def critical(
        self,
        msg: object,
        *args: object,
        api_exc_info: "_ExcInfoType | None" = None,
        gui_duration: int = 0,
        extra: Mapping[str, object] | None = None,
    ) -> None:
        self._log(
            logging.CRITICAL,
            msg,
            *args,
            api_exc_info=api_exc_info,
            gui_duration=gui_duration,
            extra=extra,
        )

    def _log(
        self,
        level: int,
        msg: object,
        *args: object,
        api_exc_info: "_ExcInfoType | None" = None,
        gui_duration: int = 0,
        extra: Mapping[str, object] | None = None,
    ) -> None:
        match self.run_mode:
            case "api":
                exc_info = api_exc_info
            case "cli":
                exc_info = None
            case "gui":
                exc_info = None
                extra = _extra(gui_duration, extra)
        _logger.log(
            level,
            msg,
            *args,
            exc_info=exc_info,
            stacklevel=3,
            extra=extra,
        )


def normalize(name: str) -> str:
    return packaging.utils.canonicalize_name(
        pydantic.alias_generators.to_snake(name).removeprefix("_"),
        validate=True,
    )


def summary(description: str) -> str:
    # str.split(str) never returns a empty list, see
    # https://docs.python.org/3/library/stdtypes.html#str.split
    return description.split("\n", maxsplit=1)[0].rstrip(".").strip()


def _extra(
    duration: int,
    extra: Mapping[str, object] | None,
) -> dict[str, object]:
    if not extra:
        return {"gandharva.gui.duration": duration}
    merged = dict(extra)
    merged["gandharva.gui.duration"] = duration
    return merged


os.environ.setdefault(
    "HYPOTHESIS_STORAGE_DIRECTORY",
    platformdirs.user_cache_dir("gandharva", appauthor=False),
)
_logger = logging.getLogger("_gandharva")
