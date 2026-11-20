# Backlog

Project items after Milestone 0.

## Open items

- [ ] Load the extension in a real browser (side panel, content script, background wiring,
      real sign-in and "I know this" against a running core). Milestone 0 only checked the
      panel with stubs.
- [ ] Side panel: check dark-theme contrast and keyboard focus and tab order.
- [ ] Coverage: add vitest coverage for the extension and pytest-cov for core and worker,
      record a baseline, add a duplicate-code check. The extension needs a coverage
      dependency vetted first.
- [ ] Narrow the `<all_urls>` content-script permission in `extension/manifest.json` before
      any publish.
- [ ] Python dependencies are pinned with `==` and there is no lock file; decide between
      `uv lock` and pinned versions.
- [ ] Style nits: three `nosec` lines longer than 100 columns; `MarkSink` vs
      `Pick<CoreClient>`.
- [ ] A combined `pytest tests/core tests/worker` run once gave 11 collection errors (each
      directory passes alone). Check that `pytest tests` collects cleanly.
- [ ] Decide whether to track a copy of the project instructions file and the audit tool list,
      which are currently excluded from git.
- [ ] Embeddings, cloud model path, concept-level marks and the guided screen are out of scope
      until later milestones (see [`roadmap.md`](roadmap.md)).
- [ ] Reproducible Postgres test setup (roles, port, config generated from
      `config/kata.example.toml`) as a script or documented commands.
- [ ] Remove hard-coded paths and ports (extension default base URL and host permission).
