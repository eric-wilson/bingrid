"""Interactive layer: rich formatting + prompt_toolkit input.

Two entry points, both only ever called once the dispatcher has confirmed an
interactive (TTY, not --no-input) session:

- :func:`select_item` — arrow-select menu over the registered generators.
- :func:`walk_options` — guided per-option walkthrough producing a Namespace.

All reads go through the thin wrappers :func:`_ask_text` / :func:`_ask_choice` /
:func:`_ask_bool`, which tests patch to script answers. Value-range validation
is NOT done here (owned by ``*Config.__post_init__``); the walkthrough only does
type conversion, re-prompting on a conversion failure.
"""
from __future__ import annotations

from argparse import Namespace
from pathlib import Path
from typing import Any

from .schema import BoolStyle, GeneratorSpec, OptionSpec, OptionType

_SCALAR_CONVERT = {
    OptionType.INT: int,
    OptionType.FLOAT: float,
    OptionType.STR: str,
    OptionType.PATH: Path,
}


# --- thin, patchable read seams --------------------------------------------

def _ask_text(label: str, default_display: str) -> str:
    """Prompt for a line of text. Returns the raw string ('' means accept default)."""
    from prompt_toolkit import prompt

    return prompt(f"{label} [{default_display}]: ")


def _ask_choice(label: str, choices: "tuple[str, ...]", default: str) -> str:
    """Arrow-select among ``choices`` with ``default`` pre-highlighted."""
    from prompt_toolkit.shortcuts import radiolist_dialog

    result = radiolist_dialog(
        title=label,
        text="Use arrow keys, Enter to confirm.",
        values=[(c, c) for c in choices],
        default=default,
    ).run()
    return default if result is None else result


def _ask_bool(label: str, default: bool) -> bool:
    """Yes/no prompt reflecting ``default``."""
    from prompt_toolkit.shortcuts import confirm

    return bool(confirm(label))


# --- rich helpers ----------------------------------------------------------

def _console():
    from rich.console import Console

    return Console()


def _pretty_name(flag: str) -> str:
    return flag.lstrip("-").replace("-", " ")


def _describe(console, spec: OptionSpec, default_display: str) -> None:
    from rich.text import Text

    text = Text()
    text.append(_pretty_name(spec.flag), style="bold cyan")
    text.append("\n")
    text.append(spec.help, style="dim")
    text.append(f"\n[default: {default_display}]", style="green")
    console.print(text)


# --- public API ------------------------------------------------------------

def select_item(specs: "list[GeneratorSpec]") -> str:
    """Arrow-select menu over ``specs``; returns the chosen generator name."""
    from prompt_toolkit.shortcuts import radiolist_dialog

    console = _console()
    from rich.panel import Panel

    console.print(Panel.fit("Pick an item to generate (\u2191/\u2193, Enter)"))

    names = [spec.name for spec in specs]
    result = radiolist_dialog(
        title="bingrid",
        text="Pick an item to generate.",
        values=[(spec.name, f"{spec.name} \u2014 {spec.help}") for spec in specs],
        default=names[0] if names else None,
    ).run()
    return names[0] if result is None else result


def walk_options(spec: GeneratorSpec) -> Namespace:
    """Guided per-option walkthrough; returns a Namespace with every dest set."""
    console = _console()
    ns = Namespace()
    for opt in spec.options:
        if not opt.prompt:
            setattr(ns, opt.dest, opt.default)
            continue
        setattr(ns, opt.dest, _prompt_one(console, opt))
    return ns


def _default_display(opt: OptionSpec) -> str:
    if opt.default is None:
        return "auto"
    return str(opt.default)


def _prompt_one(console, opt: OptionSpec) -> Any:
    if opt.type is OptionType.BOOL:
        _describe(console, opt, _default_display(opt))
        return _ask_bool(_pretty_name(opt.flag), bool(opt.default))

    if opt.type is OptionType.CHOICE:
        _describe(console, opt, _default_display(opt))
        return _ask_choice(_pretty_name(opt.flag), opt.choices, opt.default)

    # Scalar: INT / FLOAT / STR / PATH.
    convert = _SCALAR_CONVERT[opt.type]
    while True:
        _describe(console, opt, _default_display(opt))
        raw = _ask_text(_pretty_name(opt.flag), _default_display(opt))
        # EMPTY input short-circuits to the schema default BEFORE any type
        # conversion (so None/auto stays None and Path(".output") is kept).
        if raw == "":
            return opt.default
        try:
            return convert(raw)
        except (ValueError, TypeError) as exc:
            console.print(f"[red]invalid value: {exc}[/red]")
