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

"""Test automatic conversion from input fields."""

from typing import Annotated

import fastapi.testclient
import panel as pn
import panel_material_ui as pmui
import pydantic
import pydantic_settings
from typing_extensions import override

import gandharva as gd


def test_nested_types_api() -> None:
    """Test nested input fields in API mode."""
    with fastapi.testclient.TestClient(_App()) as client:
        client.post("/", json={
            "base_model": {
                "field": ["a", "b"],
            },
            "data_class": [
                {"field": 0},
                {"field": 1},
            ],
        }).raise_for_status()


def test_nested_types_cli() -> None:
    """Test nested input fields in CLI mode."""
    pydantic_settings.CliApp.run(
        _App.to_cli(),
        cli_args=[
            "--base-model.field", "a",
            "--base-model.field", "b",
            "--data-class", '{"field": 0}',
            "--data-class", '{"field": 1}',
        ],
    )


def test_nested_types_gui() -> None:
    """Test nested input fields in GUI mode."""
    editor1, editor2, row = _sidebar(_App)
    assert isinstance(editor1, pn.widgets.JSONEditor)
    assert isinstance(editor2, pn.widgets.JSONEditor)
    _assert_submit_button(row)
    adapter = pydantic.TypeAdapter(dict[str, pydantic.JsonValue])
    assert adapter.validate_python(editor1.schema)["type"] == "object"
    assert adapter.validate_python(editor2.schema)["type"] == "array"


def test_union_type_gui() -> None:
    """Test union-typed input fields in GUI mode."""
    text, editor, row = _sidebar(_App2)
    assert isinstance(text, pmui.TextInput)
    assert isinstance(editor, pn.widgets.JSONEditor)
    _assert_submit_button(row)
    adapter = pydantic.TypeAdapter(dict[str, pydantic.JsonValue])
    any_of = adapter.validate_python(editor.schema)["anyOf"]
    assert isinstance(any_of, list)
    types: set[pydantic.JsonValue] = set()
    for schema in any_of:
        assert isinstance(schema, dict)
        types.add(schema["type"])
    assert types == {"integer", "string"}


class _BaseModel(pydantic.BaseModel):
    field: list[str] = []


@pydantic.dataclasses.dataclass
class _DataClass:
    field: int = -1


class _App(gd.Gandharva):
    base_model: _BaseModel = _BaseModel()
    data_class: Annotated[
        list[_DataClass],
        pydantic.Field(default_factory=list),
    ]

    @override
    def main(self) -> None:
        assert self.base_model.field == ["a", "b"]
        for i in range(2):
            assert self.data_class[i].field == i


class _App2(gd.Gandharva):
    homogeneous_union: pydantic.DirectoryPath | pydantic.FilePath
    inhomogeneous_union: int | str

    @override
    def main(self) -> None:
        pass


def _assert_submit_button(row: pn.viewable.Viewable) -> None:
    assert isinstance(row, pn.Row)
    space1, button, space2 = row
    assert isinstance(button, pmui.Button)
    assert isinstance(space1, pn.Spacer)
    assert isinstance(space2, pn.Spacer)


def _sidebar(app: type[gd.Gandharva]) -> pn.Column:
    template = pn.panel(app)  # pyright: ignore[reportUnknownMemberType]
    assert isinstance(template, pn.template.MaterialTemplate)
    sidebar = template.sidebar
    assert isinstance(sidebar, pn.Column)
    return sidebar
