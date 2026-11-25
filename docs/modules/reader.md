---
paths: [reader/, worker/kata_worker/reader_spool.py]
summary: Sandboxed document reader (Python) - turns an uploaded PDF or image into page text and clean page PNGs inside a container with no network; the worker sends the PNGs to vision
---
# reader

## Purpose
`kata_reader` is the sandbox for untrusted document bytes. It runs as its own process in the `reader` compose service (`deploy/compose.yaml:126`, command `python -m kata_reader`). It takes a document from the spool, checks it, parses it, and writes back page text plus page PNG images. It never calls a model, never reads a secret, and never talks to the core.

D47 (`docs/decisions.md`, section D47) puts document reading in a sandboxed container with no network, no keys, file in and text out. The M23 reading of D47: the file goes in, and text and clean page PNGs come out of the container. Only text leaves the reader job. The parsing of untrusted bytes (PDFium, image decoders, native code) stays in the sandbox. The model reads the page images that the sandbox re-encoded, through the worker's router (task class `vision`), so the model never sees the raw file. The reasoning is in the M23 plan notes (section "D47 conflict resolved"; not yet in `docs/decisions.md`). A model inside the sandbox was rejected: the dev host has no GPU and the local model runs on another node.

## Public surface
- `reader/kata_reader/__main__.py:24` `main()` - `python -m kata_reader`; loads `[reader]` from `KATA_CONFIG` (default `/config/kata.toml`), serves the spool until SIGTERM (then exit 0). A config error prints one line and exits 2.
- `reader/kata_reader/config.py:35` `load(path) -> ReaderConfig` - reads only the `[reader]` table; a missing key is `ConfigError` (`:24`) naming it. `:17` `CONFIG_ENV`, `:18` `DEFAULT_CONFIG`.
- `reader/kata_reader/extract.py:96` `extract(path, media_type, limits) -> Result` - pure check and parse of one file; writes PNG pages only into the out dir it is given. `:92` `fail(doc_id, code)` builds an error `Result`. `:31` `RESULT_VERSION = 1`; `:36` `ALLOWED_MEDIA` (PDF, PNG, JPEG, WEBP).
- `reader/kata_reader/extract.py:47` `Page`, `:54` `Result` - the result the spool writes as `result.json`.
- `reader/kata_reader/limits.py:13` `Limits` - frozen caps built from `[reader]` (see the config keys below).
- `reader/kata_reader/sandbox.py:36` `run_extract_isolated(...)` and `:44` `run_isolated(target, job, limits, doc_id)` - runs one job in a fresh `python -m kata_reader.child` process under the limits; `:82` `extract_job(job)` is the target for extract.
- `reader/kata_reader/child.py:22` `main()` - child side: reads one JSON job on stdin, sets `RLIMIT_AS` and `RLIMIT_CPU` (`:40` `_apply_limits`), prints the `Result`.
- `reader/kata_reader/spool.py:54` `process_once(...)` - handles at most one request; `:71` `serve(...)` - the poll loop; `:86` `_handle_request`, `:105` `_run_request`, `:133` `_parse_marker`, `:161` `_publish` (rename of the work dir into `out/<id>/`).

## Key files
- `reader/kata_reader/extract.py` - the checks in order (size, magic bytes, page count, decoded size) and the parsing; the only module that imports `pypdfium2` and `PIL`.
- `reader/kata_reader/sandbox.py` - the parent side of the child process: a plain `subprocess`, not `multiprocessing`; the child environment is not inherited (only `PYTHONPATH` and `TMPDIR`, `HOME`).
- `reader/kata_reader/spool.py` - spool protocol v1, reader side.
- `reader/kata_reader/config.py`, `limits.py` - `[reader]` config and the caps.
- `worker/kata_worker/reader_spool.py` - spool protocol v1, worker side (the worker never imports `kata_reader`).
- `worker/kata_worker/handlers/reader_extract.py` - the `reader.extract` job ([worker](worker.md), M23 section).
- `core/kata_core/reader/` and `core/kata_core/api/routes/reader.py` - upload, job queue and output hook in core ([core](core.md)).
- `deploy/compose.yaml:126` - the `reader` service; `:190`, `:191` the `reader-in` and `reader-out` volumes.

## Spool protocol v1
Two named volumes: `reader-in` (worker read-write, reader read-only) and `reader-out` (reader read-write, worker read-write). The request id is uuid4 hex, made by the worker per attempt.

1. The worker writes `in/<id>.bin` (the file), then `in/<id>.json` (the commit marker), each by tmp file and rename. The marker is `{"v":1,"id","media_type","size","sha256"}`.
2. The reader polls `in/*.json` for a marker with no `out/<id>/` and no `out/<id>.tmp/`. It checks size and sha256, and checks the magic bytes against `media_type`. The parse runs in a child process with `RLIMIT_AS`, `RLIMIT_CPU` and a wall timeout. A crash or hang of the child gives an error result.
3. The reader writes `out/<id>.tmp/` and renames it to `out/<id>/`, so the result appears whole or not at all. The contents are `result.json` plus `pNNNN.png` files: `{"v":1,"id","status":"ok|error","error":null|"too_large|bad_type|bad_file|too_many_pages|timeout|bomb","pages":[{"n","text","image":"pNNNN.png"|null}]}`. A page gets an image when it holds an image object or its text is shorter than `min_page_chars`. PNGs are re-encoded with no metadata.
4. The worker waits for `out/<id>/result.json`, checks it (schema, `v` == 1, page count, text caps, PNG magic, PNG byte cap, IHDR size), and deletes `in/<id>.*` and `out/<id>/` in a `finally`. The reader never deletes anything under `in/`: that mount is read-only for it.
5. An unknown `v` or a bad shape fails the job; nothing is half-stored.

