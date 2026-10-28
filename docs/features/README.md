# Feature docs

Durable status for `bingrid` features — what exists, what's planned. Replaces
the old session-handoff note.

| Feature | Status | Doc |
| --- | --- | --- |
| Gridfinity baseplate / frame | ✅ shipped | [baseplate-and-bins.md](baseplate-and-bins.md) |
| Gridfinity bins (foot, hollow body, stacking lip, split-lip export) | ✅ shipped | [baseplate-and-bins.md](baseplate-and-bins.md) |
| Snug-fit holder bins (item-shaped cradles) | 📋 planned | [snug-fit-holder-bins.md](snug-fit-holder-bins.md) |

## Conventions

- Run CLIs from `src/`: `bingrid grid ...` (baseplate),
  `bingrid bin ...` (bins), `python -m bingrid.meshtools.cli ...`.
- Tests: `pytest` (fast), `pytest -m integration` (builds solids). `src` is on
  pythonpath via `pyproject.toml`; integration tests are deselected by default.
- Commit style: emoji + type + (scope): short description
  (e.g. `✨ feat (bins): ...`). Commit only when asked.

## Licensing (important)

- `samples/` is **gitignored** and must stay out of the repo. The reference STLs
  are under a Standard Digital File License that forbids redistribution. Do not
  commit them or reference them by name in committed code/docs.
- All tests are self-contained: they measure our own generated meshes against
  the published Gridfinity spec, never a sample file. One local-only comparison
  test exists but is `@pytest.mark.skip`'d and points outside the repo.
