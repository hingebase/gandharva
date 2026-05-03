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

__all__ = ["APIRouteParameters", "APIRouterParameters", "FastAPIParameters"]

from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Generic

import fastapi
from typing_extensions import Any, Never, Required, TypedDict, TypeVar

if TYPE_CHECKING:
    from enum import Enum

    from fastapi.params import Depends
    from fastapi.routing import APIRoute
    from starlette.routing import BaseRoute
    from starlette.types import ASGIApp, Lifespan

_T = TypeVar("_T")


class _APIRouter(TypedDict, Generic[_T], extra_items=Any, total=False):
    callbacks: list["BaseRoute"] | None
    default_response_class: type[fastapi.Response]
    dependencies: Sequence["Depends"] | None
    generate_unique_id_function: Callable[["APIRoute"], str]
    lifespan: "Lifespan[_T] | None"
    on_shutdown: Never
    on_startup: Never
    redirect_slashes: bool
    responses: dict[int | str, dict[str, Any]] | None
    routes: Never
    strict_content_type: bool


class APIRouteParameters(TypedDict, extra_items=Any, total=False):
    path: Never
    response_model: Never
    status_code: int | None
    tags: list["str | Enum"] | None
    dependencies: Sequence["Depends"] | None
    summary: Required[str]
    description: str | None
    response_description: str
    responses: Never
    deprecated: bool | None
    operation_id: str | None
    response_model_include: Never
    response_model_exclude: Never
    response_model_by_alias: bool
    response_model_exclude_unset: Never
    response_model_exclude_defaults: Never
    response_model_exclude_none: Never
    include_in_schema: bool
    response_class: type[fastapi.Response]
    name: Never
    callbacks: list["BaseRoute"] | None
    openapi_extra: dict[str, Any] | None
    generate_unique_id_function: Callable[["APIRoute"], str]


class APIRouterParameters(_APIRouter[Any], total=False):
    prefix: Never
    tags: list["str | Enum"] | None
    default: "ASGIApp | None"
    dependency_overrides_provider: Never
    route_class: type["APIRoute"]
    deprecated: bool | None
    include_in_schema: bool


class FastAPIParameters(_APIRouter[fastapi.FastAPI], total=False):
    debug: Never
    title: str
    summary: str | None
    description: str
    version: str
    openapi_url: str | None
    openapi_tags: list[dict[str, Any]] | None
    servers: list[dict[str, Any]] | None
    docs_url: str | None
    redoc_url: str | None
    swagger_ui_oauth2_redirect_url: str | None
    swagger_ui_init_oauth: dict[str, Any] | None
    middleware: Never
    exception_handlers: Never
    terms_of_service: str | None
    contact: dict[str, Any] | None
    license_info: dict[str, Any] | None
    openapi_prefix: Never
    root_path: str
    root_path_in_servers: bool
    webhooks: fastapi.APIRouter | None
    deprecated: Never
    include_in_schema: Never
    swagger_ui_parameters: dict[str, Any] | None
    separate_input_output_schemas: bool
    openapi_external_docs: dict[str, Any] | None
