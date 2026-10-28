"""The option schema: the single source of truth for every generator.

An :class:`OptionSpec` describes one user-facing option exactly once; the
argparse subparser (``argparse_builder``) AND the interactive prompter
(``prompter``) are both generated from the ordered :class:`OptionSpec` list on a
:class:`GeneratorSpec`, so flags and prompts cannot drift.

``__post_init__`` on both dataclasses performs RUNTIME structural validation of
the spec's own consistency (not value validation of a user's input — that lives
in the frozen ``*Config.__post_init__`` methods). A malformed spec is a
programming error, so it raises at import time.

All PEP 604 unions (``X | None``) and builtin generic subscriptions
(``tuple[str, ...]``) are kept strictly in ANNOTATION position so the module
stays valid on the declared Python 3.8 floor; runtime checks use runtime-safe
forms (``isinstance(x, bool)``, ``isinstance(x, tuple)``).
"""
from __future__ import annotations

import enum
from argparse import Namespace
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


class OptionType(enum.Enum):
    """The value kinds the schema supports (the complete set for this CLI)."""

    INT = "int"        # argparse type=int
    FLOAT = "float"    # argparse type=float
    STR = "str"        # argparse type=str
    PATH = "path"      # argparse type=pathlib.Path
    BOOL = "bool"      # a boolean feature flag (see BoolStyle)
    CHOICE = "choice"  # a fixed set of string values


class BoolStyle(enum.Enum):
    """How a boolean option maps to argparse flags / prompt rendering."""

    # Paired flags: --stacking-lip (store_true) + --no-stacking-lip
    # (store_false) onto the same dest, with a parser-level default.
    PAIR = "pair"
    # Single negative flag disabling an on-by-default feature:
    # --no-magnets (store_false), default True.
    NEGATIVE_OFF = "negative_off"
    # Single positive flag enabling an off-by-default feature:
    # --connectors / --split-lip / --3mf / --3mf-paint / --color-band
    # (store_true), default False.
    POSITIVE_ON = "positive_on"


# Scalar value types (as opposed to BOOL / CHOICE).
_SCALAR_TYPES = (OptionType.INT, OptionType.FLOAT, OptionType.STR, OptionType.PATH)


