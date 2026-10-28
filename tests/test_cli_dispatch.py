"""Dispatcher mode + exit-code/stream contract tests."""
import dataclasses

import pytest

from bingrid.config import BinConfig, GridConfig


@pytest.fixture
def app():
    import bingrid.cli.app as m
    import bingrid.cli.generators  # noqa: F401  ensure registration

    return m


def _force_non_tty(monkeypatch):
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    monkeypatch.setattr("sys.stdout.isatty", lambda: False)


def _capture_config(monkeypatch, name):
    """Replace a generator's build_and_export with a capturing stub.

    Returns a dict that gets ``cfg`` set when the dispatcher runs the tail.
    """
    from bingrid.cli.registry import REGISTRY

    captured = {}
    spec = REGISTRY.get(name)

    def fake_build_and_export(config, ns, exporter):
        captured["cfg"] = config
        return []

    replaced = dataclasses.replace(spec, build_and_export=fake_build_and_export)
    monkeypatch.setitem(REGISTRY._specs, name, replaced)
    return captured


# --- PAIR default parity ----------------------------------------------------

def test_pair_default_survives_bare_subcommand_parse(app):
    parser = app._build_top_parser()
    assert parser.parse_args(["bin"]).stacking_lip is True


# --- Mode 1/4 validation ----------------------------------------------------

def test_bin_x_zero_validation_error(app, tmp_path, capsys):
    rc = app.main(["bin", "--x", "0", "--output-dir", str(tmp_path)])
    assert rc == 2
    assert "error:" in capsys.readouterr().out
    assert not list(tmp_path.glob("*.stl"))


def test_grid_wall_too_thin_validation_error(app, tmp_path, capsys):
    rc = app.main(["grid", "--wall", "0.5", "--output-dir", str(tmp_path)])
    assert rc == 2
    assert "error:" in capsys.readouterr().out
    assert not list(tmp_path.glob("*.stl"))


# --- bin precheck trio ------------------------------------------------------

@pytest.mark.parametrize("flag", ["--3mf", "--split-lip", "--3mf-paint"])
def test_bin_precheck_requires_lip(app, tmp_path, capsys, flag):
    rc = app.main(
        ["bin", flag, "--no-stacking-lip", "--output-dir", str(tmp_path)]
    )
    assert rc == 2
    assert "error:" in capsys.readouterr().out
    assert not list(tmp_path.glob("*"))


# --- Mode 2 non-interactive -------------------------------------------------

def test_mode2_no_item_errors_on_stderr(app, monkeypatch, capsys):
    _force_non_tty(monkeypatch)
    rc = app.main([])
    assert rc == 2
    err = capsys.readouterr().err
    assert "grid, bin" in err


# --- Mode 3 non-interactive fallback (defaults) -----------------------------

def test_mode3_bin_defaults(app, monkeypatch, tmp_path):
    # output_dir is NOT a config field (it only feeds the exporter), so the
    # captured config equals a plain all-defaults BinConfig().
    _force_non_tty(monkeypatch)
    captured = _capture_config(monkeypatch, "bin")
    rc = app.main(["bin", "--no-input", "--output-dir", str(tmp_path)])
    assert rc == 0
    assert captured["cfg"] == BinConfig()


def test_mode3_grid_defaults(app, monkeypatch, tmp_path):
    _force_non_tty(monkeypatch)
    captured = _capture_config(monkeypatch, "grid")
    rc = app.main(["grid", "--no-input", "--output-dir", str(tmp_path)])
    assert rc == 0
    assert captured["cfg"] == GridConfig()


def test_mode3_bin_bare_subcommand_defaults(app, monkeypatch, tmp_path):
    # `bingrid bin` with NO option tokens routes through parse_args([spec.name]).
    _force_non_tty(monkeypatch)
    captured = _capture_config(monkeypatch, "bin")
    rc = app.main(["bin"])
    assert rc == 0
    assert captured["cfg"] == BinConfig()


# --- Mode 1 (options present) is non-interactive, never prompts -------------

def test_mode1_with_no_input_is_noninteractive(app, monkeypatch, tmp_path):
    # --output-dir is an option token, so after stripping --no-input rest is
    # non-empty -> Mode 1 (NOT Mode 3).
    import bingrid.cli.prompter as prompter

    def boom(*a, **k):  # pragma: no cover - must never be called
        raise AssertionError("prompter must not be called in Mode 1")

    monkeypatch.setattr(prompter, "select_item", boom)
    monkeypatch.setattr(prompter, "walk_options", boom)

    captured = _capture_config(monkeypatch, "bin")
    rc = app.main(["bin", "--no-input", "--output-dir", str(tmp_path)])
    assert rc == 0
    assert captured["cfg"] == BinConfig()


# --- No-hang guarantee ------------------------------------------------------

def test_no_input_never_calls_prompter(app, monkeypatch, tmp_path):
    _force_non_tty(monkeypatch)
    import bingrid.cli.prompter as prompter

    calls = []
    for fn in ("select_item", "walk_options", "_ask_text", "_ask_choice",
               "_ask_bool"):
        monkeypatch.setattr(
            prompter, fn,
            lambda *a, _n=fn, **k: calls.append(_n),
        )

    captured = _capture_config(monkeypatch, "bin")
    app.main(["bin", "--no-input", "--output-dir", str(tmp_path)])
    app.main(["bin"])
    assert calls == []


# --- Mode 3 non-interactive end-to-end (renders) ----------------------------

@pytest.mark.integration
def test_mode3_bin_end_to_end_writes_output(app, tmp_path, monkeypatch):
    _force_non_tty(monkeypatch)
    rc = app.main(["bin", "--no-input", "--output-dir", str(tmp_path)])
    assert rc == 0
    assert list(tmp_path.glob("*.stl"))
