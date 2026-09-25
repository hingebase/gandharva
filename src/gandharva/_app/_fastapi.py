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

__all__ = ["App", "get_lock"]

import asyncio
import contextlib
import contextvars
import dataclasses
import functools
import io
import sys
import weakref
from collections.abc import (
    AsyncGenerator,
    Awaitable,
    Callable,
    Iterable,
    MutableMapping,
    Sequence,
)
from email.message import Message
from typing import Annotated, Literal, no_type_check

import anyio.lowlevel
import fastapi.middleware.cors
import matplotlib as mpl
import panel as pn
import starlette.exceptions
import starlette.types
from anyio.from_thread import threadlocals  # pyright: ignore[reportPrivateImportUsage]
from bokeh.resources import CDN, INLINE
from distributed.scheduler import RLock  # pyright: ignore[reportPrivateImportUsage]
from pydantic_core import Url
from typing_extensions import Any, NamedTuple, Self, final, overload, override

import gandharva as gd
from gandharva import _convert, _utils

from . import _pydantic

if sys.version_info >= (3, 12):
    import bs4
    import kiss_headers
    from bokeh.server.request import ServerRequest
    from panel.io import application, asgi

    class _PanelASGI(asgi.PanelASGI):
        @contextlib.asynccontextmanager
        async def lifespan(
            self,
            app: fastapi.FastAPI,  # Store a reference once we need it
        ) -> AsyncGenerator[None]:
            _lifespan(app)
            await self._ensure_started()
            try:
                yield
            finally:
                await self._panel_stop()
                await self.core.stop()

        def middleware_factory(self, app: starlette.types.ASGIApp) -> Callable[
            ["asgi.Scope", "asgi.Receive", starlette.types.Send],
            Awaitable[None],
        ]:
            async def middleware(
                scope: "asgi.Scope",
                receive: "asgi.Receive",
                send: starlette.types.Send,
            ) -> None:
                if (
                    "http" != scope["type"] != "websocket"
                    or not self.handles(scope)
                ):
                    await app(scope, receive, send)
                    return
                route = self._route_path(scope)
                if scope.get("method") == "HEAD" or {
                    route,
                    route.removesuffix("/"),
                }.isdisjoint(self.core.applications):
                    # We don't check if FastAPI can handle the request
                    # to `/favicon.ico` like
                    # `pn.io.fastapi.PanelDispatchMiddleware`.
                    # The returned Panel application is intended to be
                    # embedded as iframe, where the favicon is unused.
                    await self(scope, receive, send)
                    return
                try:
                    href = str(_href(scope))
                except Exception as e:  # ruff: ignore[blind-except]
                    await _unknown_href(e, send)
                    return
                try:
                    await app(scope, receive, send)
                except _convert.LetMiddlewareHandleThisError as e:
                    obj = e.obj
                else:
                    return
                ctx = contextvars.copy_context()
                ctx.run(_curdoc.set, obj)
                coro = self(scope, _unexpected_receive, _Send(send, href))
                await asyncio.create_task(coro, context=ctx)
            return middleware

        @override
        async def _check_method(
            self,
            request: ServerRequest,
            send: "asgi.Send",
            allowed: tuple[str, ...] | None = None,
        ) -> bool:
            if allowed is None:
                if _curdoc.get(None) is None:
                    allowed = ("GET", "HEAD")
                else:
                    allowed = ("GET", "POST")
            return await super()._check_method(request, send, allowed)

    @dataclasses.dataclass
    class _Send:
        send: starlette.types.Send
        href: str

        async def __call__(self, message: MutableMapping[str, Any]) -> None:
            match message:
                case {"type": "http.response.start"}:
                    self._previous = message
                    return
                case {"type": "http.response.body", "body": body}:
                    previous = self._previous
                case _:
                    _utils.unreachable()

            # This section takes ~1ms thus no need to run in thread
            headers: list[tuple[bytes, bytes]] = previous["headers"]
            header = _content_length_header(body)
            soup = bs4.BeautifulSoup(body, "lxml")
            [head] = soup.find_all("head")
            for base in head.find_all("base"):
                base.decompose()
            base = soup.new_tag("base", href=self.href)
            head.insert(0, base)
            message["body"] = body = soup.encode()
            headers[headers.index(header)] = _content_length_header(body)

            send = self.send
            await send(previous)
            await send(message)

    def _extract(
        all_headers: Iterable[tuple[bytes, bytes]],
    ) -> tuple[list[kiss_headers.Forwarded], list[bytes], list[bytes]]:
        forwarded: list[kiss_headers.Forwarded] = []
        x_forwarded_host: list[bytes] = []
        x_forwarded_proto: list[bytes] = []
        for name, value in all_headers:
            match name.lower():
                case b"forwarded":
                    match kiss_headers.get_polymorphic(
                        kiss_headers.parse_it(b"Forwarded: %b" % value),
                        kiss_headers.Forwarded,
                    ):
                        case list(headers):
                            forwarded += headers
                        case None:
                            _utils.unreachable()
                        case header:
                            forwarded.append(header)
                # Since the X-Forwarded-* headers are non-standard, it's
                # undefined whether they can include commas.
                # In consideration of performance, we omit the checks
                # for commas, and let the undefined behavior take place.
                case b"x-forwarded-host":
                    x_forwarded_host.append(value)
                case b"x-forwarded-proto":
                    x_forwarded_proto.append(value)
                case _:
                    pass
        return forwarded, x_forwarded_host, x_forwarded_proto

    def _forwarded(headers: Iterable[tuple[bytes, bytes]]) -> Url | None:
        # ASGI specification doesn't preserve the order of header names
        # while the order of header values does matter in RFC 7239,
        # making it impossible to parse mixed `Forwarded` and
        # `X-Forwarded-*`. Reference:
        # https://datatracker.ietf.org/doc/html/rfc7239#section-7.4
        forwarded, x_forwarded_host, x_forwarded_proto = _extract(headers)
        if len(x_forwarded_host) != len(x_forwarded_proto):
            raise starlette.exceptions.HTTPException(
                status_code=200,
                detail="Unpaired `X-Forwarded-*` headers",
            )
        if forwarded and x_forwarded_host:
            raise starlette.exceptions.HTTPException(
                status_code=200,
                detail="Cannot mix `Forwarded` and `X-Forwarded-*` headers",
            )
        for header in forwarded:
            # A proxy can omit `Forwarded: host=` if it doesn't rewrite
            # the `Host` header
            host = header.get("host")
            if host is not None:
                # Although a proxy can omit `Forwarded: proto=` if it
                # doesn't perform HTTPS decryption, we require the field
                # to be present here, otherwise it will be much more
                # difficult to retrieve the original scheme
                return Url.build(scheme=header.proto, host=header.host)  # pyright: ignore[reportArgumentType]
        for proto, h in zip(x_forwarded_proto, x_forwarded_host, strict=False):
            return Url.build(
                scheme=proto.decode("latin-1"),
                host=h.decode("latin-1"),
            )
        return None

    def _host(all_headers: Iterable[tuple[bytes, bytes]]) -> str | None:
        hosts: list[kiss_headers.Host] = []
        for name, value in all_headers:
            if name.lower() == b"host":
                match kiss_headers.get_polymorphic(
                    kiss_headers.parse_it(b"Host: %b" % value),
                    kiss_headers.Host,
                ):
                    case list(headers):
                        hosts += headers
                    case None:
                        _utils.unreachable()
                    case header:
                        hosts.append(header)
        match hosts:
            case [host]:
                return host.content
            case []:
                # It should be a 400 Bad Request for HTTP/1.1, see
                # https://datatracker.ietf.org/doc/html/rfc7230#section-5.4
                # We are just not ready for handling each HTTP version
                return None
            case _:
                raise starlette.exceptions.HTTPException(
                    status_code=400,
                    detail="Multiple `Host` headers found",
                )

    def _href(scope: "asgi.Scope") -> Url:
        # https://asgi.readthedocs.io/en/latest/specs/www.html#http-connection-scope
        headers = scope.get("headers", ())
        if forwarded := _forwarded(headers):
            return forwarded
        scheme = scope.get("scheme", "http")
        if host := _host(headers):
            return Url.build(scheme=scheme, host=host)
        # The "server" key is optional, but let it raise if missing
        # Users should migrate to another ASGI server that provides it
        host, port = scope["server"]
        return Url.build(scheme=scheme, host=host, port=port)


