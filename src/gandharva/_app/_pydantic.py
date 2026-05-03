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

__all__ = ["App"]

import functools
import inspect
import itertools
import keyword
import sys
from collections.abc import Callable, Mapping, Sequence
from typing import (
    TYPE_CHECKING,
    Annotated,
    ClassVar,
    Literal,
    cast,
    get_origin,
)

import pydantic.alias_generators
import pydantic_settings
import rich.markdown
import rich_argparse
from pydantic._internal import _config  # noqa: PLC2701
from pydantic.fields import FieldInfo
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource
from typing_extensions import Any, Self, Unpack, override
from typing_inspection import introspection

import gandharva as gd
from gandharva import _convert

from . import _base

if TYPE_CHECKING:
    from argparse import _FormatterClass  # pyright: ignore[reportPrivateUsage]

if sys.version_info >= (3, 14):
    import annotationlib

    def _safe_get_annotations(obj: object) -> dict[str, Any]:
        return annotationlib.get_annotations(
            obj,
            format=annotationlib.Format.FORWARDREF,
        )
else:
    def _safe_get_annotations(obj: object) -> dict[str, Any]:
        return getattr(obj, "__annotations__", {})


class _CliAppBaseModel(pydantic.BaseModel):
    json_: Annotated[
        pydantic_settings.CliToggleFlag[bool],
        gd.Field(alias="json", description="Output raw JSON"),
    ] = False