A request is handled once: a marker that already has an `out/<id>/` or `out/<id>.tmp/` is skipped. Every failure of one request becomes an error result for that request; the loop does not stop. Paths are built from the id only after it matches `ID_RE`, and no file is followed through a symlink.

## Config keys
All in the `[reader]` table of `config/kata.example.toml` and `deploy/kata.host.toml`; the keys and env names are in [configuration](../configuration.md).
- Upload and extract caps: `enabled` (off by default; `409 reader_disabled` while off), `max_file_bytes`, `max_pages`, `min_page_chars`, `max_image_side_px`, `max_image_bytes`, `max_images_per_document`, `max_text_chars_per_page`.
- Sandbox: `child_memory_mb`, `child_cpu_seconds`, `wall_seconds`.
- Spool: `poll_seconds` (reader poll), `wait_seconds` (worker wait for one result), `spool_dir` (`/spool` in the container; the reader uses `in/` and `out/` under it).

## Hardening of the compose service
`deploy/compose.yaml:126` `reader`: `network_mode: none`; `read_only: true`; `cap_drop: [ALL]`; `security_opt: [no-new-privileges:true]`; `tmpfs: /tmp` with `size=64m,noexec,nosuid`; `healthcheck: disable` (the reader serves no HTTP); no `secrets:`, no `networks:`, no environment entry holding a key or token; the config is mounted read-only (`./kata.host.toml:/config/kata.toml:ro`); `reader-in` is mounted read-only; `pids_limit: 128`; `mem_limit: ${KATA_MEM_READER:-512m}` and `cpus: ${KATA_CPU_READER:-1.0}` (defaults when the env file has no value).

The `check_compose` rule `reader-hardened` in `scripts/deploy/validate_stack.py` (`:160` `_reader_problems`) checks this: `network_mode` is none, `read_only` is true, `cap_drop` has ALL, `security_opt` has `no-new-privileges:true`, none of the no-access keys is set, no environment name looks secret-like, and the config and `reader-in` mounts are read-only. It runs on the normalised model of `docker compose config --format json`; `tests/scripts/test_validate_stack.py` feeds it a parsed model dict (`_reader`, `_set_reader`), never a regex over the YAML. Each violation is one `reader-hardened: <key> ...` line.

## Dependencies
- `pypdfium2` (text and page render; bundles PDFium, Apache-2.0 or BSD-3) and `Pillow` (image decode and re-encode; decompression-bomb guard). Both are in the optional group `reader` (`pyproject.toml:11`), installed in the image's deps stage and in the dev group. No `pypdf`.
- The sandbox imports nothing from `core` or `worker`.

## Import boundary
Core and worker never import `kata_reader`; the reader runs as its own process, behind the spool. `tests/reader/test_import_boundary.py` walks the `core` and `worker` trees with `ast` and fails on any import of `kata_reader`. A second test checks that the helper detects such an import.

## Running extract in tests
- `pytest tests/reader` runs in process, with no container and no real sleep. `pyproject.toml:25` puts `reader` on the test `pythonpath`, so `import kata_reader` works. The optional group `reader` must be installed (`PIL` and `pypdfium2` are imported by the tests).
- `tests/reader/conftest.py` builds the hostile corpus in the test: `make_pdf` (`:16`), `png_bytes` (`:55`), `bomb_png` (`:62`) and the `corpus` fixture (`:92`, `tmp_path`-based). Files: truncated PDF, page-count bomb, decompression-bomb PNG, wrong magic, PDF with a JavaScript action, polyglot, oversize file.
- `tests/reader/test_extract.py` calls `extract()` on that corpus and checks the exact error code. `tests/reader/test_spool.py` drives the spool with a temp dir and `tests/reader/test_sandbox.py` runs the child process limits.
- The worker side is tested in `tests/worker/test_reader_spool.py` and `tests/worker/test_handler_reader_extract.py`, with a fake spool directory and an injected clock.

## Invariants and gotchas
- The reader never sends anything over the network and never reads an env var holding a secret; the child environment holds only `PYTHONPATH`, `TMPDIR` and `HOME`.
- Parse errors become a code (`bad_file`, `bomb`, ...), never a message: a message may carry document text.
- PDF JavaScript is never run: pypdfium2 does not execute it (`reader/kata_reader/extract.py:1-14`).
- Text per page is cut to `max_text_chars_per_page` and control characters except newline are dropped (`reader/kata_reader/extract.py:225` `_clean_text`).
- Each page image is checked for PNG magic, byte cap and IHDR size by the worker before it is read (`worker/kata_worker/reader_spool.py:164`).
- The `reader` service has `enabled` off by default in config; the upload route refuses with `409 reader_disabled` until the owner turns it on.

## Depends on / used by
- Depends on: `pypdfium2`, `Pillow` (`reader` extra), the Python standard library.
- Used by: the worker's `reader.extract` handler (through the spool directories only, [worker](worker.md)); the compose stack ([deploy](deploy.md)); the core upload route `POST /reader/documents` ([api](../api.md)).
- Tests: `tests/reader/`, `tests/worker/test_reader_spool.py`, `tests/worker/test_handler_reader_extract.py`, `tests/scripts/test_validate_stack.py` (the `reader-hardened` rule).
