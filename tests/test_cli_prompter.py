"""Interactive prompter tests driven by scripted/mocked answers."""
import pytest

import bingrid.cli.prompter as prompter
from bingrid.config import BinConfig, GridConfig


def _script(monkeypatch, text_answers):
    """Make the prompter read scripted answers for scalar options.

    ``text_answers`` maps the option dest -> raw string the user "typed"
    ('' means accept the default). CHOICE and BOOL accept the default.
    """
    texts = dict(text_answers)

    def fake_text(label, default_display):
        # label is the prettified flag; map back is awkward, so pop in order.
        raise AssertionError("use dest-keyed scripting via _walk instead")

    return texts


def _walk(monkeypatch, spec, text_answers, choice_answers=None, bool_answers=None):
    choice_answers = choice_answers or {}
    bool_answers = bool_answers or {}

    # Drive by intercepting at the per-option level: patch the wrappers to read
    # from dicts keyed by the prettified label.
    pretty = {o.dest: prompter._pretty_name(o.flag) for o in spec.options}
    by_label_text = {pretty[d]: v for d, v in text_answers.items()}
    by_label_choice = {pretty[d]: v for d, v in choice_answers.items()}
    by_label_bool = {pretty[d]: v for d, v in bool_answers.items()}

    monkeypatch.setattr(
        prompter, "_ask_text",
        lambda label, default_display: by_label_text.get(label, ""),
    )
    monkeypatch.setattr(
        prompter, "_ask_choice",
        lambda label, choices, default: by_label_choice.get(label, default),
    )
    monkeypatch.setattr(
        prompter, "_ask_bool",
        lambda label, default: by_label_bool.get(label, default),
    )
    return prompter.walk_options(spec)


def test_walk_bin_all_defaults_builds_default_config(monkeypatch):
    import bingrid.cli.generators.bin as bin_

    ns = _walk(monkeypatch, bin_.SPEC, {})
    cfg = bin_.build_config(ns)
    assert cfg == BinConfig()


def test_walk_bin_scripted_values(monkeypatch):
    import bingrid.cli.generators.bin as bin_

    ns = _walk(
        monkeypatch, bin_.SPEC,
        text_answers={"x": "2", "y": "1", "units": "6"},
    )
    cfg = bin_.build_config(ns)
    assert (cfg.grid_x, cfg.grid_y, cfg.height_units) == (2, 1, 6)


def test_walk_bin_empty_keeps_none_defaults(monkeypatch):
    import bingrid.cli.generators.bin as bin_

    ns = _walk(monkeypatch, bin_.SPEC, text_answers={})
    assert ns.lip_wall is None
    assert ns.color_band_start is None
    assert ns.name is None


def test_walk_grid_all_defaults_builds_default_config(monkeypatch):
    import bingrid.cli.generators.grid as grid

    ns = _walk(monkeypatch, grid.SPEC, {})
    cfg = grid.build_config(ns)
    assert cfg == GridConfig()


def test_walk_grid_empty_keeps_none_height(monkeypatch):
    import bingrid.cli.generators.grid as grid

    ns = _walk(monkeypatch, grid.SPEC, text_answers={})
    assert ns.height is None
    assert ns.name is None


def test_walk_grid_choice_and_bool(monkeypatch):
    import bingrid.cli.generators.grid as grid

    ns = _walk(
        monkeypatch, grid.SPEC,
        text_answers={},
        choice_answers={"style": "taper"},
        bool_answers={"magnets": False, "connectors": True},
    )
    cfg = grid.build_config(ns)
    assert cfg.opening_style == "taper"
    assert cfg.magnet.enabled is False
    assert cfg.connector.enabled is True


def test_walk_path_empty_keeps_default_path(monkeypatch):
    import bingrid.cli.generators.bin as bin_

    ns = _walk(monkeypatch, bin_.SPEC, text_answers={})
    # Empty input short-circuits to the schema default Path(".output"),
    # NOT Path("") / Path(".").
    from pathlib import Path

    assert ns.output_dir == Path(".output")


def test_walk_path_nonempty_converts(monkeypatch):
    import bingrid.cli.generators.bin as bin_
    from pathlib import Path

    ns = _walk(monkeypatch, bin_.SPEC, text_answers={"output_dir": "/tmp/xyz"})
    assert ns.output_dir == Path("/tmp/xyz")


def test_select_item_returns_choice(monkeypatch):
    import bingrid.cli.generators  # noqa: F401
    from bingrid.cli.registry import REGISTRY

    seen = {}

    def fake_radiolist_dialog(**kwargs):
        seen["values"] = kwargs["values"]

        class _R:
            def run(self_inner):
                return "bin"

        return _R()

    monkeypatch.setattr(
        "prompt_toolkit.shortcuts.radiolist_dialog", fake_radiolist_dialog
    )
    # Silence rich panel output.
    monkeypatch.setattr(prompter, "_console", lambda: _NullConsole())

    name = prompter.select_item(REGISTRY.specs())
    assert name == "bin"
    listed = [v[0] for v in seen["values"]]
    assert listed == REGISTRY.names()


class _NullConsole:
    def print(self, *a, **k):
        pass
