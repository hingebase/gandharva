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

"""Test calling coroutine functions."""

import asyncio
import threading

import fastapi.testclient
import panel_material_ui as pmui
import pydantic_settings
from typing_extensions import override

import gandharva as gd


def test_syncify_api() -> None:
    """Call coroutine functions in API mode."""
    with fastapi.testclient.TestClient(_App()) as client:
        client.get("/").raise_for_status()


def test_syncify_cli() -> None:
    """Call coroutine functions in CLI mode."""
    pydantic_settings.CliApp.run(_App.to_cli(), cli_args=[])


def test_syncify_gui() -> None:
    """Call coroutine functions in GUI mode."""
    class App(_App):
        @override
        def main(self) -> None:
            super().main()
            event.set()  # Unreachable if main() raises an exception

    event = threading.Event()
    [submit] = App.__panel__().select(pmui.Button)
    submit.param.trigger("value")
    assert event.wait(60)


class _App(gd.Gandharva):
    @override
    def main(self) -> None:
        get_running_loop = self.syncify(_get_running_loop)
        if self.run_mode == "cli":
            assert get_running_loop() is not get_running_loop()
        else:
            assert get_running_loop() is get_running_loop()


async def _get_running_loop() -> asyncio.AbstractEventLoop:
    await asyncio.sleep(0)
    return asyncio.get_running_loop()