@dataclass(frozen=True)
class OptionSpec:
    """One user-facing option. Defaults and help are lifted VERBATIM."""

    dest: str
    flag: str
    type: OptionType
    help: str
    default: Any = None
    choices: tuple[str, ...] | None = None
    bool_style: BoolStyle | None = None
    negative_flag: str | None = None
    prompt: bool = True
    # Interactive-walkthrough requiredness (optional). ``required=True`` marks a
    # scalar option (INT/FLOAT/STR/PATH) with ``default=None`` that the
    # walkthrough must NOT satisfy with empty input: it re-prompts until a value
    # is given, instead of falling back to the default. It is only coherent when
    # there is no sensible default (hence ``default=None`` is enforced; a
    # non-None default is contradictory and rejected). It composes with
    # ``prompt_when``: a required option whose gate is unmet is not prompted and
    # keeps its ``None`` default — requiredness applies ONLY when the prompt is
    # actually shown. BOOL always carries a concrete default and CHOICE a
    # non-None default, so neither may be required. This is DATA for the prompter
    # only; argparse is unaffected (non-interactive callers still pass the flag
    # or hit the generator's own precheck).
    required: bool = False
    # Interactive-prompt overrides (optional). ``prompt_label`` is the positive
    # feature name shown in a BOOL prompt (e.g. "Magnet pockets") so a negative
    # flag like --no-magnets is never asked as a double negative; ``prompt_help``
    # is a positive-sense description for the same prompt. Both only affect the
    # interactive walkthrough; argparse flags/help are unchanged.
    prompt_label: str | None = None
    prompt_help: str | None = None
    # Dependency gate for the interactive walkthrough (optional). A tuple of
    # (dest, value) conditions; the option is prompted only when EVERY named
    # earlier option already equals its value (e.g. a magnet sub-option gates
    # on ("magnets", True); the teardrop angle on both ("magnets", True) and
    # ("magnet_shape", "teardrop")). When a gate is unmet the walkthrough skips
    # the prompt and uses the schema default, so build_config still gets a
    # complete namespace. Does NOT affect argparse (all flags stay available
    # non-interactively).
    prompt_when: tuple[tuple[str, Any], ...] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.flag, str) or not self.flag.startswith("--"):
            raise ValueError(f"OptionSpec flag must start with '--': {self.flag!r}")
        if not isinstance(self.dest, str) or not self.dest:
            raise ValueError(f"OptionSpec dest must be a non-empty str: {self.dest!r}")

        for attr in ("prompt_label", "prompt_help"):
            value = getattr(self, attr)
            if value is not None and (not isinstance(value, str) or not value):
                raise ValueError(
                    f"OptionSpec {attr} must be a non-empty str or None: {value!r}"
                )
        if (self.prompt_label is not None or self.prompt_help is not None) \
                and self.type is not OptionType.BOOL:
            raise ValueError(
                f"OptionSpec {self.flag!r}: prompt_label/prompt_help apply only "
                f"to BOOL options"
            )

        if not isinstance(self.required, bool):
            raise ValueError(
                f"OptionSpec {self.flag!r}: required must be a bool, "
                f"got {self.required!r}"
            )
        if self.required:
            if self.type not in _SCALAR_TYPES:
                raise ValueError(
                    f"OptionSpec {self.flag!r}: required applies only to scalar "
                    f"options"
                )
            if self.default is not None:
                raise ValueError(
                    f"OptionSpec {self.flag!r}: a required option must have "
                    f"default=None"
                )

        if self.prompt_when is not None:
            if not isinstance(self.prompt_when, tuple) or not self.prompt_when:
                raise ValueError(
                    f"OptionSpec {self.flag!r}: prompt_when must be a non-empty "
                    f"tuple of (dest, value) conditions"
                )
            for cond in self.prompt_when:
                if (not isinstance(cond, tuple) or len(cond) != 2
                        or not isinstance(cond[0], str) or not cond[0]):
                    raise ValueError(
                        f"OptionSpec {self.flag!r}: each prompt_when condition "
                        f"must be a (dest, value) pair: {cond!r}"
                    )

        if self.type is OptionType.CHOICE:
            if not isinstance(self.choices, tuple) or not self.choices:
                raise ValueError(
                    f"CHOICE option {self.flag!r} requires a non-empty choices tuple"
                )
            if self.default is None:
                raise ValueError(
                    f"CHOICE option {self.flag!r} requires a non-None default"
                )
            if self.default not in self.choices:
                raise ValueError(
                    f"CHOICE option {self.flag!r} default {self.default!r} "
                    f"not in choices {self.choices!r}"
                )
            if self.bool_style is not None or self.negative_flag is not None:
                raise ValueError(
                    f"CHOICE option {self.flag!r} must not set bool_style/negative_flag"
                )
        elif self.type is OptionType.BOOL:
            if self.choices is not None:
                raise ValueError(f"BOOL option {self.flag!r} must not set choices")
            if self.bool_style is None:
                raise ValueError(f"BOOL option {self.flag!r} requires a bool_style")
            if not isinstance(self.default, bool):
                raise ValueError(
                    f"BOOL option {self.flag!r} default must be a bool, "
                    f"got {self.default!r}"
                )
            if self.bool_style is BoolStyle.PAIR:
                if self.negative_flag is None:
                    raise ValueError(
                        f"PAIR option {self.flag!r} requires a negative_flag"
                    )
            elif self.negative_flag is not None:
                raise ValueError(
                    f"BOOL option {self.flag!r} with style {self.bool_style} "
                    f"must not set negative_flag"
                )
        elif self.type in _SCALAR_TYPES:
            if self.choices is not None:
                raise ValueError(
                    f"option {self.flag!r} of type {self.type} must not set choices"
                )
            if self.bool_style is not None or self.negative_flag is not None:
                raise ValueError(
                    f"option {self.flag!r} of type {self.type} "
                    f"must not set bool_style/negative_flag"
                )
        else:  # pragma: no cover - OptionType is a closed enum
            raise ValueError(f"unknown OptionType {self.type!r}")


@dataclass(frozen=True)
class GeneratorSpec:
    """A registered generator: name + ordered options + bound builders."""

    name: str
    help: str
    options: tuple[OptionSpec, ...]
    build_config: Callable[[Namespace], Any]
    build_and_export: Callable[[Any, Namespace, Any], "list[Path]"]
    summary: Callable[[Any, "list[Path]"], str]
    precheck: Callable[[Namespace], "str | None"] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.isidentifier():
            raise ValueError(
                f"GeneratorSpec name must be a non-empty identifier: {self.name!r}"
            )
        if not isinstance(self.options, tuple) or not self.options:
            raise ValueError(
                f"GeneratorSpec {self.name!r} requires a non-empty options tuple"
            )
        seen = set()
        for opt in self.options:
            if opt.dest in seen:
                raise ValueError(
                    f"GeneratorSpec {self.name!r} has duplicate dest {opt.dest!r}"
                )
            # A prompt_when gate may only reference options that appear EARLIER,
            # so the controlling answer is already in the namespace when the
            # walkthrough evaluates the gate.
            if opt.prompt_when is not None:
                for gate_dest, _ in opt.prompt_when:
                    if gate_dest not in seen:
                        raise ValueError(
                            f"GeneratorSpec {self.name!r}: option {opt.flag!r} "
                            f"gates on {gate_dest!r}, which must appear earlier "
                            f"in the options list"
                        )
            seen.add(opt.dest)
