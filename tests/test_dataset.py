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

"""Test reading and writing `xarray.Dataset`."""

import asyncio
import contextlib
import functools
import http.server
import pathlib
import socket
import tempfile
import threading
import time
from collections.abc import Callable, Generator
from typing import ClassVar

import fastapi.staticfiles
import numpy as np
import pandera.errors
import pandera.xarray as pa
import pydantic
import pydantic_settings
import pytest
import uvicorn
import xarray as xr
from fastapi.testclient import TestClient
from typing_extensions import Any, TypeVarTuple, Unpack, override

import gandharva as gd

_Ts = TypeVarTuple("_Ts")


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


def test_default_protection() -> None:
    """Remote clients should not be able to request local datasets."""
    with (
        TestClient(_ComplexReader()) as client,
        pytest.raises(ValueError, match="Invalid protocol"),
    ):
        client.post(
            "/",
            # Any local path is fine even if not existing
            json={"data": tempfile.gettempdir()},
        )


def test_lazy_loading_nc(server_port: int, tmp_path: pathlib.Path) -> None:
    """netCDF4 datasets should be loaded lazily."""
    # Prepare data
    store = str(tmp_path / "test_data.nc")
    xr.Dataset({"da": ("dim", [0j])}).to_netcdf(  # pyright: ignore[reportUnknownMemberType]
        store,
        format="NETCDF4",
        engine="netcdf4",
        auto_complex=True,
    )

    # Access via local path
    pydantic_settings.CliApp.run(_ComplexReader.to_cli(), cli_args=[store])

    # Access via HTTP
    # `#mode=bytes` is required, otherwise it will be treated as DAP2
    # Use starlette `FileResponse` which supports HTTP range request
    app = fastapi.staticfiles.StaticFiles(directory=tmp_path)
    server = uvicorn.Server(uvicorn.Config(app, port=server_port))
    with (
        _daemon_thread(asyncio.run, server.serve()),
        TestClient(_ComplexReader()) as client,
    ):
        try:
            _wait_for_startup(server)
            client.post(
                "/",
                json={"data": f"http://127.0.0.1:{server_port}/test_data.nc#mode=bytes"},
            ).raise_for_status()
        finally:
            server.should_exit = True


def test_lazy_loading_zarr(server_port: int, tmp_path: pathlib.Path) -> None:
    """Zarr datasets should be loaded lazily."""
    # Prepare data
    with TestClient(_ComplexWriter()) as client:
        response = client.post("/", json={"output_path": str(tmp_path)})
    response.raise_for_status()
    store = response.json()["data"]

    # Access via local path
    pydantic_settings.CliApp.run(_ComplexReader.to_cli(), cli_args=[store])

    # Access via HTTP
    # Zarr `consolidated=False` requires server-side directory listing,
    # so we use stdlib `SimpleHTTPRequestHandler` here
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler,
        directory=tmp_path,
    )
    with (
        http.server.HTTPServer(("127.0.0.1", server_port), handler) as server,
        _daemon_thread(server.serve_forever),
        TestClient(_ComplexReader()) as client,
    ):
        try:
            client.post(
                "/",
                json={"data": f"http://127.0.0.1:{server_port}/test_data.zarr"},
            ).raise_for_status()
        finally:
            server.shutdown()


def test_metadata(tmp_path: pathlib.Path) -> None:
    """Gandharva should write CF standard metadata by default."""
    cli = _MetadataWriter.to_cli()
    cli_args = [str(tmp_path)]

    # Test if the validator works as expected
    with pytest.raises(pandera.errors.SchemaError):
        pydantic_settings.CliApp.run(cli, cli_args)

    pydantic_settings.CliApp.run(cli, ["--title", "Test data", *cli_args])


class _Complex(pa.DatasetModel):
    class Config(gd.DatasetConfig):
        strict = True

    da: np.complex128 = pa.Field(nullable=True)


class _ComplexReader(gd.Gandharva):
    data: gd.Dataset[_Complex]

    @override
    def main(self) -> None:
        da = self.data.data_vars["da"]
        assert not da._in_memory  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]


class _ComplexWriter(gd.Gandharva):
    output_path: pydantic.DirectoryPath

    @override
    def main(self) -> str:
        return self.to_zarr(
            xr.Dataset({"da": ("dim", [0j])}),
            self.output_path / "test_data.zarr",
            model=_Complex,
        )


class _Metadata(pa.DatasetModel):
    class Config(Any):
        attrs: ClassVar[dict[str, Any]] = {
            "history": "^20.+",
            "source": "^gandharva/.+",
            "title": "Test data",
        }
        strict = True


class _MetadataWriter(gd.Gandharva):
    output_path: pydantic.DirectoryPath
    title: str = ""

    @override
    def main(self) -> None:
        self.to_netcdf(
            xr.Dataset(),
            self.output_path / "test_data.nc",
            model=_Metadata,
        )

    @override
    def dataset_title(self) -> str:
        return self.title


@contextlib.contextmanager
def _daemon_thread(
    target: Callable[[Unpack[_Ts]], object],
    *args: Unpack[_Ts],
) -> Generator[None]:
    thread = threading.Thread(target=target, args=args, daemon=True)
    thread.start()
    try:
        yield
    finally:
        thread.join(timeout=60)
        if thread.is_alive():
            pytest.exit("Server shutdown timeout", returncode=1)


def _wait_for_startup(server: uvicorn.Server) -> None:
    for _ in range(600):
        if server.started:
            break
        time.sleep(.1)
    else:
        pytest.exit("Server startup timeout", returncode=1)
