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

"""Test notifications."""

import contextlib
import io
import logging
import types

import pydantic_settings
import pytest
from typing_extensions import override

import gandharva as gd


class _CheckLoggingState(
    contextlib.ContextDecorator,
    contextlib.AbstractContextManager[None, None],
):
    @override
    def __enter__(self) -> None:
        assert not _logger.level
        assert _logger.getEffectiveLevel() == logging.WARNING

    @override
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: types.TracebackType | None,
        /,
    ) -> None:
        self.__enter__()


_check_logging_state = _CheckLoggingState()


@_check_logging_state
def test_notifications_cli() -> None:
    """Test notifications in CLI mode."""
    app = _PlainNotifications.to_cli()
    with io.StringIO() as f:
        handler = logging.StreamHandler(f)
        _logger.addHandler(handler)
        try:
            pydantic_settings.CliApp.run(app, cli_args=[])
        finally:
            _logger.removeHandler(handler)
        f.seek(0)
        assert next(f) == "Warning message\n"
        assert next(f) == "Error message\n"
        assert next(f) == "Critical message\n"
        assert next(f, None) is None


@pytest.mark.xfail(raises=NotImplementedError)
@_check_logging_state
def test_notifications_gui() -> None:
    """Test notifications in GUI mode."""
    raise NotImplementedError


class _PlainNotifications(gd.Gandharva):
    @override
    def main(self) -> None:
        self.debug("Debug message")
        self.info("%s message", "Info")
        self.success("%s %s", "Success", "message")
        self.warning("Warning message")
        self.error("%s message", "Error")
        self.critical("%s %s", "Critical", "message")


_logger = logging.getLogger("_gandharva")
