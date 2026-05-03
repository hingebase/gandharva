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

"""Test creating Gandharva subclasses."""

import dataclasses

import attrs
import pydantic
import pydantic_settings
import pytest
from typing_extensions import override

import gandharva as gd


def test_abstract_subclass() -> None:
    """Gandharva should not run without a concrete main() method."""
    with pytest.raises(gd.ApplicationBuilderError):
        _App.to_pydantic()


def test_multi_level_inheritance() -> None:
    """Gandharva should support multi-level inheritance."""
    model = _App3.to_cli()
    assert model.model_config.get("json_file") == "app3.json"
    assert model.model_config.get("toml_file") == "app1.toml"
    assert model.model_config.get("yaml_file") == "app2.yml"
    assert "field" not in model.__pydantic_fields__
    assert (field1 := model.__pydantic_fields__.get("field1"))
    assert (field2 := model.__pydantic_fields__.get("field2"))
    assert (field3 := model.__pydantic_fields__.get("field3"))
    assert field1.annotation is bool
    assert field2.annotation is int
    assert field3.annotation is float


def test_inheriting_from_attrs() -> None:
    """Gandharva should not inherit from `@attrs.define` classes.

    The old `@attr.s` decorator has been deprecated thus doesn't require
    a separate test.
    """
    with pytest.raises(gd.ApplicationBuilderError):
        type("App", (_AttrsClass, gd.Gandharva), {})
    with pytest.raises(gd.ApplicationBuilderError):
        type("App", (gd.Gandharva, _AttrsClass), {})


def test_inheriting_from_dataclasses() -> None:
    """Gandharva should not inherit from stdlib dataclasses.

    `@pydantic.dataclasses.dataclass` classes are also standard
    dataclasses thus don't require a separate test.
    """
    with pytest.raises(gd.ApplicationBuilderError):
        type("App", (_DataClass, gd.Gandharva), {})
    with pytest.raises(gd.ApplicationBuilderError):
        type("App", (gd.Gandharva, _DataClass), {})


def test_inheriting_from_pydantic() -> None:
    """Gandharva should not inherit from `pydantic.BaseModel` classes.

    `pydantic_settings.BaseSettings` is a subclass of `BaseModel` thus
    doesn't require a separate test.
    """
    with pytest.raises(gd.ApplicationBuilderError):
        type("App", (_PydanticClass, gd.Gandharva), {})
    with pytest.raises(gd.ApplicationBuilderError):
        type("App", (gd.Gandharva, _PydanticClass), {})


class _App(gd.Gandharva):
    field: str


class _App1(gd.Gandharva):
    model_config = pydantic_settings.SettingsConfigDict(
        json_file="app1.json",
        toml_file="app1.toml",
    )
    field1: bool


class _App2(gd.Gandharva, toml_file="app2.toml", yaml_file="app2.yml"):
    field2: int


class _PlainClass:
    model_config = pydantic_settings.SettingsConfigDict(yaml_file="plain.yml")
    field: str


class _App3(_App1, _PlainClass, _App2):
    model_config = pydantic_settings.SettingsConfigDict(
        json_file="app3.json",
    )
    field3: float

    @override
    def main(self) -> None:
        pass


@attrs.define
class _AttrsClass:
    field: str


@dataclasses.dataclass
class _DataClass:
    field: str


class _PydanticClass(pydantic.BaseModel):
    field: str
