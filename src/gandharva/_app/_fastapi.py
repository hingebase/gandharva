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

__all__ = ["App", "get_lock"]

import contextlib
import weakref
from email.message import Message
from typing import Annotated, Literal, no_type_check

import anyio.lowlevel
import fastapi
import matplotlib as mpl
import starlette.types
from anyio.from_thread import threadlocals  # pyright: ignore[reportPrivateImportUsage]
from distributed.scheduler import RLock  # pyright: ignore[reportPrivateImportUsage]
from typing_extensions import Any, Self, final, overload

import gandharva as gd
from gandharva import _convert

from . import _pydantic


class App(_pydantic.App):
    fastapi_request: fastapi.Request

    @classmethod
    def fastapi_apiroute_params(cls) -> gd.typing.APIRouteParameters:
        return {
            "summary": cls.app_summary(),
            "description": cls.app_description(),
            "deprecated": hasattr(cls, "__deprecated__"),
        }

    @classmethod
    def fastapi_apirouter_params(
        cls,
        lifespan: starlette.types.Lifespan[Any],
    ) -> gd.typing.APIRouterParameters:
        return {"lifespan": lifespan}

    @classmethod
    def fastapi_app_params(
        cls,
        lifespan: starlette.types.Lifespan[fastapi.FastAPI],
        meta: Message,
    ) -> gd.typing.FastAPIParameters:
        kwargs: gd.typing.FastAPIParameters = {
            "lifespan": lifespan,
            "summary": meta.get("Summary"),
        }
        for key in "description", "version":
            if value := meta.get(key):
                kwargs[key] = value
        if title := cls.app_title(meta):
            kwargs["title"] = title
        if identifier := meta.get("License-Expression"):
            kwargs["license_info"] = {
                "name": "License",
                "identifier": identifier,
            }
        return kwargs

    @classmethod
    def fastapi_post_init(
        cls,
        router: fastapi.APIRouter | fastapi.FastAPI,
    ) -> None:
        pass

    @classmethod
    @final
    def to_router(cls) -> fastapi.APIRouter:
        kwargs: dict[str, Any] = dict(
            cls.fastapi_apirouter_params(_lifespan),
            prefix="/" + cls.app_normalized_name(),
        )
        router = fastapi.APIRouter(**kwargs)
        cls._fastapi_routes(router)
        return router

    @overload
    def __new__(cls, run_mode: None = ...) -> fastapi.FastAPI: ...
    @overload
    def __new__(cls, run_mode: Literal["api", "cli", "gui"]) -> Self: ...
    @final
    def __new__(  # pyright: ignore[reportInconsistentConstructor]
        cls,
        run_mode: Literal["api", "cli", "gui"] | None = None,
    ) -> fastapi.FastAPI | Self:
        if run_mode:
            return super().__new__(cls)
        meta = cls.app_distribution_metadata()
        if meta.get("Name", "gandharva") == "gandharva":
            meta = Message()
        app = fastapi.FastAPI(**cls.fastapi_app_params(_lifespan, meta))
        cls._fastapi_routes(app)
        return app

    def _fastapi_main(self) -> object:
        with self.auto_plotting_backend():
            try:
                result = self.main()
                result = _convert.to_response(result, self)
            except Exception as e:  # ruff: ignore[blind-except]
                return {"code": 1, "message": str(e), "data": None}
        return result

    @classmethod
    def _fastapi_routes(
        cls,
        router: fastapi.APIRouter | fastapi.FastAPI,
    ) -> None:
        responses: dict[int | str, dict[str, Any]] = {}
        kwargs: dict[str, Any] = dict(
            cls.fastapi_apiroute_params(),
            path="/",
            responses=responses,
            name=cls.__name__,
        )
        _convert.to_response_model(
            f"__Response_{cls.__name__}",
            cls.main_return_annotation(),
            kwargs,
        )
        model = cls.to_pydantic()
        if model.__pydantic_fields__:
            @no_type_check
            @router.post(**kwargs)
            def _(
                request: fastapi.Request,
                body: Annotated[model, fastapi.Body()],
            ) -> object:
                self = cls(run_mode="api")
                self.fastapi_request = request
                with self.from_pydantic(body):
                    return self._fastapi_main()
        else:
            @router.get(**kwargs)
            def _(request: fastapi.Request) -> object:
                self = cls(run_mode="api")
                self.fastapi_request = request
                return self._fastapi_main()

        for child in cls.children:
            router.include_router(child.to_router())
        cls.fastapi_post_init(router)


def get_lock() -> RLock:
    token: anyio.lowlevel.EventLoopToken = threadlocals.current_token
    return _locks[token.native_token]


def _lifespan(_: fastapi.FastAPI) -> contextlib.nullcontext[None]:
    mpl.use("agg")
    token = anyio.lowlevel.current_token().native_token
    if token not in _locks:
        _locks[token] = RLock()
    return _noop


_locks = weakref.WeakKeyDictionary[object, RLock]()
_noop = contextlib.nullcontext()
