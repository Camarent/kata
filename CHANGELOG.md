# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Entries are grouped by component: core, worker, extension, trainer, deploy.

## [Unreleased]

### Added

- core: knowledge model and API for the pipeline.
- worker: local worker that runs the pipeline tasks and reports status.
- extension: browser extension client for Firefox and Chrome.
- trainer: `dojo` trainer CLI runner, configured in the `[trainer]` section.
- deploy: deployment scripts and a container image for the web VM.
- licence: MIT licence in `LICENSE`, declared in `pyproject.toml` and `extension/package.json`.

## [0.1.10] - 2026-11-24

- fix(config): do not echo values in ConfigError messages

## [0.1.9] - 2026-11-24

- fix(security): close CodeQL alerts 5 and 6

## [0.1.8] - 2026-11-24

- chore(docs): cleanup after M18 (docs, tests, dead code, config)

## [0.1.7] - 2026-11-24

- feat(worker): control local models on the GPU PC through worker jobs

## [0.1.6] - 2026-11-24

- feat(routing): local-first routing, needs_cloud refusal and local capability audit

## [0.1.5] - 2026-11-24

- docs(extension): redo extension UI design with navigation, settings, auto-scan and block states

## [0.1.4] - 2026-11-24

- chore(repo): licence, security policy, CI hardening, docs scrub, README rewrite

## [0.1.3] - 2026-11-23

- docs(extension): UI design and static mockups

## [0.1.2] - 2026-11-23

- feat(extension): scan button in side panel and Firefox permission fix

## [0.1.1] - 2026-11-23

- feat(trainer): course limit, unique course names, delete course in panel

## [0.1.0] - 2026-11-23

- docs(release): prepare first release notes and install docs

