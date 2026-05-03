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

"""Gandharva CLI/GUI runner.

If you want to run Gandharva as RESTful API, please use an ASGI server,
e.g. `uvicorn --factory module_name:AppName`
"""

__all__ = ["run"]

import importlib
import sys
from typing import Annotated

import panel as pn
import pydantic
import pydantic_settings
from typing_extensions import Any, override

import gandharva as gd

_WEBSOCKET_ORIGIN_REFERENCE = (
    "https://docs.bokeh.org/en/latest/docs/reference/server/util.html#bokeh.server.util.create_hosts_allowlist"
)


def run(app: type["gd.Gandharva"]) -> None:
    def cli_cmd(self: _GUI) -> None:
        self.serve(app.to_panels())

    if doc := __doc__:
        module_name = app.__module__
        if module_name != "__main__":
            try:
                module = importlib.import_module(module_name)
            except ImportError:
                pass
            else:
                app_name = app.__qualname__
                if getattr(module, app_name, None) is app:
                    doc = doc.replace(
                        "module_name:AppName",
                        f"{module_name}:{app_name}",
                    )

    gui = pydantic.create_model(
        "GUI",
        __config__=gd.Gandharva.model_config,
        __doc__="Gandharva GUI runner",
        __base__=_GUI,
        __validators__={"cli_cmd": cli_cmd},
    )
    runner = pydantic.create_model(
        "Runner",
        __config__=gd.Gandharva.model_config,
        __doc__=doc,
        __base__=_Runner,
        cli=Annotated[
            pydantic_settings.CliSubCommand[app.to_cli()],
            gd.Field(description="Run this application as CLI"),
        ],
        gui=Annotated[
            pydantic_settings.CliSubCommand[gui],
            gd.Field(description="Run this application as GUI"),
        ],
    )
    pydantic_settings.CliApp.run(
        runner,
        cli_args=["--help"] if len(sys.argv) <= 1 else None,
        cli_settings_source=pydantic_settings.CliSettingsSource(
            runner,
            formatter_class=app.cli_formatter_class(),
        ),
    )


class _GUI(pydantic_settings.BaseSettings):
    port: Annotated[
        pydantic.NonNegativeInt,
        gd.Field(le=65535, description="Port to listen on"),
    ] = 0
    address: Annotated[
        str | None,
        gd.Field(description="Address to listen on"),
    ] = None
    websocket_origin: Annotated[
        list[str],
        gd.Field(description=f"See {_WEBSOCKET_ORIGIN_REFERENCE}"),
    ] = []
    show: Annotated[
        pydantic_settings.CliToggleFlag[bool],
        gd.Field(description="Don't open in browser automatically"),
    ] = True
    verbose: Annotated[
        pydantic_settings.CliToggleFlag[bool],
        gd.Field(description="Don't print the address and port"),
    ] = True
    ico_path: Annotated[
        str,
        gd.Field(description="Local path to favicon file", min_length=1),
    ] = str(pn.io.resources.DIST_DIR / "images/favicon.ico")
    session_token_expiration: Annotated[
        pydantic.PositiveInt,
        gd.Field(description="Duration in seconds before a session expires"),
    ] = 300

    def serve(self, panels: dict[str, Any]) -> None:
        pn.serve(  # pyright: ignore[reportUnknownMemberType]
            panels,
            self.port,
            self.address,
            self.websocket_origin,
            show=self.show,
            verbose=self.verbose,
            use_index=False,
            ico_path=self.ico_path,
            session_token_expiration=self.session_token_expiration,
        )


class _Runner(pydantic_settings.BaseSettings):
    def cli_cmd(self) -> None:
        pydantic_settings.CliApp.run_subcommand(self)

    @classmethod
    @override
    def settings_customise_sources(
        cls,
        settings_cls: type[pydantic_settings.BaseSettings],
        init_settings: pydantic_settings.PydanticBaseSettingsSource,
        env_settings: pydantic_settings.PydanticBaseSettingsSource,
        dotenv_settings: pydantic_settings.PydanticBaseSettingsSource,
        file_secret_settings: pydantic_settings.PydanticBaseSettingsSource,
    ) -> tuple[pydantic_settings.PydanticBaseSettingsSource, ...]:
        return ()