class App(_base.App):
    model_config = pydantic_settings.SettingsConfigDict(
        nested_model_default_partial_update=True,
        cli_hide_none_type=True,
        cli_avoid_json=True,
        cli_enforce_required=True,
        cli_implicit_flags=True,
        cli_kebab_case=True,
    )

    @classmethod
    def cli_config_files(cls, settings_cls: type[BaseSettings]) -> Sequence[
        pydantic_settings.JsonConfigSettingsSource
            | pydantic_settings.TomlConfigSettingsSource
            | pydantic_settings.YamlConfigSettingsSource,
    ]:
        del settings_cls
        return ()

    @classmethod
    def cli_env_settings(cls) -> bool:
        return False

    @classmethod
    def cli_formatter_class(cls) -> "_FormatterClass":
        return _MarkdownHelpFormatter

    @classmethod
    def to_cli(cls) -> type[BaseSettings]:
        def cli_cmd(self: _CliAppBaseModel) -> None:
            cls._pydantic_cli_cmd(self)

        return pydantic.create_model(
            cls.__name__,
            __config__=cls.model_config,
            __doc__=cls.__doc__,
            __base__=_CliAppBaseSettings,
            __validators__={
                "cli_cmd": cli_cmd,
                "cli_extra_sources": cls._pydantic_cli_extra_sources,
            },
            __module__=cls.__module__,
            __qualname__=cls.__qualname__,
            **cls._pydantic_fields_for_validation(cli=True),
        )

    @classmethod
    def to_pydantic(cls) -> type[pydantic.BaseModel]:
        return pydantic.create_model(
            cls.__name__,
            __config__=cls.model_config,
            __doc__=cls.__doc__,
            __module__=cls.__module__,
            __qualname__=cls.__qualname__,
            **cls._pydantic_fields_for_validation(),
        )

    @classmethod
    def to_subcommand(cls) -> type[pydantic.BaseModel]:
        def cli_cmd(self: _CliAppBaseModel) -> None:
            cls._pydantic_cli_cmd(self)

        return pydantic.create_model(
            cls.__name__,
            __config__=cls.model_config,
            __doc__=cls.__doc__,
            # Subcommands should inherit from BaseModel, see
            # https://pydantic.dev/docs/validation/latest/concepts/pydantic_settings/#parsing-environment-variable-values
            __base__=_CliAppBaseModel,
            __validators__={"cli_cmd": cli_cmd},
            __module__=cls.__module__,
            __qualname__=cls.__qualname__,
            **cls._pydantic_fields_for_validation(cli=True),
        )

    @classmethod
    def from_pydantic(
        cls,
        model: pydantic.BaseModel,
        run_mode: Literal["api", "cli", "gui"],
    ) -> Self:
        self = cls(run_mode)
        fields = cls._pydantic_fields_for_main()
        for k, v in model:
            if info := fields.get(k):
                setattr(self, k, _convert.from_pydantic_field(v, info))
        return self

    def __init_subclass__(
        cls,
        **kwargs: Unpack[pydantic_settings.SettingsConfigDict],
    ) -> None:
        for attr, parent in (
            ("__attrs_attrs__", "@attrs.define"),
            ("__dataclass_fields__", "@dataclasses.dataclass"),
            ("__pydantic_fields__", "pydantic.BaseModel"),
            ("__dataclass_transform__", "@typing.dataclass_transform"),
        ):
            if hasattr(cls, attr):
                message = f"Gandharva is incompatible with {parent} classes"
                raise gd.ApplicationBuilderError(message)

        config_wrapper = _config.ConfigWrapper.for_model(
            tuple(filter(App.__subclasscheck__, reversed(cls.__bases__))),
            dict(vars(cls)),
            cls.__annotations__,
            dict(kwargs),
        )
        cls.model_config = cast(
            "pydantic_settings.SettingsConfigDict",
            config_wrapper.config_dict,
        )

        if "children" not in vars(cls):
            cls.children = []

        super().__init_subclass__()

    @classmethod
    def _pydantic_cli_cmd(cls, model: _CliAppBaseModel) -> None:
        if cls.children and (
            child := pydantic_settings.get_subcommand(model, is_required=False)
        ):
            if model.json_ and isinstance(child, _CliAppBaseModel):
                child.json_ = True
            pydantic_settings.CliApp.run_subcommand(model)
            return
        self = cls.from_pydantic(model, run_mode="cli")
        result = self.main()
        _convert.to_cli(result, json=model.json_)

    @classmethod
    def _pydantic_cli_extra_sources(
        cls,
        settings_cls: type[BaseSettings],
        env_settings: PydanticBaseSettingsSource,
    ) -> Sequence[PydanticBaseSettingsSource]:
        sources: list[PydanticBaseSettingsSource] = [
            pydantic_settings.CliSettingsSource(
                settings_cls,
                formatter_class=cls.cli_formatter_class(),
            ),
        ]
        if cls.cli_env_settings():
            sources.append(env_settings)
        sources += cls.cli_config_files(settings_cls)
        return sources

    @classmethod
    def _pydantic_field_info(
        cls,
        k: str,
        v: object,
        metadata: list[Any],
    ) -> FieldInfo:
        obj = get_origin(v) or v
        if isinstance(obj, type) and issubclass(obj, gd.Gandharva):
            message = (
                "Nesting Gandharva classes is unsupported. If you want "
                f"nested data structure, declare the field {k!r} as "
                "pydantic.BaseModel or pydantic.dataclasses.dataclass. "
                "If you want sub-applications, use @Gandharva.register."
            )
            raise gd.ApplicationBuilderError(message)
        ann = cast("type", Annotated[(v, *metadata)] if metadata else v)
        try:
            default = getattr(cls, k)
        except AttributeError:
            return FieldInfo.from_annotation(ann)
        return FieldInfo.from_annotated_attribute(ann, default)

    @classmethod
    @functools.cache
    def _pydantic_fields_for_main(cls) -> Mapping[str, FieldInfo]:
        fields: dict[str, FieldInfo] = {}
        mro = cls.__mro__
        for base in reversed(mro[:mro.index(gd.Gandharva)]):
            if issubclass(base, gd.Gandharva):
                for k, v in inspect.get_annotations(
                    base,
                    eval_str=True,
                ).items():
                    ann = introspection.inspect_annotation(
                        v,
                        annotation_source=introspection.AnnotationSource.CLASS,
                        unpack_type_aliases="eager",
                    )
                    if not (
                        k.startswith("_")
                        or k in _reserved()
                        or hasattr(gd.Gandharva, k)
                        or ann.qualifiers
                    ):
                        fields[k] = cls._pydantic_field_info(
                            k,
                            ann.type,
                            ann.metadata,
                        )
        return fields

    @classmethod
    def _pydantic_fields_for_validation(
        cls,
        *,
        cli: bool = False,
    ) -> dict[str, Any]:
        if inspect.isabstract(cls):
            message = (
                f"Can't build application while {cls} is abstract. "
                "Please implement the main() method."
            )
            raise gd.ApplicationBuilderError(message)
        fields: dict[str, tuple[Any, FieldInfo]] = {}
        for k, v in cls._pydantic_fields_for_main().items():
            field = _convert.to_pydantic_field(v)
            ann = field.rebuild_annotation()
            if cli and field.is_required():
                if cls.children:
                    message = (
                        "Subcommands and mandatory arguments are mutually "
                        "exclusive in a CLI application. You can still run "
                        "this application in GUI/API mode, or move the "
                        "mandatory arguments into another subcommand."
                    )
                    raise gd.ApplicationBuilderError(message)
                ann = pydantic_settings.CliPositionalArg[ann]
            fields[k] = ann, gd.Field(**field.asdict()["attributes"])
        if cli:
            for child in cls.children:
                alias = child.app_normalized_name()
                name = _base.normalize(alias)
                name = pydantic.alias_generators.to_snake(name)
                if keyword.iskeyword(name):
                    name += "_"
                if name in fields:
                    message = (
                        f"Subcommand {name=!r} conflicts with an existing "
                        "argument or subcommand"
                    )
                    raise gd.ApplicationBuilderError(message)
                fields[name] = (
                    pydantic_settings.CliSubCommand[child.to_subcommand()],
                    gd.Field(alias=alias, description=child.app_summary()),
                )
        return fields


class _MarkdownHelpFormatter(rich_argparse.RichHelpFormatter):
    @override
    def add_text(self, text: rich.console.RenderableType | None) -> None:
        if not hasattr(self, "_description_added"):
            self._description_added = True
            if isinstance(text, str):
                text = rich.markdown.Markdown(inspect.cleandoc(text))
        return super().add_text(text)


class _CliAppBaseSettings(_CliAppBaseModel, BaseSettings):
    cli_extra_sources: ClassVar[
        Callable[
            [type[BaseSettings], PydanticBaseSettingsSource],
            Sequence[PydanticBaseSettingsSource],
        ]
    ]

    @classmethod
    @override
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            *cls.cli_extra_sources(settings_cls, env_settings),
        )


@functools.lru_cache(maxsize=1)
def _reserved() -> frozenset[str]:
    return frozenset(
        itertools.chain.from_iterable(
            map(_safe_get_annotations, gd.Gandharva.__mro__),
        ),
    )
