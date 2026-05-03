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

__all__ = ["to_response", "to_response_model"]

import functools

import fastapi
import pydantic
from typing_extensions import Any
from typing_inspection import introspection


@functools.singledispatch
def to_response(value: object) -> object:
    return {"code": 0, "message": "OK", "data": value}


def to_response_model(
    model_name: str,
    data: object,
    kwargs: dict[str, Any],
) -> None:
    try:
        kwargs["response_model"] = pydantic.create_model(
            model_name,
            code=int,
            message=str,
            data=data,
        )
    except pydantic.PydanticSchemaGenerationError:
        pass
    else:
        return
    kwargs["response_model"] = pydantic.create_model(
        model_name,
        code=int,
        message=str,
        data=Any,
    )
    ann = introspection.inspect_annotation(
        data,
        annotation_source=introspection.AnnotationSource.BARE,
        unpack_type_aliases="eager",
    )
    _to_responses(ann, kwargs["responses"])


def _to_responses(
    ann: introspection.InspectedAnnotation,
    responses: dict[int | str, dict[str, Any]],
) -> None:
    pass


@to_response.register
def _(value: fastapi.Response) -> fastapi.Response:
    return value