class _PanelTracker(NamedTuple):
    panels: list[str]
    prefix: list[str]


class App(_pydantic.App):
    fastapi_request: fastapi.Request

    @classmethod
    def fastapi_apiroute_params(cls) -> gd.typing.APIRouteParameters:
        return {
            "summary": cls.app_summary(),
            "description": cls.app_description(),
            "deprecated": hasattr(cls, "__deprecated__"),
        }

    @classmethod
    def fastapi_apirouter_params(
        cls,
        lifespan: starlette.types.Lifespan[Any],
    ) -> gd.typing.APIRouterParameters:
        return {"lifespan": lifespan}

    @classmethod
    def fastapi_app_params(
        cls,
        lifespan: starlette.types.Lifespan[fastapi.FastAPI],
        meta: Message,
    ) -> gd.typing.FastAPIParameters:
        kwargs: gd.typing.FastAPIParameters = {
            "lifespan": lifespan,
            "summary": meta.get("Summary"),
        }
        for key in "description", "version":
            if value := meta.get(key):
                kwargs[key] = value
        if title := cls.app_title(meta):
            kwargs["title"] = title
        if identifier := meta.get("License-Expression"):
            kwargs["license_info"] = {
                "name": "License",
                "identifier": identifier,
            }
        return kwargs

    @classmethod
    def fastapi_post_init(
        cls,
        router: fastapi.APIRouter | fastapi.FastAPI,
    ) -> None:
        pass

    @classmethod
    @final
    def to_router(
        cls,
        *,
        _tracker: _PanelTracker | None = None,
    ) -> fastapi.APIRouter:
        prefix = "/" + cls.app_normalized_name()
        kwargs: dict[str, Any] = dict(
            cls.fastapi_apirouter_params(_lifespan),
            prefix=prefix,
        )
        router = fastapi.APIRouter(**kwargs)
        if _tracker:
            _tracker.prefix.append(prefix)
            cls._fastapi_routes(router, _tracker)
            _tracker.prefix.pop()
        else:
            cls._fastapi_routes(router)
        return router

    @overload
    def __new__(
        cls,
        run_mode: None = ...,
        *,
        allow_origins: Sequence[str] = ...,
        allow_methods: Sequence[str] = ...,
    ) -> fastapi.FastAPI: ...
    @overload
    def __new__(cls, run_mode: Literal["api", "cli", "gui"]) -> Self: ...
    @final
    def __new__(  # pyright: ignore[reportInconsistentConstructor]
        cls,
        run_mode: Literal["api", "cli", "gui"] | None = None,
        *,
        allow_origins: Sequence[str] = ("*",),
        allow_methods: Sequence[str] = ("*",),
    ) -> fastapi.FastAPI | Self:
        if run_mode:
            return super().__new__(cls)
        meta = cls.app_distribution_metadata()
        if meta.get("Name", "gandharva") == "gandharva":
            meta = Message()
        asgi = None
        kwargs = cls.fastapi_app_params(
            lambda app: asgi.lifespan(app) if asgi else _lifespan(app),
            meta,
        )
        app = fastapi.FastAPI(**kwargs)
        if sys.version_info >= (3, 12):
            tracker = _PanelTracker([], [])
            cls._fastapi_routes(app, tracker)
            if panels := tracker.panels:
                apps = application.build_applications(  # pyright: ignore[reportUnknownMemberType]
                    dict.fromkeys(panels, _panel),
                )
                asgi = _PanelASGI(
                    apps,
                    extra_websocket_origins=allow_origins,
                    index_enabled=False,
                )
                app.add_middleware(asgi.middleware_factory)
        else:
            cls._fastapi_routes(app)
        if allow_origins and allow_methods:
            app.add_middleware(
                fastapi.middleware.cors.CORSMiddleware,
                allow_origins=allow_origins,
                allow_methods=allow_methods,
            )
        return app

    def _fastapi_main(self) -> object:
        with self.auto_plotting_backend():
            result = self.main()
            return _convert.to_response(result, self)
            # TODO(): #4

    @classmethod
    def _fastapi_routes(
        cls,
        router: fastapi.APIRouter | fastapi.FastAPI,
        tracker: _PanelTracker | None = None,
    ) -> None:
        responses: dict[int | str, dict[str, Any]] = {}
        kwargs: dict[str, Any] = dict(
            cls.fastapi_apiroute_params(),
            path="/",
            responses=responses,
            name=cls.__name__,
        )
        if leaf := _convert.to_response_model(
            f"__Response_{cls.__name__}",
            cls.main_return_annotation(),
            kwargs,
        ):
            if not tracker:
                message = (
                    "This application can only be converted to "
                    "`fastapi.FastAPI` since it relies on features unavailable"
                    " on `fastapi.APIRouter`."
                )
                raise gd.ApplicationBuilderError(message)
            tracker.panels.append("".join(tracker.prefix) or "/")

        # Remove the default `application/json` from OpenAPI
        if responses:
            kwargs["response_class"] = fastapi.Response

        model = cls.to_pydantic()
        if model.__pydantic_fields__:
            @no_type_check
            @router.post(**kwargs)
            def _(
                request: fastapi.Request,
                body: Annotated[model, fastapi.Body()],
            ) -> object:
                self = cls(run_mode="api")
                self.fastapi_request = request
                with self.from_pydantic(body):
                    return self._fastapi_main()
        else:
            @router.get(**kwargs)
            def _(request: fastapi.Request) -> object:
                self = cls(run_mode="api")
                self.fastapi_request = request
                return self._fastapi_main()

        if children := cls.children:
            if leaf:
                message = (
                    "Returning HoloViz objects from a parent application is "
                    "unsupported in API mode"
                )
                raise gd.ApplicationBuilderError(message)
            for child in children:
                router.include_router(child.to_router(_tracker=tracker))
        cls.fastapi_post_init(router)


