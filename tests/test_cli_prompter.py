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
    # from dicts keyed by the label each wrapper actually receives. Scalars and
    # choices get the prettified FLAG; booleans get the positive dest-based
    # label (so --no-magnets prompts "Magnet pockets", not "no magnets").
    pretty = {o.dest: prompter._pretty_name(o.flag) for o in spec.options}
    bool_label = {o.dest: prompter._bool_label(o) for o in spec.options}
    by_label_text = {pretty[d]: v for d, v in text_answers.items()}
    by_label_choice = {pretty[d]: v for d, v in choice_answers.items()}
    by_label_bool = {bool_label[d]: v for d, v in bool_answers.items()}

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

    printed = []

    # The inline menu lists each item via the console, then reads one line.
    # "bin" is the 2nd registered item; type its number.
    bin_index = REGISTRY.names().index("bin") + 1

    class _RecordingConsole:
        def print(self, *a, **k):
            printed.extend(str(x) for x in a)

    monkeypatch.setattr(prompter, "_console", lambda: _RecordingConsole())
    monkeypatch.setattr(prompter, "_read_line", lambda *a, **k: str(bin_index))

    name = prompter.select_item(REGISTRY.specs())
    assert name == "bin"
    # Every registered item name is listed in the inline menu.
    for item in REGISTRY.names():
        assert any(item in line for line in printed)


def test_select_item_empty_accepts_first(monkeypatch):
    import bingrid.cli.generators  # noqa: F401
    from bingrid.cli.registry import REGISTRY

    monkeypatch.setattr(prompter, "_console", lambda: _NullConsole())
    monkeypatch.setattr(prompter, "_read_line", lambda *a, **k: "")

    name = prompter.select_item(REGISTRY.specs())
    assert name == REGISTRY.names()[0]


def test_ask_choice_numbered_selection(monkeypatch):
    monkeypatch.setattr(prompter, "_read_line", lambda *a, **k: "2")
    assert prompter._ask_choice("style", ("socket", "taper"), "socket") == "taper"


def test_ask_choice_empty_keeps_default(monkeypatch):
    monkeypatch.setattr(prompter, "_read_line", lambda *a, **k: "")
    assert prompter._ask_choice("style", ("socket", "taper"), "socket") == "socket"


def test_ask_choice_reprompts_on_bad_input(monkeypatch):
    answers = iter(["9", "x", "1"])
    monkeypatch.setattr(prompter, "_read_line", lambda *a, **k: next(answers))
    assert prompter._ask_choice("style", ("socket", "taper"), "taper") == "socket"


def test_bool_label_is_positive_feature_from_schema():
    import bingrid.cli.generators.grid as grid
    import bingrid.cli.generators.bin as bin_

    labels = {o.dest: prompter._bool_label(o) for o in grid.SPEC.options
              if o.type.name == "BOOL"}
    # The negative flag --no-magnets prompts the POSITIVE feature, never
    # "no magnets".
    assert labels["magnets"] == "Magnet pockets"
    assert labels["connectors"] == "Dovetail connectors"

    bin_labels = {o.dest: prompter._bool_label(o) for o in bin_.SPEC.options
                  if o.type.name == "BOOL"}
    assert bin_labels["stacking_lip"] == "Stacking lip"


def test_bool_label_falls_back_to_titlecased_dest():
    from bingrid.cli.schema import BoolStyle, OptionSpec, OptionType

    # No prompt_label set -> title-cased dest.
    opt = OptionSpec(
        "snug_fit", "--no-snug-fit", OptionType.BOOL, "disable snug fit",
        default=True, bool_style=BoolStyle.NEGATIVE_OFF,
    )
    assert prompter._bool_label(opt) == "Snug fit"


def test_bool_help_prefers_schema_prompt_help():
    import bingrid.cli.generators.grid as grid

    magnets = next(o for o in grid.SPEC.options if o.dest == "magnets")
    # grid sets an explicit positive prompt_help.
    assert prompter._bool_help(magnets) == "recess magnet pockets into the plate"


def test_bool_help_rephrases_negative_off_without_override():
    from bingrid.cli.schema import BoolStyle, OptionSpec, OptionType

    opt = OptionSpec(
        "magnets", "--no-magnets", OptionType.BOOL, "disable magnet pockets",
        default=True, bool_style=BoolStyle.NEGATIVE_OFF,
    )
    # No prompt_help -> disable-sense help flipped to include-sense.
    assert prompter._bool_help(opt) == "include magnet pockets"


def test_walk_negative_off_default_yes_declined(monkeypatch):
    import bingrid.cli.generators.grid as grid

    # "Magnet pockets" defaults yes (magnets dest default True); decline it.
    ns = _walk(
        monkeypatch, grid.SPEC,
        text_answers={},
        bool_answers={"magnets": False},
    )
    cfg = grid.build_config(ns)
    assert cfg.magnet.enabled is False


def test_ask_bool_yes_no_and_default(monkeypatch):
    monkeypatch.setattr(prompter, "_read_line", lambda *a, **k: "y")
    assert prompter._ask_bool("magnets", False) is True
    monkeypatch.setattr(prompter, "_read_line", lambda *a, **k: "n")
    assert prompter._ask_bool("magnets", True) is False
    monkeypatch.setattr(prompter, "_read_line", lambda *a, **k: "")
    assert prompter._ask_bool("magnets", True) is True


class _NullConsole:
    def print(self, *a, **k):
        pass
