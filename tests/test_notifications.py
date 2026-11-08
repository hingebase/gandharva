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

import asyncio
import contextlib
import email.message
import io
import logging
import os
import threading
import time
import types
from collections.abc import Generator
from typing import TYPE_CHECKING, NoReturn

import fastapi.testclient
import logfire
import pydantic_settings
import pytest
import uvicorn
from logfire._internal import forwarding  # ruff: ignore[import-private-name]
from opentelemetry.proto.trace.v1.trace_pb2 import TracesData
from typing_extensions import override

import gandharva as gd

if TYPE_CHECKING:
    from opentelemetry.proto.common.v1.common_pb2 import AnyValue


class _CheckLoggingState(
    contextlib.ContextDecorator,
    contextlib.AbstractContextManager[None, None],
):
    @override
    def __enter__(self) -> None:
        assert not _logger.level
        assert _logger.getEffectiveLevel() == logging.WARNING
        assert _logger.propagate

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
def test_notifications_api(
    monkeypatch: pytest.MonkeyPatch,
    server_port: int,
) -> None:
    """Test notifications in API mode."""
    for name in list(os.environ):
        if name.startswith(("OTEL_", "FASTAPI_OTEL_", "LOGFIRE_")):
            monkeypatch.delenv(name)
    monkeypatch.setenv(
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        f"http://localhost:{server_port}",
    )
    monkeypatch.setattr(forwarding.OTLPForwardingManager, "submit", _submit)
    collector = fastapi.FastAPI()

    @collector.post("/{path:path}")
    async def _(path: str, request: fastapi.Request) -> fastapi.Response:
        if path == "v1/traces":
            requests.append(await request.body())
        return await lf.forward_export_request_starlette(request)

    requests: list[bytes] = []
    _logger.setLevel(logging.WARNING)
    try:
        with (
            _daemon_server(collector, server_port),
            fastapi.testclient.TestClient(_RichNotifications()) as client,
        ):
            lf = logfire.configure(local=True, send_to_logfire=False)
            client.get("/").raise_for_status()
            assert not requests  # Telemetry doesn't block the application
    finally:
        _logger.setLevel(logging.NOTSET)
    [body] = requests
    _check_content(body)


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
        self.warning("Warning message", api_exc_info=Exception("ignored"))
        self.error("%s message", "Error")
        self.critical("%s %s", "Critical", "message")


class _RichNotifications(gd.Gandharva):
    @override
    @classmethod
    def fastapi_telemetry_params(
        cls,
        meta: email.message.Message,
    ) -> gd.typing.LogfireConfiguration | None:
        kwargs = super().fastapi_telemetry_params(meta)
        assert kwargs
        kwargs["local"] = True
        return kwargs

    @override
    def main(self) -> None:
        self.debug("Debug message")
        self.info("%s message", "Info")
        self.success("%s %s", "Success", "message")
        try:
            _raise_runtime_error()
        except RuntimeError:
            # Default `api_exc_info=None` doesn't record the error
            self.warning("Warning message")
        try:
            _raise_runtime_error()
        except RuntimeError:
            self.error("%s message", "Error", api_exc_info=True)
        self.critical(
            "%s %s", "Critical", "message",
            extra={"gandharva.testing.is_critical": True},
        )


def _check_content(body: bytes) -> None:
    [resource_spans] = TracesData.FromString(body).resource_spans
    for entry in resource_spans.resource.attributes:
        if entry.key == "service.name":
            assert entry.value.string_value == "gandharva"
            break
    else:
        pytest.fail("'service.name' is missing")
    spans = {x.scope.name: x.spans for x in resource_spans.scope_spans}
    [fastapi_span] = spans["opentelemetry.instrumentation.fastapi"]
    assert not fastapi_span.parent_span_id
    span_attrs: list[dict[str, AnyValue]] = []

    # https://github.com/pydantic/logfire/issues/1118
    for logging_span in spans["logfire.stdlib.logging"]:
        assert logging_span.parent_span_id == fastapi_span.span_id
        assert logging_span.trace_id == fastapi_span.trace_id
        attrs = {x.key: x.value for x in logging_span.attributes}
        for name, expected in [
            ("code.filepath", __file__),
            ("logfire.logger_name", "_gandharva"),
            ("logfire.span_type", "log"),
        ]:
            assert attrs[name].string_value == expected
        span_attrs.append(attrs)
    warn_attrs, error_attrs, critical_attrs = span_attrs

    # https://opentelemetry.io/docs/specs/otel/logs/data-model/#field-severitynumber
    assert warn_attrs["logfire.level_num"].int_value in range(13, 17)
    assert error_attrs["logfire.level_num"].int_value in range(17, 21)
    assert critical_attrs["logfire.level_num"].int_value in range(21, 25)

    assert warn_attrs["logfire.msg"].string_value == "Warning message"
    assert error_attrs["logfire.msg"].string_value == "Error message"
    assert critical_attrs["logfire.msg"].string_value == "Critical message"

    assert warn_attrs["logfire.msg_template"].string_value == "Warning message"
    assert error_attrs["logfire.msg_template"].string_value == "%s message"
    assert critical_attrs["logfire.msg_template"].string_value == "%s %s"

    assert "gandharva.testing.is_critical" not in warn_attrs
    assert "gandharva.testing.is_critical" not in error_attrs
    assert critical_attrs["gandharva.testing.is_critical"].bool_value

    warn_span, error_span, critical_span = spans["logfire.stdlib.logging"]
    assert not warn_span.events
    assert not critical_span.events
    [event] = error_span.events
    attrs = {x.key: x.value for x in event.attributes}
    assert attrs["exception.type"].string_value == "RuntimeError"
    assert attrs["exception.message"].string_value == "Test message"


@contextlib.contextmanager
def _daemon_server(app: fastapi.FastAPI, port: int) -> Generator[None]:
    server = uvicorn.Server(uvicorn.Config(app, port=port))
    thread = threading.Thread(
        target=asyncio.run,
        args=(server.serve(),),
        daemon=True,
    )
    thread.start()
    try:
        for _ in range(600):
            if server.started:
                break
            time.sleep(.1)
        else:
            pytest.exit("Server startup timeout", returncode=1)
        yield
    finally:
        server.should_exit = True
        thread.join(timeout=60)
        if thread.is_alive():
            pytest.exit("Server shutdown timeout", returncode=1)


def _raise_runtime_error() -> NoReturn:
    message = "Test message"
    raise RuntimeError(message)


def _submit(
    self: forwarding.OTLPForwardingManager,
    request: forwarding.ForwardingRequest,
) -> forwarding.ForwardingAdmissionResult:
    del self, request
    return forwarding.ForwardingAdmissionResult("success", message=None)


_logger = logging.getLogger("_gandharva")