def get_lock() -> RLock:
    token: anyio.lowlevel.EventLoopToken = threadlocals.current_token
    return _locks[token.native_token]


def _content_length_header(body: bytes) -> tuple[bytes, bytes]:
    return b"content-length", b"%d" % len(body)


def _lifespan(_: fastapi.FastAPI) -> contextlib.nullcontext[None]:
    mpl.use("agg")
    token = anyio.lowlevel.current_token().native_token
    if token not in _locks:
        _locks[token] = RLock()
    return _noop


def _panel() -> pn.viewable.Viewable:
    return _curdoc.get()


def _serialize(pane: pn.viewable.Viewable) -> bytes:
    with io.BytesIO() as f:
        pane.save(f, resources=INLINE if pn.config.inline else CDN)  # pyright: ignore[reportUnknownMemberType]
        return f.getvalue()


async def _unexpected_receive() -> dict[str, Any]:  # ruff: ignore[unused-async]
    _utils.unreachable()


@functools.singledispatch
async def _unknown_href(exc: Exception, send: starlette.types.Send) -> None:
    pane = _convert.gui_error_handler(exc)
    body = _serialize(pane)
    await send({
        "type": "http.response.start",
        "status": 200,
        "headers": [
            (b"content-type", b"text/html"),
            _content_length_header(body),
        ],
    })
    await send({"type": "http.response.body", "body": body})


@_unknown_href.register
async def _(
    exc: starlette.exceptions.HTTPException,
    send: starlette.types.Send,
) -> None:
    pane = pn.pane.Alert(exc.detail, alert_type="danger", margin=5)
    body = _serialize(pane)
    headers = [(b"content-type", b"text/html"), _content_length_header(body)]
    if extra_headers := exc.headers:
        for name, value in extra_headers:
            header = name.encode("latin-1"), value.encode("latin-1")
            headers.append(header)
    await send({
        "type": "http.response.start",
        "status": exc.status_code,
        "headers": headers,
    })
    await send({"type": "http.response.body", "body": body})


_curdoc = contextvars.ContextVar[pn.viewable.Viewable]("_curdoc")
_locks = weakref.WeakKeyDictionary[object, RLock]()
_noop = contextlib.nullcontext()
