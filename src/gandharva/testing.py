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

"""Test only: not for external use."""

__all__ = ["TESTING", "BytesIO", "reset_logger"]

import contextlib
import logging
import os
import types
from io import BytesIO

from typing_extensions import override

TESTING = "PYTEST_VERSION" in os.environ


class _ResetLogger(contextlib.AbstractAsyncContextManager[None, None]):
    @override
    async def __aenter__(self) -> None:
        pass

    @override
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: types.TracebackType | None,
        /,
    ) -> None:
        self()

    def __call__(self, handler: logging.Handler | None = None) -> None:
        logger = logging.getLogger("_gandharva")
        logger.propagate = True
        if handler:
            logger.removeHandler(handler)


reset_logger = _ResetLogger()
