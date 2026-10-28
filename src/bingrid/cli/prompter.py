"""Interactive layer: rich formatting + inline single-line input.

Two entry points, both only ever called once the dispatcher has confirmed an
interactive (TTY, not --no-input) session:

- :func:`select_item` — inline numbered menu over the registered generators.
- :func:`walk_options` — guided per-option walkthrough producing a Namespace.

Every prompt is a plain single-line read rendered in the normal terminal flow;
no full-screen/alternate-screen widgets. All reads go through the thin wrappers
:func:`_ask_text` / :func:`_ask_choice` / :func:`_ask_bool` (which in turn call
:func:`_read_line`), so tests patch them to script answers. Value-range
validation is NOT done here (owned by ``*Config.__post_init__``); the
walkthrough only does type conversion, re-prompting on a conversion failure.
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
#
# All interactive input is a plain single-line ``input()`` read in the NORMAL
# terminal flow. An earlier version used prompt_toolkit's dialog/full-screen
# widgets (radiolist_dialog, confirm); they switch to the alternate screen,
# which read as a jarring DOS-style GUI jumping in and out between the inline
# text prompts, so that dependency was dropped. A plain line read keeps every
# prompt inline, reads piped/non-TTY stdin without cursor-position-request
# warnings, and is trivial to script in tests. rich (below) renders the option
# descriptions, menu, and choice lists.


def _read_line(prompt_text: str) -> str:
    """Read one line of input, inline. Seam kept tiny so tests patch above it."""
    return input(prompt_text)


def _ask_text(label: str, default_display: str) -> str:
    """Prompt for a line of text. Returns the raw string ('' means accept default)."""
    return _read_line(f"{label} [{default_display}]: ")


def _ask_choice(label: str, choices: "tuple[str, ...]", default: str) -> str:
    """Inline numbered pick among ``choices``; empty input accepts ``default``.

    Rendered in the normal terminal flow (no alternate-screen dialog): the
    choices are listed with 1-based numbers, the default marked, and a single
    line is read. Empty input keeps the default; an out-of-range or non-numeric
    entry re-prompts.
    """
    options = list(choices)
    default_index = options.index(default) + 1 if default in options else 1
    lines = []
    for i, choice in enumerate(options, start=1):
        marker = " (default)" if choice == default else ""
        lines.append(f"  {i}) {choice}{marker}")
    menu = "\n".join(lines)
    while True:
        raw = _read_line(
            f"{label}:\n{menu}\nchoose [1-{len(options)}, "
            f"default {default_index}]: "
        ).strip()
        if raw == "":
            return default
        try:
            idx = int(raw)
        except ValueError:
            print(f"  invalid choice: {raw!r}")
            continue
        if 1 <= idx <= len(options):
            return options[idx - 1]
        print(f"  choice out of range: {idx}")


def _ask_bool(label: str, default: bool) -> bool:
    """Inline yes/no prompt reflecting ``default``; empty input keeps it."""
    suffix = "Y/n" if default else "y/N"
    while True:
        raw = _read_line(f"{label}? [{suffix}]: ").strip().lower()
        if raw == "":
            return default
        if raw in ("y", "yes"):
            return True
        if raw in ("n", "no"):
            return False
        print(f"  please answer y or n (got {raw!r})")


# --- rich helpers ----------------------------------------------------------

def _console():
    from rich.console import Console

    return Console()


def _pretty_name(flag: str) -> str:
    return flag.lstrip("-").replace("-", " ")


def _bool_label(opt: OptionSpec) -> str:
    """A POSITIVE feature label for a boolean prompt.

    The flag may be negative (``--no-magnets``), so we never prompt the
    double-negative "no magnets? [Y/n]". The clean label is DATA owned by the
    schema (``OptionSpec.prompt_label``): e.g. "Magnet pockets", "Stacking
    lip", "Dovetail connectors". When a spec omits it we fall back to a
    title-cased dest ("magnets" -> "Magnets").
    """
    if opt.prompt_label:
        return opt.prompt_label
    phrase = opt.dest.replace("_", " ").strip()
    if not phrase:
        return opt.dest
    return phrase[0].upper() + phrase[1:]


def _describe(console, spec: OptionSpec, default_display: str) -> None:
    from rich.text import Text

    text = Text()
    text.append(_pretty_name(spec.flag), style="bold cyan")
    text.append("\n")
    text.append(spec.help, style="dim")
    text.append(f"\n[default: {default_display}]", style="green")
    console.print(text)


def _describe_bool(console, opt: OptionSpec) -> None:
    """Describe a boolean option by its POSITIVE feature, resolved default.

    Avoids echoing a negative flag's "disable ..." help (which inverts the
    on/off sense) and shows the default as the resolved yes/no, not the raw
    dest boolean.
    """
    from rich.text import Text

    text = Text()
    text.append(_bool_label(opt), style="bold cyan")
    text.append("\n")
    text.append(_bool_help(opt), style="dim")
    text.append(
        f"\n[default: {'yes' if bool(opt.default) else 'no'}]", style="green"
    )
    console.print(text)


def _bool_help(opt: OptionSpec) -> str:
    """Positive-sense help for a boolean option.

    Prefers an explicit ``OptionSpec.prompt_help`` from the schema. Otherwise
    falls back to the argparse ``help``, rephrasing a NEGATIVE_OFF flag's
    disable-sense help ("disable magnet pockets" -> "include magnet pockets")
    so it matches the positive question. PAIR/POSITIVE_ON help already reads
    positively.
    """
    if opt.prompt_help:
        return opt.prompt_help
    if opt.bool_style is BoolStyle.NEGATIVE_OFF:
        stripped = opt.help.strip()
        low = stripped.lower()
        for verb in ("disable ", "omit "):
            if low.startswith(verb):
                return f"include {stripped[len(verb):]}"
    return opt.help


# --- public API ------------------------------------------------------------

def select_item(specs: "list[GeneratorSpec]") -> str:
    """Inline numbered menu over ``specs``; returns the chosen generator name.

    Rendered in the normal terminal flow (no alternate-screen dialog). Empty
    input accepts the first item; a non-numeric or out-of-range entry
    re-prompts.
    """
    console = _console()
    from rich.panel import Panel

    console.print(Panel.fit("Pick an item to generate"))

    names = [spec.name for spec in specs]
    for i, spec in enumerate(specs, start=1):
        console.print(f"  {i}) {spec.name} \u2014 {spec.help}")

    if not names:
        raise ValueError("no items registered")

    while True:
        raw = _read_line(f"choose [1-{len(names)}, default 1]: ").strip()
        if raw == "":
            return names[0]
        try:
            idx = int(raw)
        except ValueError:
            console.print(f"  invalid choice: {raw!r}")
            continue
        if 1 <= idx <= len(names):
            return names[idx - 1]
        console.print(f"  choice out of range: {idx}")


def walk_options(spec: GeneratorSpec) -> Namespace:
    """Guided per-option walkthrough; returns a Namespace with every dest set.

    Options are prompted in order. An option is SKIPPED (set to its schema
    default) when either ``prompt`` is False or its ``prompt_when`` dependency
    gate is unmet given the answers collected so far — so declining a feature
    (e.g. magnets off, connectors off) suppresses that feature's sub-questions
    instead of asking dead inputs. The returned namespace always has every
    dest set, so ``build_config`` sees a complete set of values.
    """
    console = _console()
    ns = Namespace()
    for opt in spec.options:
        if not opt.prompt or not _gate_satisfied(ns, opt):
            setattr(ns, opt.dest, opt.default)
            continue
        setattr(ns, opt.dest, _prompt_one(console, opt))
    return ns


def _gate_satisfied(ns: Namespace, opt: OptionSpec) -> bool:
    """True when ``opt``'s prompt_when gate holds against answers so far.

    An option with no gate is always prompted. A gate holds only when EVERY
    (dest, value) condition matches an already-collected answer; a referenced
    dest missing from the namespace fails closed (skip the prompt).
    """
    if opt.prompt_when is None:
        return True
    for gate_dest, expected in opt.prompt_when:
        if not hasattr(ns, gate_dest):
            return False
        if getattr(ns, gate_dest) != expected:
            return False
    return True


def _default_display(opt: OptionSpec) -> str:
    if opt.default is None:
        return "auto"
    return str(opt.default)


def _prompt_one(console, opt: OptionSpec) -> Any:
    if opt.type is OptionType.BOOL:
        _describe_bool(console, opt)
        return _ask_bool(_bool_label(opt), bool(opt.default))

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
