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

"""Test sub-applications."""

import fastapi.testclient
import pydantic_settings
import pytest
from typing_extensions import override

import gandharva as gd


def test_register_abc() -> None:
    """Abstract applications should not become a parent or a child."""
    with pytest.raises(gd.ApplicationRegisterError):
        _Abstract.register(_Concrete)
    with pytest.raises(gd.ApplicationRegisterError):
        _Concrete.register(_Abstract)
    with pytest.raises(gd.ApplicationRegisterError):
        gd.Gandharva.register(_Concrete)
    with pytest.raises(gd.ApplicationRegisterError):
        _Concrete.register(gd.Gandharva)


def test_register_cycle() -> None:
    """Register should fail if a cycle is detected."""
    with pytest.raises(gd.ApplicationRegisterError):
        _Parent.register(_Parent)
    with pytest.raises(gd.ApplicationRegisterError):
        _Child.register(_Parent)
    with pytest.raises(gd.ApplicationRegisterError):
        _Grandchild.register(_Parent)


def test_subapp_api() -> None:
    """Sub-applications should be mapped to endpoints in API mode."""
    with fastapi.testclient.TestClient(_Parent()) as client:
        for endpoint in "/", "/child-2/", "/child-2/grandchild/":
            response = client.get(endpoint)
            response.raise_for_status()
            assert response.json()["data"] == endpoint
        response = client.post("/child/", json={})
        response.raise_for_status()
        assert response.json()["data"] == "/child/"


def test_subapp_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sub-applications should be mapped to subcommands in CLI mode."""
    monkeypatch.setenv("GANDHARVA_CHILD_NAME", "overwritten")
    app = _Parent.to_cli()

    parent = pydantic_settings.CliApp.run(app, cli_args=[])
    assert not parent.child  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
    assert not parent.child_2  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]

    assert pydantic_settings.CliApp.run(
        app,
        cli_args=["child"],
    ).child.name == "overwritten"  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]

    assert pydantic_settings.CliApp.run(
        app,
        cli_args=["child-2", "grandchild"],
    ).child_2.grandchild  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]


def test_subapp_gui() -> None:
    """Sub-applications should be mapped to pages in GUI mode."""
    assert _Parent.to_panels().keys() == {
        "/",
        "/child",
        "/child-2",
        "/child-2/grandchild",
    }


class _Abstract(gd.Gandharva):
    pass


class _Concrete(gd.Gandharva):
    @override
    def main(self) -> None:
        pass


class _Parent(gd.Gandharva):
    model_config = pydantic_settings.SettingsConfigDict(
        env_nested_delimiter="_",
        env_prefix="GANDHARVA_",
        env_prefix_target="all",
    )

    @classmethod
    @override
    def cli_env_settings(cls) -> bool:
        return True

    @override
    def main(self) -> str:
        return "/"


@_Parent.register
class _Child(gd.Gandharva):
    name: str = "child"

    @override
    def main(self) -> str | None:
        return "/child/" if self.run_mode == "api" else None


@_Parent.register
class _Child2(gd.Gandharva):
    @override
    def main(self) -> str:
        return "/child-2/"


@_Child2.register
class _Grandchild(gd.Gandharva):
    @override
    def main(self) -> str:
        return "/child-2/grandchild/"
