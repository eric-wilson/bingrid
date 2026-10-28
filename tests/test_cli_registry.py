"""Schema/registry correctness tests."""
import pytest

from bingrid.cli.registry import Registry
from bingrid.cli.schema import (
    BoolStyle,
    GeneratorSpec,
    OptionSpec,
    OptionType,
)


def test_import_generators_registers_grid_bin_holder_battery():
    import bingrid.cli.generators  # noqa: F401
    from bingrid.cli.registry import REGISTRY

    assert REGISTRY.names() == ["grid", "bin", "holder", "battery"]


def test_reregistering_a_name_raises():
    import bingrid.cli.generators.grid as grid

    reg = Registry()
    reg.register(grid.SPEC)
    with pytest.raises(ValueError):
        reg.register(grid.SPEC)


# --- OptionSpec structural validation --------------------------------------

def test_choice_without_choices_raises():
    with pytest.raises(ValueError):
        OptionSpec("s", "--s", OptionType.CHOICE, "h", default="a")


def test_choice_default_not_in_choices_raises():
    with pytest.raises(ValueError):
        OptionSpec("s", "--s", OptionType.CHOICE, "h", default="z",
                   choices=("a", "b"))


def test_choice_default_none_raises():
    with pytest.raises(ValueError):
        OptionSpec("s", "--s", OptionType.CHOICE, "h", default=None,
                   choices=("a", "b"))


def test_bool_without_style_raises():
    with pytest.raises(ValueError):
        OptionSpec("b", "--b", OptionType.BOOL, "h", default=False)


def test_pair_without_negative_flag_raises():
    with pytest.raises(ValueError):
        OptionSpec("b", "--b", OptionType.BOOL, "h", default=True,
                   bool_style=BoolStyle.PAIR)


def test_scalar_with_choices_raises():
    with pytest.raises(ValueError):
        OptionSpec("f", "--f", OptionType.FLOAT, "h", default=1.0,
                   choices=("a",))


def test_flag_must_start_with_dashes():
    with pytest.raises(ValueError):
        OptionSpec("f", "f", OptionType.FLOAT, "h", default=1.0)


def test_bool_default_must_be_bool():
    with pytest.raises(ValueError):
        OptionSpec("b", "--b", OptionType.BOOL, "h", default="yes",
                   bool_style=BoolStyle.POSITIVE_ON)


# --- GeneratorSpec structural validation -----------------------------------

def _dummy_opt():
    return OptionSpec("x", "--x", OptionType.INT, "h", default=0)


def test_generator_empty_options_raises():
    with pytest.raises(ValueError):
        GeneratorSpec(
            name="g", help="h", options=(),
            build_config=lambda ns: None,
            build_and_export=lambda c, ns, e: [],
            summary=lambda c, p: "",
        )


def test_generator_duplicate_dests_raises():
    opt = _dummy_opt()
    with pytest.raises(ValueError):
        GeneratorSpec(
            name="g", help="h", options=(opt, opt),
            build_config=lambda ns: None,
            build_and_export=lambda c, ns, e: [],
            summary=lambda c, p: "",
        )


def test_registered_generators_have_unique_dests_and_nonempty_options():
    import bingrid.cli.generators  # noqa: F401
    from bingrid.cli.registry import REGISTRY

    for spec in REGISTRY.specs():
        assert spec.options
        dests = [o.dest for o in spec.options]
        assert len(dests) == len(set(dests))


# --- shared profile raw material -------------------------------------------

def test_profile_options_identical_between_grid_and_bin():
    import bingrid.cli.generators.grid as grid
    import bingrid.cli.generators.bin as bin_

    profile_dests = [
        "profile_top_opening",
        "profile_chamfer_top",
        "profile_straight",
        "profile_chamfer_bottom",
        "profile_bottom_inset",
    ]

    def by_dest(spec):
        return {o.dest: o for o in spec.options}

    g = by_dest(grid.SPEC)
    b = by_dest(bin_.SPEC)
    for dest in profile_dests:
        assert g[dest].default == b[dest].default
        assert g[dest].help == b[dest].help
