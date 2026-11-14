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

"""Shared fixtures."""

import contextlib
import os
import socket
import sys

import pytest


@pytest.fixture
def server_port() -> int:
    """Find an available port.

    Returns:
        The port number.

    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


if sys.platform == "win32" and sys.version_info < (3, 12):
    # https://github.com/lnqs/textual-image/pull/163
    class _DisableStdout(contextlib.redirect_stdout[None]):
        _stream = "__stdout__"

    with _DisableStdout(None):
        from textual_image import renderable
    del renderable

for key in list(os.environ):
    if key.startswith(("BOKEH_", "PANEL_")):
        del os.environ[key]
