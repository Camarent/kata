# Local capability audit

Results of the local capability audit (`scripts/smoke/local_audit.py`, opt-in with
`KATA_SMOKE_LOCAL=1`). One row per model and task class. The lead fills the rows after a run on
the PC and then sets `[local_capability]` in `config/kata.example.toml` from the verdicts. M26 changed the example file's `[models]`, `[provider_openai]` and `vision` keys, not `[local_capability]`.

Not run yet: every row below is a placeholder.

| model | class | pass rate | seconds | memory | notes | verdict |
|---|---|---|---|---|---|---|
| Strata | (per class) | - | - | - | placeholder, not measured | - |
