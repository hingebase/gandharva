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

__all__ = ["App"]

import importlib.metadata
import inspect
from email.message import Message
from typing import Annotated, Literal, no_type_check

import fastapi
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
    def fastapi_apirouter_params(cls) -> gd.typing.APIRouterParameters:
        return {}

    @classmethod
    def fastapi_app_params(cls, meta: Message) -> gd.typing.FastAPIParameters:
        kwargs: gd.typing.FastAPIParameters = {
            "summary": meta.get("Summary"),
        }
        for key in "description", "version":
            if value := meta.get(key):
                kwargs[key] = value
        if name := meta.get("Name"):
            kwargs["title"] = name.replace("-", " ").title()
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
            cls.fastapi_apirouter_params(),
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
        distribution_name = cls.__module__.split(".", 1)[0]
        try:
            meta = importlib.metadata.metadata(distribution_name)
        except ModuleNotFoundError:
            message = Message()
        else:
            message = meta if isinstance(meta, Message) else Message()
        app = fastapi.FastAPI(**cls.fastapi_app_params(message))
        cls._fastapi_routes(app)
        return app

    def _fastapi_main(self, request: fastapi.Request) -> object:
        self.fastapi_request = request
        try:
            result = self.main()
            result = _convert.to_response(result)
        except Exception as e:  # noqa: BLE001
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
            inspect.signature(cls.main, eval_str=True).return_annotation,
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
                self = cls.from_pydantic(body, run_mode="api")
                return self._fastapi_main(request)
        else:
            @router.get(**kwargs)
            def _(request: fastapi.Request) -> object:
                self = cls(run_mode="api")
                return self._fastapi_main(request)

        for child in cls.children:
            router.include_router(child.to_router())
        cls.fastapi_post_init(router)
